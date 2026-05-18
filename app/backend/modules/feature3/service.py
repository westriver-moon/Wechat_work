import hashlib
import os
import re
import threading
import time
from typing import Dict, Optional, Tuple

from modules.ai.service import build_answer
from modules.auth.service import build_external_identity
from modules.shared.id_utils import generate_view_code
from modules.shared.db import (
    claim_next_task,
    create_question,
    enqueue_task,
    get_or_create_user,
    get_question,
    get_task_summary,
    get_tracked_question,
    mark_task_done,
    mark_task_retry,
    save_answer,
)

WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "replace_with_your_token")
FEATURE3_TICKET_MODE = os.getenv("FEATURE3_TICKET_MODE", "1").strip().lower() in {"1", "true", "yes", "on"}
FEATURE3_AUTO_AI_ANSWER = os.getenv("FEATURE3_AUTO_AI_ANSWER", "0").strip().lower() in {"1", "true", "yes", "on"}
FEATURE3_ENABLE_WORKER = os.getenv("FEATURE3_ENABLE_WORKER", "1").strip().lower() in {"1", "true", "yes", "on"}
FEATURE3_ENABLE_WECHAT_PUSH = os.getenv("FEATURE3_ENABLE_WECHAT_PUSH", "0").strip().lower() in {"1", "true", "yes", "on"}
FEATURE3_WORKER_POLL_SECONDS = float(os.getenv("FEATURE3_WORKER_POLL_SECONDS", "1.5"))
FEATURE3_HELP_URL = os.getenv("FEATURE3_HELP_URL", "/freshman")

TRACK_CMD_PATTERN = re.compile(r"^(?:查|查询|问题)\s*(\d+)\s+([A-Za-z0-9]{4,16})$")
WORKER_STOP_EVENT = threading.Event()
WORKER_THREAD = None


def enqueue_ai_answer_if_enabled(question_id: int) -> None:
    if FEATURE3_AUTO_AI_ANSWER:
        enqueue_task("ai_answer", {"question_id": question_id}, max_attempts=3)


def _process_task(task: Dict) -> None:
    task_type = str(task.get("type") or "").strip()
    payload = task.get("payload") or {}
    if task_type != "ai_answer":
        return

    question_id = int(payload.get("question_id") or 0)
    if question_id <= 0:
        raise ValueError("invalid_question_id")

    question = get_question(question_id)
    if not question:
        return
    if question.get("status") != "pending":
        return

    answer_text = build_answer(str(question.get("content") or "").strip())
    if not answer_text:
        raise RuntimeError("empty_answer_text")

    save_answer(question_id=question_id, content=answer_text, answer_type="ai")


def _worker_loop(app) -> None:
    app.logger.info("feature3 worker started")
    while not WORKER_STOP_EVENT.is_set():
        try:
            task = claim_next_task()
            if not task:
                WORKER_STOP_EVENT.wait(FEATURE3_WORKER_POLL_SECONDS)
                continue

            task_id = int(task.get("id"))
            try:
                _process_task(task)
                mark_task_done(task_id)
            except Exception as exc:
                mark_task_retry(task_id, str(exc))
                app.logger.warning("feature3 task failed: id=%s err=%s", task_id, exc)
        except Exception as exc:
            app.logger.warning("feature3 worker loop error: %s", exc)
            WORKER_STOP_EVENT.wait(FEATURE3_WORKER_POLL_SECONDS)


def start_feature3_worker(app) -> None:
    global WORKER_THREAD
    if not FEATURE3_ENABLE_WORKER:
        return
    if WORKER_THREAD and WORKER_THREAD.is_alive():
        return
    WORKER_THREAD = threading.Thread(target=_worker_loop, args=(app,), daemon=True)
    WORKER_THREAD.start()


def worker_alive() -> bool:
    return bool(WORKER_THREAD and WORKER_THREAD.is_alive())


def get_feature3_runtime_summary() -> Dict:
    return {
        "ticket_mode": FEATURE3_TICKET_MODE,
        "auto_ai_answer": FEATURE3_AUTO_AI_ANSWER,
        "worker_enabled": FEATURE3_ENABLE_WORKER,
        "worker_alive": worker_alive(),
        "task_summary": get_task_summary(),
        "help_url": FEATURE3_HELP_URL,
    }


def get_feature3_status_payload(auth_user: Optional[Dict[str, object]], can_answer: bool, is_admin: bool) -> Dict:
    payload = get_feature3_runtime_summary()
    payload["auth"] = {
        "logged_in": bool(auth_user),
        "user": auth_user or {},
        "can_answer": can_answer,
        "is_admin": is_admin,
    }
    return payload


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def parse_track_command(text: str) -> Tuple[int, str]:
    match = TRACK_CMD_PATTERN.match((text or "").strip())
    if not match:
        return (0, "")
    return (int(match.group(1)), match.group(2).upper())


def verify_wechat_signature(signature: str, timestamp: str, nonce: str) -> bool:
    items = [WECHAT_TOKEN, timestamp, nonce]
    items.sort()
    digest = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()
    return digest == signature


def build_text_reply(to_user: str, from_user: str, text: str) -> str:
    now_ts = int(time.time())
    return f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{now_ts}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{text}]]></Content>
</xml>"""


def build_wechat_reply_text(content: str, from_user: str) -> str:
    if not content:
        return "请先输入你的问题，例如：新生如何选课？"
    if not FEATURE3_TICKET_MODE:
        return build_answer(content)

    question_id, code = parse_track_command(content)
    if question_id > 0 and code:
        tracked = get_tracked_question(question_id, code)
        if not tracked:
            return "未找到对应问题，请检查编号和查询码是否正确。"
        if tracked.get("status") == "answered" and tracked.get("answer"):
            answer_text = str(tracked.get("answer") or "").strip()[:560]
            return f"问题 {question_id} 当前状态：已回复\n\n{answer_text}\n\n如需完整内容，请前往我的问题页面查看。"
        if tracked.get("status") == "closed":
            return f"问题 {question_id} 已关闭。你仍可在“我的问题”页面查看历史记录。"
        return f"问题 {question_id} 正在处理中。请稍后前往“我的问题”页面查看。"

    if (content.startswith("查") or content.startswith("查询") or content.startswith("问题")) and (" " not in content):
        return "查询格式示例：查 123 ABCD1234（编号+查询码）。"

    user = get_or_create_user(
        identity=build_external_identity("wx", from_user),
        role="freshman",
        source="wechat",
        nickname="微信用户",
    )
    question = create_question(
        from_user_id=int(user["id"]),
        title="",
        content=content,
        channel="wechat",
        client_id=None,
    )
    enqueue_ai_answer_if_enabled(int(question["id"]))
    return (
        f"已收到（{now_text()}）。问题编号：{question['id']}，查询码：{question['view_code']}。\n"
        f"请打开“我的问题”页面（{FEATURE3_HELP_URL}）查看进展；\n"
        f"或发送：查 {question['id']} {question['view_code']}"
    )