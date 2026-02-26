from flask import Flask, render_template, request


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/workflow-status")
    def workflow_status():
        config_name = request.args.get("config", "Unknown Configuration")
        status = request.args.get("status", "Unknown")
        return render_template("workflow_status.html", config_name=config_name, status=status)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=True, host="127.0.0.1", port=3306)
