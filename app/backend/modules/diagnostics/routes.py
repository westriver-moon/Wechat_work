from flask import jsonify

from modules.ai.service import get_ai_runtime_summary
from modules.feature3.service import get_feature3_runtime_summary


def register_diagnostic_routes(app) -> None:
    @app.get("/api/demo_status")
    def api_demo_status():
        payload = get_ai_runtime_summary()
        payload["feature3"] = get_feature3_runtime_summary()
        payload["routes"] = {
            "chat_page": "/chat",
            "chat_api": "/api/chat",
            "kb_query_api": "/api/kb_query",
            "rebuild_index_api": "/api/rebuild_index",
            "freshman_page": "/freshman",
            "senior_page": "/senior",
            "feature3_status_api": "/api/feature3_status",
            "feature3_pending_api": "/api/tasks/pending",
            "feature3_answered_api": "/api/tasks/answered",
        }
        return jsonify(payload)