import logging
import os
import re
from typing import Dict, List, Tuple

import requests

from modules.ai.kb import index_status, query_index
from modules.ai.web_fetcher import (
    build_web_reference,
    format_web_sources_markdown,
    search_and_fetch_public_web,
)
from modules.shared.paths import DATA_ROOT
from modules.shared.text_utils import lexical_score, normalize_text

logger = logging.getLogger(__name__)

FAQ_PATH = DATA_ROOT / "faq.md"

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
KB_PREFERRED_MIN_SCORE = float(os.getenv("KB_PREFERRED_MIN_SCORE", "0.55"))
WEB_FETCH_ENABLED = os.getenv("WEB_FETCH_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}

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
    if not FAQ_PATH.exists():
        return []

    content = FAQ_PATH.read_text(encoding="utf-8")
    rows: List[Tuple[str, str]] = []
    question, answer = "", ""

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("Q:"):
            question = line[2:].strip()
        elif line.startswith("A:"):
            answer = line[2:].strip()
            if question and answer:
                rows.append((question, answer))
                question, answer = "", ""

    return rows


def score_question(input_question: str, faq_question: str) -> float:
    return lexical_score(input_question, faq_question, bidirectional_contains=True)


def retrieve_from_high_freq_cache(user_question: str) -> Tuple[str, float]:
    normalized_question = normalize_text(user_question)
    for keyword, answer in HIGH_FREQ_CACHE.items():
        if keyword in normalized_question:
            return (f"(来源:bit_freshman_rag_handbook.md score:0.980) {answer}", 0.98)
    return ("", 0.0)


def extract_sources(reference_text: str) -> List[Tuple[str, str]]:
    matches = re.findall(r"\(来源:([^\s\)]+)\s+score:([0-9.]+)\)", reference_text or "")
    return [(match[0], match[1]) for match in matches]


def format_sources_markdown(reference_text: str) -> str:
    sources = extract_sources(reference_text)
    if not sources:
        return ""

    lines = ["### 来源"]
    seen = set()
    for source, score in sources:
        key = (source, score)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {source} ({score})")
    return "\n".join(lines)


def append_source_if_missing(answer: str, reference_text: str, markdown: bool = False) -> str:
    if not answer:
        return answer
    if "【来源:" in answer or "### 来源" in answer:
        return answer
    sources = extract_sources(reference_text)
    if not sources:
        return answer

    seen = set()
    labels = []
    for source, score in sources:
        key = (source, score)
        if key in seen:
            continue
        seen.add(key)
        labels.append(f"{source} ({score})")

    if not labels:
        return answer
    if markdown:
        items = "\n".join(f"- {label}" for label in labels)
        return f"{answer.rstrip()}\n\n### 来源\n{items}"
    return f"{answer.rstrip()}\n\n【来源: {'；'.join(labels)}】"


def call_llm(messages: List[Dict[str, str]]) -> str:
    if not LLM_BASE_URL or not LLM_API_KEY:
        return ""

    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": LLM_TEMPERATURE,
        "top_p": LLM_TOP_P,
        "max_tokens": LLM_MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=OPENAI_TIMEOUT,
        )
        if response.status_code != 200:
            logger.warning("LLM request failed: status=%s body=%s", response.status_code, response.text[:300])
            return ""
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.RequestException as exc:
        logger.warning("LLM request exception: %s", exc)
        return ""
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("LLM response parse error: %s", exc)
        return ""


def retrieve_from_faq(user_question: str) -> Tuple[str, float]:
    high_freq_text, high_freq_score = retrieve_from_high_freq_cache(user_question)
    if high_freq_text:
        return (high_freq_text, high_freq_score)

    try:
        results = query_index(user_question, k=8)
    except Exception:
        results = []

    if results:
        parts = []
        for item in results[:6]:
            snippet = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
            if len(snippet) > 360:
                snippet = snippet[:360].rstrip() + "..."
            parts.append(f"(来源:{item['source']} score:{item['score']:.3f}) {snippet}")
        top_score = max(item["score"] for item in results)
        return ("\n\n".join(parts), float(top_score))

    faq_pairs = load_faq()
    if not faq_pairs:
        return ("", 0.0)

    best_score = 0.0
    best_answer = ""
    best_question = ""

    for question, answer in faq_pairs:
        score = score_question(user_question, question)
        if score > best_score:
            best_score = score
            best_answer = answer
            best_question = question

    if best_score >= 0.22 and best_answer:
        reference = f"(来源:faq.md score:{best_score:.3f}) Q:{best_question} A:{best_answer}"
        return (reference, float(best_score))

    return ("", 0.0)


def ask_llm(user_question: str, retrieved_answer: str, retrieved_score: float, markdown: bool = False) -> str:
    if not LLM_BASE_URL or not LLM_API_KEY:
        return ""

    sys_prompt = (
        "你是北京理工大学新生助手。\n"
        "严格仅基于提供的参考知识回答；如果参考知识不足，明确说明无法确定并建议用户查证。\n"
        "回答要准确、简洁、友好。答案末尾必须列出来源（文件名和相似度分数）。"
    )
    if markdown:
        sys_prompt += "\n输出请使用 Markdown，可用小标题和列表提升可读性。"

    reference_block = f"参考知识：\n{retrieved_answer}" if retrieved_answer else "参考知识：无直接匹配。"

    caution_note = ""
    if retrieved_score and retrieved_score < LLM_MIN_CONFIDENCE:
        caution_note = f"注意：检索到的相似度较低（{retrieved_score:.3f}），请谨慎回答并在无法确定时明确说明。\n"

    raw_answer = call_llm(
        [
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": (
                    f"{caution_note}{reference_block}\n\n"
                    f"用户问题：{user_question}\n\n"
                    "请仅基于上述参考知识回答。若证据不足，请明确回复“无法确定”，并给出可查证入口。"
                    + (
                        "输出为 Markdown；结尾用“### 来源”并以列表列出文件名和 score。"
                        if markdown
                        else "答案末尾用【来源: 文件名 (score)】格式列出。"
                    )
                ),
            },
        ]
    )
    if not raw_answer:
        return ""
    return append_source_if_missing(raw_answer, retrieved_answer, markdown=markdown)


def ask_llm_with_web_context(user_question: str, web_reference: str, markdown: bool = False) -> str:
    if not web_reference:
        return ""

    sys_prompt = (
        "你是北京理工大学新生助手。\n"
        "严格仅基于提供的网页抓取内容回答；不要编造网页中未出现的信息。\n"
        "如果网页证据不足，请明确说明无法确定，并建议用户继续访问本次已抓取的网址核验。"
    )
    if markdown:
        sys_prompt += "\n输出请使用 Markdown，可用小标题和列表提升可读性。"

    return call_llm(
        [
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": (
                    f"网页抓取结果：\n{web_reference}\n\n"
                    f"用户问题：{user_question}\n\n"
                    "请仅基于这些网页内容回答，禁止使用未抓取到的外部信息。"
                ),
            },
        ]
    )


def build_web_fallback_answer(fetch_results: List[Dict], markdown: bool = False) -> str:
    useful = [item for item in fetch_results if item.get("ok")]
    if not useful:
        return ""

    if markdown:
        lines = ["### 基于抓取网页的摘要"]
        for item in useful[:3]:
            title = str(item.get("title") or item.get("final_url") or item.get("url") or "网页")
            excerpt = re.sub(r"\s+", " ", str(item.get("excerpt") or "")).strip()
            lines.append(f"- **{title}**：{excerpt}")
        sources_markdown = format_web_sources_markdown(useful)
        if sources_markdown:
            lines.append("")
            lines.append(sources_markdown)
        return "\n".join(lines)

    parts = []
    for item in useful[:3]:
        title = str(item.get("title") or item.get("final_url") or item.get("url") or "网页")
        excerpt = re.sub(r"\s+", " ", str(item.get("excerpt") or "")).strip()
        parts.append(f"{title}: {excerpt}")
    return "\n".join(parts)


def build_answer(question: str, markdown: bool = False) -> str:
    retrieved, top_score = retrieve_from_faq(question)

    if retrieved.startswith("(来源:bit_freshman_rag_handbook.md score:0.980)"):
        cached_answer = retrieved.split(") ", 1)[1] if ") " in retrieved else retrieved
        if markdown:
            return f"{cached_answer}\n\n### 来源\n- bit_freshman_rag_handbook.md (0.980)"
        return f"{cached_answer}\n\n【来源: bit_freshman_rag_handbook.md (0.980)】"

    llm_answer = ask_llm(question, retrieved, top_score, markdown=markdown)
    if llm_answer:
        return llm_answer
    if retrieved:
        if markdown:
            sources_markdown = format_sources_markdown(retrieved)
            source_part = f"\n\n{sources_markdown}" if sources_markdown else ""
            return (
                "### 基于知识库的参考\n"
                f"{retrieved}\n\n"
                "> 如需更准确的实时信息，请以学校和学院最新通知为准。"
                f"{source_part}"
            )
        return f"根据现有资料：{retrieved}\n\n如需更准确的实时信息，请以学校最新通知为准。"
    if markdown:
        return (
            "暂时没有匹配到明确答案。\n\n"
            "你可以尝试：\n"
            "- 换一种问法（例如加上校区、系统名、业务场景）\n"
            "- 使用关键词提问（如 选课、宿舍、校园网、奖助）\n"
            "- 参考学校官网或联系辅导员获取最新通知"
        )
    return "暂时没有匹配到明确答案，建议查看学校官网通知或联系辅导员。"


def build_chat_response(question: str, markdown: bool = False) -> Dict:
    process_steps: List[Dict] = []
    web_sources: List[Dict] = []
    retrieved, top_score = retrieve_from_faq(question)

    if retrieved and top_score >= KB_PREFERRED_MIN_SCORE:
        process_steps.append(
            {
                "stage": "kb_prefetch",
                "ok": True,
                "message": f"本地知识库命中较高（score={top_score:.3f}），已优先使用知识库回答",
                "url": "",
            }
        )
        return {
            "answer": build_answer(question, markdown=markdown),
            "steps": process_steps,
            "web_sources": web_sources,
            "mode": "kb",
        }

    if WEB_FETCH_ENABLED:
        search_bundle = search_and_fetch_public_web(question)
        process_steps.extend(search_bundle.get("steps") or [])
        web_sources = [item for item in (search_bundle.get("results") or []) if item.get("ok")]
        if web_sources:
            web_reference = build_web_reference(web_sources)
            answer = ask_llm_with_web_context(question, web_reference, markdown=markdown)
            if not answer:
                answer = build_web_fallback_answer(web_sources, markdown=markdown)
            sources_markdown = format_web_sources_markdown(web_sources)
            if markdown and sources_markdown and "### 本次访问网址" not in answer:
                answer = f"{answer.rstrip()}\n\n{sources_markdown}"
            process_steps.append({"stage": "answer", "ok": True, "message": "已基于网页搜索结果生成回答", "url": ""})
            return {
                "answer": answer,
                "steps": process_steps,
                "web_sources": web_sources,
                "mode": "web",
            }

        process_steps.append({"stage": "fallback", "ok": True, "message": "网页搜索未获得可用网页，已回退到本地知识库回答", "url": ""})

    answer = build_answer(question, markdown=markdown)
    if process_steps:
        process_steps.append({"stage": "answer", "ok": True, "message": "已生成回答", "url": ""})
    return {
        "answer": answer,
        "steps": process_steps,
        "web_sources": web_sources,
        "mode": "kb",
    }


def get_ai_runtime_summary() -> Dict:
    provider = "deepseek" if DEEPSEEK_API_KEY else ("openai-compatible" if OPENAI_API_KEY else "faq-only")
    kb = index_status()
    return {
        "provider": provider,
        "llm_enabled": bool(LLM_BASE_URL and LLM_API_KEY),
        "model": LLM_MODEL,
        "base_url": LLM_BASE_URL,
        "kb_index_ready": kb.get("ready", False),
        "kb_backend": kb.get("backend", "none"),
        "kb_doc_count": kb.get("doc_count", 0),
        "kb_error": kb.get("error", ""),
    }