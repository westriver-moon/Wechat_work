from flask import jsonify, redirect, request, send_from_directory

from modules.auth.service import (
    authenticate_bit_user,
    current_user,
    is_authenticated,
    login_required_response,
    login_user,
    logout_user,
)


def _public_path(path: str) -> bool:
    if path in {"/login", "/logout"}:
        return True
    if path.startswith("/api/auth/"):
        return True
    if path == "/wechat":
        return True
    if path.startswith("/favicon"):
        return True
    return False


def register_auth_guard(app) -> None:
    @app.before_request
    def require_authentication():
        if _public_path(request.path):
            return None
        if not is_authenticated():
            return login_required_response()
        return None


def register_auth_routes(app) -> None:
    @app.get("/login")
    def login_page():
        if is_authenticated():
            return redirect(request.args.get("next") or "/")
        return send_from_directory(app.static_folder, "login.html")

    @app.get("/logout")
    def logout_page():
        logout_user()
        return redirect("/login")

    @app.post("/api/auth/login")
    def api_auth_login():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        next_url = str(data.get("next") or request.args.get("next") or "/").strip() or "/"
        try:
            profile = authenticate_bit_user(username=username, password=password)
            auth_user = login_user(profile)
            return jsonify({"ok": True, "user": auth_user, "next": next_url})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 401

    @app.post("/api/auth/logout")
    def api_auth_logout():
        logout_user()
        return jsonify({"ok": True})

    @app.get("/api/auth/me")
    def api_auth_me():
        user = current_user()
        if not user:
            return jsonify({"error": "authentication required"}), 401
        return jsonify({"user": user})