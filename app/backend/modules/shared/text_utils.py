from typing import Set


PUNCTUATION_CHARS = "，。！？；：、,.!?;:()（）[]【】{}\n\t\r\"'“”‘’"


def normalize_text(text: str, compact: bool = False) -> str:
    normalized = (text or "").strip().lower()
    for punctuation in PUNCTUATION_CHARS:
        normalized = normalized.replace(punctuation, " ")
    parts = normalized.split()
    return "".join(parts) if compact else " ".join(parts)


def char_ngrams(text: str, n: int = 2, compact: bool = False) -> Set[str]:
    normalized = normalize_text(text, compact=compact)
    if len(normalized) < n:
        return {normalized} if normalized else set()
    return {normalized[index : index + n] for index in range(len(normalized) - n + 1)}


def lexical_score(query: str, content: str, compact: bool = False, bidirectional_contains: bool = False) -> float:
    normalized_query = normalize_text(query, compact=compact)
    normalized_content = normalize_text(content, compact=compact)
    if not normalized_query or not normalized_content:
        return 0.0

    query_bigrams = char_ngrams(normalized_query, 2)
    content_bigrams = char_ngrams(normalized_content, 2)
    query_chars = set(normalized_query)
    content_chars = set(normalized_content)

    overlap_bigrams = len(query_bigrams & content_bigrams) / max(1, len(query_bigrams))
    overlap_chars = len(query_chars & content_chars) / max(1, len(query_chars))
    contain_bonus = 0.0
    if normalized_query in normalized_content:
        contain_bonus = 0.2
    elif bidirectional_contains and normalized_content in normalized_query:
        contain_bonus = 0.2

    return float(min(1.0, 0.55 * overlap_bigrams + 0.35 * overlap_chars + contain_bonus))