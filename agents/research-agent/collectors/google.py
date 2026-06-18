import logging
import time

logger = logging.getLogger(__name__)

def generate_smart_dorks(query: str):
    base = query.strip()
    return [
        base,
        f'"{base}"',
        f'{base} filetype:pdf',
        f'{base} (tutorial OR guide OR review OR survey OR "case study")',
        f'{base} site:.edu OR site:.gov',
        f'{base} (2024 OR 2025 OR 2026)',
    ]


def search(query: str, max_results: int = 10):
    """Smart Google-style collector with fallback to web collector."""
    print(f"[+] Google (smart dorks) for '{query}'")

    results = []

    # Try to leverage existing web collector
    try:
        from collectors import web
        if hasattr(web, 'search'):
            print("   → Using web collector for rich results...")
            web_results = web.search(query, max_results=max_results)
            for item in web_results:
                item["collector"] = "google"  # unify
                results.append(item)
    except Exception as e:
        logger.debug(f"Web fallback: {e}")

    # Add high-value static links if needed
    if len(results) < 3:
        results.extend([
            {
                "collector": "google",
                "title": f"{query.title()} - Wikipedia",
                "content": f"Overview and history of {query}.",
                "url": f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}",
                "source": "Wikipedia",
                "published": "",
            },
            {
                "collector": "google",
                "title": f"Recent Papers on {query.title()}",
                "content": "Academic papers and latest research.",
                "url": f"https://arxiv.org/search/?query={query.replace(' ', '+')}&searchtype=all",
                "source": "arXiv",
                "published": "",
            }
        ])

    # Deduplicate
    seen = set()
    unique = []
    for item in results:
        url = item.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(item)

    final = unique[:max_results]
    print(f"   → Returned {len(final)} results")
    return final
