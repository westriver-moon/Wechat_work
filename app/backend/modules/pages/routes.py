from flask import send_from_directory

from modules.auth.service import PERM_ANSWER, require_permission


def register_page_routes(app) -> None:
    def page_view(filename: str):
        def _view():
            return send_from_directory(app.static_folder, filename)

        return _view

    public_pages = {
        "/": ("index", "index.html"),
        "/chat": ("chat_page", "chat.html"),
        "/place": ("place_page", "place.html"),
        "/freshman": ("freshman_page", "freshman.html"),
    }
    for path, (endpoint, filename) in public_pages.items():
        app.add_url_rule(path, endpoint=endpoint, view_func=page_view(filename))

    @app.get("/senior")
    def senior_page():
        denied = require_permission(PERM_ANSWER)
        if denied:
            return denied
        return send_from_directory(app.static_folder, "senior.html")