from pathlib import Path

from flask import Flask, jsonify, render_template, request


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

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=True, host="127.0.0.1", port=3306)
