import hashlib
import os
import time
from pathlib import Path
from typing import List, Tuple
from xml.etree import ElementTree as ET

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

app = Flask(__name__, static_folder="../frontend", static_url_path="")

WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "replace_with_your_token")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "replace_with_your_model")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "15"))

FAQ_PATH = Path(__file__).resolve().parents[1] / "data" / "faq.md"
PLACE_PAGE_PATH = Path(__file__).resolve().parents[2] / "feature1-place"


def load_faq() -> List[Tuple[str, str]]:
    """Parse markdown FAQ with simple Q/A blocks."""
    if not FAQ_PATH.exists():
        return []

    content = FAQ_PATH.read_text(encoding="utf-8")
    rows: List[Tuple[str, str]] = []
    q, a = "", ""

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("Q:"):
            q = line[2:].strip()
        elif line.startswith("A:"):
            a = line[2:].strip()
            if q and a:
                rows.append((q, a))
                q, a = "", ""

    return rows


def score_question(input_q: str, faq_q: str) -> int:
    tokens = [t for t in input_q.replace("？", " ").replace("?", " ").split() if t]
    if not tokens:
        return 0
    return sum(1 for t in tokens if t in faq_q)


def retrieve_from_faq(user_question: str) -> str:
    faq_pairs = load_faq()
    if not faq_pairs:
        return ""

    best_score = 0
    best_answer = ""

    for q, a in faq_pairs:
        s = score_question(user_question, q)
        if s > best_score:
            best_score = s
            best_answer = a

    return best_answer if best_score > 0 else ""


def ask_llm(user_question: str, retrieved_answer: str) -> str:
    if not OPENAI_BASE_URL or not OPENAI_API_KEY:
        return ""

    sys_prompt = (
        "你是北京理工大学新生助手。请优先基于提供的参考知识回答，"
        "回答要准确、简洁、友好。如果参考知识不足，请明确说明并建议用户查看学校官网或联系辅导员。"
    )

    reference_block = (
        f"参考知识：{retrieved_answer}" if retrieved_answer else "参考知识：无直接匹配。"
    )

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": f"{reference_block}\n\n用户问题：{user_question}",
            },
        ],
        "temperature": 0.3,
        "max_tokens": 400,
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=OPENAI_TIMEOUT,
        )
        if resp.status_code != 200:
            app.logger.warning("LLM request failed: status=%s body=%s", resp.status_code, resp.text[:300])
            return ""
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.RequestException as exc:
        app.logger.warning("LLM request exception: %s", exc)
        return ""
    except (KeyError, ValueError, TypeError) as exc:
        app.logger.warning("LLM response parse error: %s", exc)
        return ""


def build_answer(question: str) -> str:
    retrieved = retrieve_from_faq(question)
    llm_answer = ask_llm(question, retrieved)
    if llm_answer:
        return llm_answer
    if retrieved:
        return f"根据现有资料：{retrieved}\n\n如需更准确的实时信息，请以学校最新通知为准。"
    return "暂时没有匹配到明确答案，建议查看学校官网通知或联系辅导员。"


def verify_wechat_signature(signature: str, timestamp: str, nonce: str) -> bool:
    items = [WECHAT_TOKEN, timestamp, nonce]
    items.sort()
    digest = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()
    return digest == signature


def build_text_reply(to_user: str, from_user: str, text: str) -> str:
    now_ts = int(time.time())
    reply = f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{now_ts}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{text}]]></Content>
</xml>"""
    return reply


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/chat")
def chat_page():
    return send_from_directory(app.static_folder, "chat.html")


@app.get("/place")
def place_page():
    return send_from_directory(PLACE_PAGE_PATH, "index.html")


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    answer = build_answer(question)
    return jsonify({"answer": answer})


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
        if not content:
            reply_text = "请先输入你的问题，例如：新生如何选课？"
        else:
            reply_text = build_answer(content)

        xml_reply = build_text_reply(from_user, to_user, reply_text)
        return Response(xml_reply, mimetype="application/xml")
    except Exception:
        return Response("success", mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
