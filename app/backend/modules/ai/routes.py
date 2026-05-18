from flask import jsonify, request

from modules.auth.service import PERM_ADMIN, require_permission
from modules.ai.service import (
    LLM_API_KEY,
    LLM_BASE_URL,
    ask_llm,
    build_chat_response,
    retrieve_from_faq,
)
from modules.ai.kb import build_index


def register_ai_routes(app) -> None:
    @app.post("/api/chat")
    def api_chat():
        data = request.get_json(silent=True) or {}
        question = (data.get("question") or "").strip()
        if not question:
            return jsonify({"error": "question is required"}), 400

        response_payload = build_chat_response(question, markdown=True)
        return jsonify(response_payload)

    @app.post("/api/rebuild_index")
    def api_rebuild_index():
        denied = require_permission(PERM_ADMIN)
        if denied:
            return denied

        try:
            state = build_index()
            return jsonify(
                {
                    "ok": True,
                    "ready": bool(state.get("ready")),
                    "backend": state.get("backend", "none"),
                    "doc_count": int(state.get("doc_count", 0)),
                    "error": state.get("error", ""),
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/kb_query")
    def api_kb_query():
        question = request.args.get("q", "").strip()
        if not question:
            return jsonify({"error": "q is required"}), 400

        retrieved, top_score = retrieve_from_faq(question)

        answer = ""
        if LLM_BASE_URL and LLM_API_KEY:
            answer = ask_llm(question, retrieved, top_score)

        return jsonify(
            {
                "query": question,
                "retrieved": retrieved,
                "top_score": top_score,
                "answer": answer,
            }
        )
