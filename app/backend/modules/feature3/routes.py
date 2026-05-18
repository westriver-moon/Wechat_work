from xml.etree import ElementTree as ET

from flask import Response, jsonify, request

from modules.auth.service import PERM_ADMIN, PERM_ANSWER, current_user, has_permission, require_permission
from modules.shared.db import (
    close_question,
    create_question,
    get_or_create_user,
    get_question,
    get_tracked_question,
    list_answered_questions,
    list_pending_questions_with_query,
    list_questions_by_owner_identity,
    save_answer,
)
from modules.feature3.service import (
    FEATURE3_ENABLE_WECHAT_PUSH,
    build_text_reply,
    build_wechat_reply_text,
    enqueue_ai_answer_if_enabled,
    get_feature3_status_payload,
    verify_wechat_signature,
)
from modules.feature3.wechat_utils import send_customer_message


def register_feature3_routes(app) -> None:
    @app.post("/api/questions")
    def api_create_question():
        data = request.get_json(silent=True) or {}
        content = str(data.get("content") or "").strip()
        title = str(data.get("title") or "").strip()
        if not content:
            return jsonify({"error": "content is required"}), 400

        auth_user = current_user() or {}
        owner_identity = str(auth_user.get("owner_identity") or "").strip()
        if not owner_identity:
            return jsonify({"error": "authentication required"}), 401

        user = get_or_create_user(identity=owner_identity, role="freshman", source="web", nickname="已认证用户")
        question = create_question(
            from_user_id=int(user["id"]),
            title=title,
            content=content,
            channel="web",
            client_id=None,
        )
        enqueue_ai_answer_if_enabled(int(question["id"]))

        return (
            jsonify(
                {
                    "id": int(question["id"]),
                    "status": "pending",
                    "view_code": str(question["view_code"]),
                    "message": f"已收到，问题编号：{question['id']}。请在“我的问题”页面查看进展。",
                }
            ),
            201,
        )

    @app.get("/api/questions/mine")
    def api_my_questions():
        auth_user = current_user() or {}
        owner_identity = str(auth_user.get("owner_identity") or "").strip()
        if not owner_identity:
            return jsonify({"error": "authentication required"}), 401

        items = list_questions_by_owner_identity(owner_identity=owner_identity, limit=80)
        return jsonify({"items": items})

    @app.get("/api/questions/track")
    def api_track_question():
        question_id_raw = (request.args.get("qid") or "").strip()
        code = (request.args.get("code") or "").strip().upper()
        if not question_id_raw.isdigit() or not code:
            return jsonify({"error": "qid and code are required"}), 400

        item = get_tracked_question(question_id=int(question_id_raw), view_code=code)
        if not item:
            return jsonify({"error": "question not found"}), 404
        return jsonify(item)

    @app.put("/api/questions/<int:question_id>/close")
    def api_close_question(question_id: int):
        data = request.get_json(silent=True) or {}
        view_code = str(data.get("view_code") or request.args.get("view_code") or "").strip().upper()
        auth_user = current_user() or {}
        owner_identity = str(auth_user.get("owner_identity") or "").strip()
        if not owner_identity and not view_code:
            return jsonify({"error": "owner identity or view_code is required"}), 400

        ok = close_question(question_id=question_id, owner_identity=owner_identity or None, view_code=view_code or None)
        if not ok:
            return jsonify({"error": "close failed"}), 403
        return jsonify({"status": "closed"})

    @app.get("/api/tasks/pending")
    def api_tasks_pending():
        denied = require_permission(PERM_ANSWER)
        if denied:
            return denied

        query = (request.args.get("q") or "").strip()
        limit_raw = (request.args.get("limit") or "80").strip()
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 80

        items = list_pending_questions_with_query(limit=limit, query=query)
        return jsonify({"items": items, "query": query})

    @app.get("/api/tasks/answered")
    def api_tasks_answered():
        denied = require_permission(PERM_ANSWER)
        if denied:
            return denied

        query = (request.args.get("q") or "").strip()
        limit_raw = (request.args.get("limit") or "80").strip()
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 80

        items = list_answered_questions(limit=limit, query=query)
        return jsonify({"items": items, "query": query})

    @app.post("/api/answers")
    def api_submit_answer():
        denied = require_permission(PERM_ANSWER)
        if denied:
            return denied

        data = request.get_json(silent=True) or {}
        question_id = int(data.get("question_id") or 0)
        content = str(data.get("content") or "").strip()
        if question_id <= 0 or not content:
            return jsonify({"error": "question_id and content are required"}), 400

        question = get_question(question_id)
        if not question:
            return jsonify({"error": "question not found"}), 404
        if str(question.get("status") or "") == "closed":
            return jsonify({"error": "question is closed"}), 409

        auth_user = current_user() or {}
        student_code = str(auth_user.get("student_code") or "").strip()
        responder_name = str(auth_user.get("name") or "答复人").strip()
        senior_user = get_or_create_user(identity=f"priv:{student_code}", role="senior", source="web", nickname=responder_name)
        save_answer(
            question_id=question_id,
            content=content,
            answerer_id=int(senior_user["id"]),
            answer_type="senior",
        )

        push_result = {"ok": False, "skipped": True}
        if FEATURE3_ENABLE_WECHAT_PUSH:
            from_identity = str((question or {}).get("from_user_identity") or "")
            if from_identity.startswith("wxraw:"):
                openid = from_identity.split(":", 1)[1]
                push_result = send_customer_message(openid, f"你的问题（{question_id}）已有回复，请前往“我的问题”页面查看。")

        return jsonify({"status": "ok", "push": push_result})

    @app.get("/api/feature3_status")
    def api_feature3_status():
        auth_user = current_user() or {}
        payload = get_feature3_status_payload(
            auth_user=auth_user,
            can_answer=has_permission(PERM_ANSWER),
            is_admin=has_permission(PERM_ADMIN),
        )
        return jsonify(payload)

    @app.route("/wechat", methods=["GET", "POST"])
    def wechat():
        signature = request.args.get("signature", "")
        timestamp = request.args.get("timestamp", "")
        nonce = request.args.get("nonce", "")

        if request.method == "GET":
            echostr = request.args.get("echostr", "")
            if verify_wechat_signature(signature, timestamp, nonce):
                return echostr
            return "forbidden", 403

        if not verify_wechat_signature(signature, timestamp, nonce):
            return "forbidden", 403

        try:
            xml_root = ET.fromstring(request.data)
            msg_type = xml_root.findtext("MsgType", default="")
            from_user = xml_root.findtext("FromUserName", default="")
            to_user = xml_root.findtext("ToUserName", default="")

            if msg_type != "text":
                return Response("success", mimetype="text/plain")

            content = xml_root.findtext("Content", default="").strip()
            reply_text = build_wechat_reply_text(content, from_user)
            xml_reply = build_text_reply(from_user, to_user, reply_text)
            return Response(xml_reply, mimetype="application/xml")
        except Exception:
            return Response("success", mimetype="text/plain")