import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

from modules.auth.service import sync_auth_identities_from_file
from modules.shared.db import init_db

app = Flask(__name__, static_folder="../web", static_url_path="")
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=max(1, int(os.getenv("AUTH_SESSION_HOURS", "8"))))

from modules.ai.routes import register_ai_routes
from modules.auth.routes import register_auth_guard, register_auth_routes
from modules.diagnostics.routes import register_diagnostic_routes
from modules.feature3.routes import register_feature3_routes
from modules.feature3.service import start_feature3_worker
from modules.pages.routes import register_page_routes

init_db()
try:
    synced = sync_auth_identities_from_file()
    if synced:
        app.logger.info("synced %s privileged auth identities", synced)
except Exception as exc:
    app.logger.warning("failed to sync auth identities: %s", exc)

start_feature3_worker(app)

register_auth_guard(app)
register_auth_routes(app)
register_page_routes(app)
register_ai_routes(app)
register_diagnostic_routes(app)
register_feature3_routes(app)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)