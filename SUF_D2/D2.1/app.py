from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import time
from urllib import error as url_error
from urllib import request as url_request

from flask import Flask, jsonify, render_template, request


PROXY_HOST = "127.0.0.1"
PROXY_PORT = 11096
PROXY_API_PREFIX = "/v1"
SIMULATOR_PROCESS = None


def _slugify(name: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return "-".join(part for part in normalized.split("-") if part) or "configuration"


def _yaml_scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)

    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _to_yaml(value, indent: int = 0) -> str:
    prefix = "  " * indent

    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(_to_yaml(item, indent + 1))
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        return "\n".join(lines)

    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(_to_yaml(item, indent + 1))
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
        return "\n".join(lines)

    return f"{prefix}{_yaml_scalar(value)}"


def _parse_yaml_scalar(value: str):
    text = value.strip()
    if text == "true":
        return True
    if text == "false":
        return False
    if text == "null":
        return None

    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        inner = text[1:-1]
        return inner.replace('\\"', '"').replace('\\\\', '\\')

    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _parse_yaml_text(yaml_text: str):
    tokens = []
    for raw_line in yaml_text.splitlines():
        if not raw_line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        tokens.append((indent // 2, raw_line.strip()))

    def parse_block(start_index: int, current_indent: int):
        if start_index >= len(tokens):
            return {}, start_index

        is_list = tokens[start_index][1].startswith("- ")
        container = [] if is_list else {}
        index = start_index

        while index < len(tokens):
            indent_level, content = tokens[index]
            if indent_level < current_indent:
                break
            if indent_level > current_indent:
                break

            if isinstance(container, list):
                if not content.startswith("- "):
                    break
                list_value = content[2:].strip()
                if list_value:
                    container.append(_parse_yaml_scalar(list_value))
                    index += 1
                    continue

                child, index = parse_block(index + 1, current_indent + 1)
                container.append(child)
                continue

            key, _, remainder = content.partition(":")
            key = key.strip()
            remainder = remainder.strip()

            if remainder:
                container[key] = _parse_yaml_scalar(remainder)
                index += 1
                continue

            child, index = parse_block(index + 1, current_indent + 1)
            container[key] = child

        return container, index

    parsed, _ = parse_block(0, 0)
    return parsed if isinstance(parsed, dict) else {}


def _config_dir() -> Path:
    path = Path.cwd() / "configurations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tail_text(path: Path, max_lines: int = 20) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""

    if not lines:
        return ""

    return "\n".join(lines[-max_lines:])


def _proxy_http_request(
    method: str,
    path: str,
    *,
    payload: dict | None = None,
    host: str = PROXY_HOST,
    port: int = PROXY_PORT,
    timeout_sec: float = 1.2,
):
    url = f"http://{host}:{port}{path}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = url_request.Request(url=url, method=method.upper(), data=data, headers=headers)
    try:
        with url_request.urlopen(req, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except url_error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        detail = ""
        if body:
            try:
                parsed = json.loads(body)
                detail = parsed.get("error") or parsed.get("message") or ""
            except Exception:
                detail = body
        raise RuntimeError(detail or f"Proxy HTTP error {exc.code}") from exc
    except url_error.URLError as exc:
        raise ConnectionError(f"Unable to connect to proxy at {host}:{port}") from exc


def _proxy_connected(host: str = PROXY_HOST, port: int = PROXY_PORT) -> bool:
    try:
        reply = _proxy_http_request("GET", f"{PROXY_API_PREFIX}/ping", host=host, port=port, timeout_sec=0.7)
    except Exception:
        return False

    return bool(isinstance(reply, dict) and reply.get("ok"))


def _get_proxy_ping(host: str = PROXY_HOST, port: int = PROXY_PORT):
    try:
        reply = _proxy_http_request("GET", f"{PROXY_API_PREFIX}/ping", host=host, port=port, timeout_sec=0.7)
    except Exception:
        return None

    return reply if isinstance(reply, dict) and reply.get("ok") else None


def _simulator_started_by_app() -> bool:
    global SIMULATOR_PROCESS
    return bool(SIMULATOR_PROCESS is not None and SIMULATOR_PROCESS.poll() is None)


def _find_listening_pid(port: int) -> int | None:
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None

    if result.returncode not in (0, 1):
        return None

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return None

    try:
        return int(lines[0])
    except ValueError:
        return None


def _can_signal_pid(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_pid(pid: int, timeout_sec: float = 3.0) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not _can_signal_pid(pid):
            return True
        time.sleep(0.15)

    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass

    return not _can_signal_pid(pid)


def create_app() -> Flask:
    app_root = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(app_root / "templates"),
        static_folder=str(app_root / "static"),
    )
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/workflow-status")
    def workflow_status():
        config_name = request.args.get("config", "Unknown Configuration")
        status = request.args.get("status", "Unknown")
        return render_template("workflow_status.html", config_name=config_name, status=status)

    @app.route("/api/fs/list")
    def fs_list():
        requested_path = request.args.get("path", "").strip()
        if requested_path:
            target_dir = Path(requested_path).expanduser().resolve()
        else:
            target_dir = Path.home().resolve()

        if not target_dir.exists() or not target_dir.is_dir():
            return jsonify({"error": f"Directory not found: {target_dir}"}), 404

        try:
            entries = []
            for child in target_dir.iterdir():
                entries.append(
                    {
                        "name": child.name,
                        "path": str(child.resolve()),
                        "isDirectory": child.is_dir(),
                    }
                )
        except PermissionError:
            return jsonify({"error": f"Permission denied: {target_dir}"}), 403

        entries.sort(key=lambda entry: (not entry["isDirectory"], entry["name"].lower()))

        parent_path = str(target_dir.parent.resolve()) if target_dir.parent != target_dir else None
        return jsonify(
            {
                "path": str(target_dir),
                "parent": parent_path,
                "entries": entries,
            }
        )

    @app.route("/api/config/save", methods=["POST"])
    def save_config():
        payload = request.get_json(silent=True) or {}
        config_name = str(payload.get("name", "")).strip()
        if not config_name:
            return jsonify({"error": "Configuration name is required."}), 400

        launch_cwd = Path.cwd()
        config_dir = _config_dir()

        file_name = f"{_slugify(config_name)}.yaml"
        output_path = config_dir / file_name

        yaml_payload = {
            "name": config_name,
            "savedFrom": str(launch_cwd),
            "dataSource": payload.get("dataSource", {}),
            "dataTransport": payload.get("dataTransport", {}),
            "hpcCompute": payload.get("hpcCompute", {}),
        }

        output_path.write_text(_to_yaml(yaml_payload) + "\n", encoding="utf-8")

        return jsonify({"ok": True, "path": str(output_path), "file": file_name})

    @app.route("/api/config/list")
    def list_configs():
        config_dir = _config_dir()
        files = sorted(list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.yml")))

        items = []
        for file_path in files:
            name = file_path.stem
            try:
                parsed = _parse_yaml_text(file_path.read_text(encoding="utf-8"))
                if isinstance(parsed.get("name"), str) and parsed["name"].strip():
                    name = parsed["name"].strip()
            except OSError:
                pass

            items.append({"name": name, "file": file_path.name})

        return jsonify({"items": items})

    @app.route("/api/config/load")
    def load_config():
        file_name = (request.args.get("file") or "").strip()
        if not file_name:
            return jsonify({"error": "Missing configuration file name."}), 400

        safe_name = Path(file_name).name
        config_path = _config_dir() / safe_name
        if not config_path.exists() or not config_path.is_file():
            return jsonify({"error": f"Configuration file not found: {safe_name}"}), 404

        try:
            parsed = _parse_yaml_text(config_path.read_text(encoding="utf-8"))
        except OSError:
            return jsonify({"error": f"Unable to read configuration file: {safe_name}"}), 500

        if not isinstance(parsed, dict):
            return jsonify({"error": f"Invalid configuration format: {safe_name}"}), 400

        return jsonify({"config": parsed, "file": safe_name})

    @app.route("/api/proxy/status")
    def proxy_status():
        ping = _get_proxy_ping(PROXY_HOST, PROXY_PORT)
        connected = ping is not None
        local_pid = _find_listening_pid(PROXY_PORT) if connected else None
        can_stop = _can_signal_pid(local_pid)
        return jsonify(
            {
                "connected": connected,
                "host": PROXY_HOST,
                "port": PROXY_PORT,
                "startedByApp": _simulator_started_by_app(),
                "isSimulator": bool(isinstance(ping, dict) and ping.get("service") == "proxy-simulator"),
                "localPid": local_pid,
                "canStop": can_stop,
            }
        )

    @app.route("/api/proxy/start", methods=["POST"])
    def proxy_start():
        global SIMULATOR_PROCESS

        if _proxy_connected(PROXY_HOST, PROXY_PORT):
            return jsonify(
                {
                    "ok": True,
                    "alreadyRunning": True,
                    "host": PROXY_HOST,
                    "port": PROXY_PORT,
                    "startedByApp": _simulator_started_by_app(),
                }
            )

        simulator_script = app_root / "proxy_simulator.py"
        if not simulator_script.exists():
            return jsonify({"ok": False, "error": f"Simulator script not found: {simulator_script.name}"}), 500

        log_path = app_root / "proxy_simulator.log"
        launch_candidates = []
        if sys.executable:
            launch_candidates.append(sys.executable)
        if "python3" not in launch_candidates:
            launch_candidates.append("python3")

        last_error = ""
        started_process = None

        for launcher in launch_candidates:
            try:
                with log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write(
                        f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Launch attempt: {launcher} {simulator_script.name}\n"
                    )
                    log_file.flush()

                log_stream = log_path.open("a", encoding="utf-8")
                child_env = os.environ.copy()
                child_env.pop("WERKZEUG_SERVER_FD", None)
                child_env.pop("WERKZEUG_RUN_MAIN", None)
                process = subprocess.Popen(
                    [launcher, str(simulator_script)],
                    cwd=str(app_root),
                    stdout=log_stream,
                    stderr=log_stream,
                    start_new_session=True,
                    env=child_env,
                )
                log_stream.close()
            except Exception as exc:  # pragma: no cover - OS dependent
                last_error = f"Failed to launch simulator with '{launcher}': {exc}"
                continue

            SIMULATOR_PROCESS = process
            started_process = process

            for _ in range(10):
                time.sleep(0.3)

                if _proxy_connected(PROXY_HOST, PROXY_PORT):
                    return jsonify(
                        {
                            "ok": True,
                            "started": True,
                            "pid": process.pid,
                            "host": PROXY_HOST,
                            "port": PROXY_PORT,
                            "launcher": launcher,
                            "logPath": str(log_path),
                        }
                    )

                if process.poll() is not None:
                    tail = _tail_text(log_path, 18)
                    last_error = f"Simulator exited early with code {process.returncode}."
                    if tail:
                        last_error = f"{last_error}\nRecent simulator log:\n{tail}"
                    break

            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=1.5)
                except Exception:
                    process.kill()
                finally:
                    SIMULATOR_PROCESS = None

        if started_process is not None and started_process.poll() is None:
            SIMULATOR_PROCESS = started_process

        if not last_error:
            last_error = (
                f"Simulator was launched but proxy is still unreachable at {PROXY_HOST}:{PROXY_PORT}."
            )

        return jsonify(
            {
                "ok": False,
                "error": last_error,
                "logPath": str(log_path),
            }
        ), 502

    @app.route("/api/proxy/stop", methods=["POST"])
    def proxy_stop():
        global SIMULATOR_PROCESS

        if SIMULATOR_PROCESS is not None and SIMULATOR_PROCESS.poll() is None:
            process = SIMULATOR_PROCESS
            try:
                process.terminate()
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            except Exception as exc:  # pragma: no cover - OS dependent
                return jsonify({"ok": False, "error": f"Failed to stop simulator: {exc}"}), 500
            finally:
                SIMULATOR_PROCESS = None

            return jsonify({"ok": True, "stopped": True, "host": PROXY_HOST, "port": PROXY_PORT})

        SIMULATOR_PROCESS = None
        pid = _find_listening_pid(PROXY_PORT)
        if not pid:
            return jsonify({"ok": False, "error": "No local proxy process found listening on the configured port."}), 404

        if not _can_signal_pid(pid):
            return jsonify({"ok": False, "error": "Local proxy process exists but cannot be signaled by this Flask app."}), 403

        stopped = _terminate_pid(pid)
        if not stopped:
            return jsonify({"ok": False, "error": f"Failed to stop local proxy process (PID {pid})."}), 500

        return jsonify({"ok": True, "stopped": True, "host": PROXY_HOST, "port": PROXY_PORT, "pid": pid})

    @app.route("/api/workflow/check", methods=["POST"])
    def workflow_check():
        try:
            reply = _proxy_http_request(
                "POST",
                f"{PROXY_API_PREFIX}/check-components",
                host=PROXY_HOST,
                port=PROXY_PORT,
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503

        if not isinstance(reply, dict):
            return jsonify({"ok": False, "error": "Invalid response from proxy."}), 502

        return jsonify(reply)

    @app.route("/api/workflow/run", methods=["POST"])
    def workflow_run():
        try:
            reply = _proxy_http_request(
                "POST",
                f"{PROXY_API_PREFIX}/run-workflow",
                host=PROXY_HOST,
                port=PROXY_PORT,
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503

        if not isinstance(reply, dict):
            return jsonify({"ok": False, "error": "Invalid response from proxy."}), 502

        return jsonify(reply)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=True, host="127.0.0.1", port=3306)
