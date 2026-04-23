import hashlib
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple
from xml.etree import ElementTree as ET

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

app = Flask(__name__, static_folder="../frontend", static_url_path="")

WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "replace_with_your_token")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "replace_with_your_model")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

LLM_BASE_URL = DEEPSEEK_BASE_URL if DEEPSEEK_API_KEY else OPENAI_BASE_URL
LLM_API_KEY = DEEPSEEK_API_KEY or OPENAI_API_KEY
LLM_MODEL = DEEPSEEK_MODEL if DEEPSEEK_API_KEY else OPENAI_MODEL
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "15"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.9"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "400"))
LLM_MIN_CONFIDENCE = float(os.getenv("LLM_MIN_CONFIDENCE", "0.60"))

FAQ_PATH = Path(__file__).resolve().parents[1] / "data" / "faq.md"
from kb import build_index, index_status, query_index
PLACE_PAGE_PATH = Path(__file__).resolve().parents[2] / "feature1-place"

HIGH_FREQ_CACHE: Dict[str, str] = {
    "选课": (
        "新生选课建议按以下步骤进行：\n"
        "1) 先在教务系统确认培养方案和必修课。\n"
        "2) 再按教务处通知的时间窗口完成选课与补退选。\n"
        "3) 遇到容量冲突优先联系学院教学秘书。\n"
        "4) 关键入口：教务系统与教学日历（jwc.bit.edu.cn）。"
    ),
    "校园网": (
        "校园网建议按以下步骤：\n"
        "1) 先完成学号身份激活。\n"
        "2) 在校园网/信息化入口按提示完成认证。\n"
        "3) 无法登录时先查统一身份密码状态，再联系信息化服务。\n"
        "4) 常用入口：webvpn.bit.edu.cn、online.bit.edu.cn。"
    ),
    "宿舍": (
        "宿舍相关问题建议流程：\n"
        "1) 入住安排以迎新网和学院通知为准。\n"
        "2) 报到当天按学院分配到指定宿舍楼办理。\n"
        "3) 调整/报修类问题先走宿管与学院辅导员流程。\n"
        "4) 关键入口：迎新网 hi.bit.edu.cn。"
    ),
}


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


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    for p in "，。！？；：、,.!?;:()（）[]【】{}\n\t\r\"'“”‘’":
        text = text.replace(p, " ")
    return " ".join(text.split())


def char_ngrams(text: str, n: int = 2) -> set:
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def score_question(input_q: str, faq_q: str) -> float:
    q = normalize_text(input_q)
    f = normalize_text(faq_q)
    if not q or not f:
        return 0.0

    q2 = char_ngrams(q, 2)
    f2 = char_ngrams(f, 2)
    q1 = set(q)
    f1 = set(f)

    overlap2 = len(q2 & f2) / max(1, len(q2))
    overlap1 = len(q1 & f1) / max(1, len(q1))
    contain_bonus = 0.2 if q in f or f in q else 0.0

    return float(min(1.0, 0.55 * overlap2 + 0.35 * overlap1 + contain_bonus))


def retrieve_from_high_freq_cache(user_question: str) -> Tuple[str, float]:
    q = normalize_text(user_question)
    for keyword, answer in HIGH_FREQ_CACHE.items():
        if keyword in q:
            return (f"(来源:bit_freshman_rag_handbook.md score:0.980) {answer}", 0.98)
    return ("", 0.0)


def extract_sources(reference_text: str) -> List[Tuple[str, str]]:
    matches = re.findall(r"\(来源:([^\s\)]+)\s+score:([0-9.]+)\)", reference_text or "")
    return [(m[0], m[1]) for m in matches]


def append_source_if_missing(answer: str, reference_text: str) -> str:
    if not answer:
        return answer
    if "【来源:" in answer:
        return answer
    sources = extract_sources(reference_text)
    if not sources:
        return answer

    seen = set()
    labels = []
    for src, score in sources:
        key = (src, score)
        if key in seen:
            continue
        seen.add(key)
        labels.append(f"{src} ({score})")
    if not labels:
        return answer
    return f"{answer.rstrip()}\n\n【来源: {'；'.join(labels)}】"


def retrieve_from_faq(user_question: str) -> Tuple[str, float]:
    """Return (reference_text, top_score).

    First try vector search; if none, fall back to simple FAQ matching with score 0.
    """
    high_freq_text, high_freq_score = retrieve_from_high_freq_cache(user_question)
    if high_freq_text:
        return (high_freq_text, high_freq_score)

    try:
        results = query_index(user_question, k=3)
    except Exception:
        results = []

    if results:
        parts = [f"(来源:{r['source']} score:{r['score']:.3f}) {r['text']}" for r in results]
        top_score = max(r["score"] for r in results)
        return ("\n\n".join(parts), float(top_score))

    # fallback to original simple FAQ matching
    faq_pairs = load_faq()
    if not faq_pairs:
        return ("", 0.0)

    best_score = 0.0
    best_answer = ""
    best_question = ""

    for q, a in faq_pairs:
        s = score_question(user_question, q)
        if s > best_score:
            best_score = s
            best_answer = a
            best_question = q
    if best_score >= 0.22 and best_answer:
        ref = f"(来源:faq.md score:{best_score:.3f}) Q:{best_question} A:{best_answer}"
        return (ref, float(best_score))

    return ("", 0.0)


def ask_llm(user_question: str, retrieved_answer: str, retrieved_score: float) -> str:
    if not LLM_BASE_URL or not LLM_API_KEY:
        return ""

    sys_prompt = (
        "你是北京理工大学新生助手。\n"
        "严格仅基于提供的参考知识回答；如果参考知识不足，明确说明无法确定并建议用户查证。\n"
        "回答要准确、简洁、友好。答案末尾必须列出来源（文件名和相似度分数）。"
    )

    if retrieved_answer:
        reference_block = f"参考知识：\n{retrieved_answer}"
    else:
        reference_block = "参考知识：无直接匹配。"

    # If retrieval confidence is low, instruct model to be cautious
    caution_note = ""
    if retrieved_score and retrieved_score < LLM_MIN_CONFIDENCE:
        caution_note = (
            f"注意：检索到的相似度较低（{retrieved_score:.3f}），请谨慎回答并在无法确定时明确说明。\n"
        )

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": f"{caution_note}{reference_block}\n\n用户问题：{user_question}\n\n请仅基于上述参考知识回答，且在答案末尾用【来源: 文件名 (score)】格式列出。若不能确定，请说“无法确定”。",
            },
        ],
        "temperature": LLM_TEMPERATURE,
        "top_p": LLM_TOP_P,
        "max_tokens": LLM_MAX_TOKENS,
    }

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=OPENAI_TIMEOUT,
        )
        if resp.status_code != 200:
            app.logger.warning("LLM request failed: status=%s body=%s", resp.status_code, resp.text[:300])
            return ""
        data = resp.json()
        raw_answer = data["choices"][0]["message"]["content"].strip()
        return append_source_if_missing(raw_answer, retrieved_answer)
    except requests.RequestException as exc:
        app.logger.warning("LLM request exception: %s", exc)
        return ""
    except (KeyError, ValueError, TypeError) as exc:
        app.logger.warning("LLM response parse error: %s", exc)
        return ""


def build_answer(question: str) -> str:
    retrieved, top_score = retrieve_from_faq(question)

    # If high-frequency cache is hit, return deterministic answer to avoid unstable LLM output.
    if retrieved.startswith("(来源:bit_freshman_rag_handbook.md score:0.980)"):
        cached_answer = retrieved.split(") ", 1)[1] if ") " in retrieved else retrieved
        return f"{cached_answer}\n\n【来源: bit_freshman_rag_handbook.md (0.980)】"

    llm_answer = ask_llm(question, retrieved, top_score)
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


@app.post('/api/rebuild_index')
def api_rebuild_index():
    try:
        state = build_index()
        return jsonify({
            "ok": True,
            "ready": bool(state.get("ready")),
            "backend": state.get("backend", "none"),
            "doc_count": int(state.get("doc_count", 0)),
            "error": state.get("error", ""),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get('/api/kb_query')
def api_kb_query():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({"error": "q is required"}), 400

    # retrieve reference and top score
    retrieved, top_score = retrieve_from_faq(q)

    # generate LLM answer when backend is configured
    answer = ""
    if LLM_BASE_URL and LLM_API_KEY:
        answer = ask_llm(q, retrieved, top_score)

    return jsonify({
        "query": q,
        "retrieved": retrieved,
        "top_score": top_score,
        "answer": answer,
    })


@app.get('/api/demo_status')
def api_demo_status():
    provider = "deepseek" if DEEPSEEK_API_KEY else ("openai-compatible" if OPENAI_API_KEY else "faq-only")
    kb = index_status()
    return jsonify({
        "provider": provider,
        "llm_enabled": bool(LLM_BASE_URL and LLM_API_KEY),
        "model": LLM_MODEL,
        "base_url": LLM_BASE_URL,
        "kb_index_ready": kb.get("ready", False),
        "kb_backend": kb.get("backend", "none"),
        "kb_doc_count": kb.get("doc_count", 0),
        "kb_error": kb.get("error", ""),
        "routes": {
            "chat_page": "/chat",
            "chat_api": "/api/chat",
            "kb_query_api": "/api/kb_query",
            "rebuild_index_api": "/api/rebuild_index",
        },
    })


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
