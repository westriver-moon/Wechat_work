import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from modules.ai.web_fetcher import fetch_public_web_url, search_and_fetch_public_web, search_public_web


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for public web fetching used by AI chat")
    parser.add_argument("urls", nargs="*", help="Specific public URLs to test directly")
    parser.add_argument("--search-query", help="Run public web search smoke test with a search query")
    args = parser.parse_args()

    if not args.urls and not args.search_query:
        parser.error("请提供至少一个公开网址，或使用 --search-query 执行全网搜索测试")

    summary = {}
    if args.urls:
        results = [fetch_public_web_url(url) for url in args.urls]
        summary["direct_urls"] = {
            "tested": len(results),
            "ok": sum(1 for item in results if item.get("ok")),
            "results": [
                {
                    "url": item.get("final_url") or item.get("url"),
                    "ok": bool(item.get("ok")),
                    "title": item.get("title") or "",
                    "error": item.get("error") or "",
                    "steps": [step.get("message") for step in item.get("steps") or []],
                }
                for item in results
            ],
        }

    if args.search_query:
        search_bundle = search_public_web(args.search_query)
        fetched_bundle = search_and_fetch_public_web(args.search_query)
        fetched_results = fetched_bundle.get("results") or []
        summary["search"] = {
            "query": args.search_query,
            "candidate_count": len(search_bundle.get("results") or []),
            "candidate_hosts": [item.get("host") for item in (search_bundle.get("results") or [])[:6]],
            "fetched_ok": sum(1 for item in fetched_results if item.get("ok")),
            "fetched_titles": [item.get("title") for item in fetched_results if item.get("ok")][:6],
            "steps": [step.get("message") for step in fetched_bundle.get("steps") or []],
        }

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()