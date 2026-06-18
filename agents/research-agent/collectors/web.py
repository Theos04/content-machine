from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
import logging
import time
import urllib.parse
import random
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class RankedResult:
    """Store result with engine-specific ranking"""
    title: str
    url: str
    snippet: str
    source: str
    engine_rank: int = 999
    relevance_score: float = 0.0

# ── Robust Header Rotation (unchanged from your script) ──────────────────────
def _headers() -> dict:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
    ]
    return {
        "User-Agent": random.choice(user_agents),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1"
    }

# ── Engine Strategies (your existing functions) ──────────────────────────────
SEARXNG_INSTANCES = ["https://searx.be", "https://searxng.site", "https://paulgo.io"]

def _searxng(query: str, max_results: int, timeout: int) -> List[RankedResult]:
    results = []
    for idx, instance in enumerate(SEARXNG_INSTANCES):
        try:
            url = f"{instance}/search"
            params = {"q": query, "format": "json", "categories": "general"}
            resp = requests.get(url, params=params, headers=_headers(), timeout=timeout)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for rank, r in enumerate(data.get("results", [])[:max_results]):
                title = r.get("title", "")
                href = r.get("url", "")
                snippet = r.get("content", "")
                if title and href:
                    results.append(RankedResult(
                        title=title, url=href, snippet=snippet,
                        source=f"SearXNG", engine_rank=rank
                    ))
            if results:
                return results
        except Exception:
            continue
    return results

def _mojeek(query: str, max_results: int, timeout: int) -> List[RankedResult]:
    url = f"https://mojeek.com/search?q={urllib.parse.quote(query)}"
    resp = requests.get(url, headers=_headers(), timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for rank, li in enumerate(soup.select("ul.results-standard li")[:max_results]):
        title_el = li.select_one("a.title")
        if not title_el:
            continue
        results.append(RankedResult(
            title=title_el.get_text(strip=True),
            url=title_el.get("href", ""),
            snippet=li.select_one("p.s").get_text(strip=True) if li.select_one("p.s") else "",
            source="Mojeek",
            engine_rank=rank
        ))
    return results

def _bing(query: str, max_results: int, timeout: int) -> List[RankedResult]:
    url = f"https://bing.com/search?q={urllib.parse.quote(query)}&count={max_results}"
    resp = requests.get(url, headers=_headers(), timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for rank, li in enumerate(soup.select("li.b_algo")[:max_results]):
        title_el = li.select_one("h2 a")
        if not title_el:
            continue
        results.append(RankedResult(
            title=title_el.get_text(strip=True),
            url=title_el.get("href", ""),
            snippet=(li.select_one(".b_caption p") or li.select_one("p")).get_text(strip=True) if (li.select_one(".b_caption p") or li.select_one("p")) else "",
            source="Bing",
            engine_rank=rank
        ))
    return results

# ── DATA FUSION: CombSum Algorithm ──────────────────────────────────────────
def fusion_combine_results(all_results: List[List[RankedResult]], max_results: int = 10) -> List[Dict]:
    """
    Implements the CombSum fusion algorithm described in the Wikipedia article.
    Scores are normalized by engine rank position.
    """
    url_scores = defaultdict(float)
    url_data = {}
    
    for engine_results in all_results:
        for result in engine_results:
            # Normalized score: higher rank (lower number) gets higher score
            # Formula: score = 1 / (rank + 1)  (rank starts at 0)
            score = 1.0 / (result.engine_rank + 1)
            url_scores[result.url] += score
            
            # Store the best title/snippet for this URL
            if result.url not in url_data:
                url_data[result.url] = result
            else:
                # Keep the shorter title (often cleaner)
                if len(result.title) < len(url_data[result.url].title):
                    url_data[result.url].title = result.title
    
    # Sort by combined score and return top results
    ranked_urls = sorted(url_scores.items(), key=lambda x: x[1], reverse=True)
    
    final_results = []
    for url, score in ranked_urls[:max_results]:
        result = url_data[url]
        final_results.append({
            "title": result.title,
            "content": result.snippet[:800],
            "url": url,
            "source": result.source,
            "fusion_score": round(score, 3),
            "published": "",
            "query": query,
            "collector": "metasearch",
        })
    
    return final_results

# ── COLLECTION FUSION: Parallel Query Execution ─────────────────────────────
def search_parallel(
    query: str,
    max_results: int = 10,
    timeout: int = 15,
) -> List[Dict[str, Any]]:
    """
    True metasearch: Query ALL engines in parallel, then fuse results.
    This is more sophisticated than waterfall fallback.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    engines = [
        ("Mojeek", _mojeek),      # Most reliable in your tests
        ("Bing", _bing),
        ("SearXNG", _searxng),
    ]
    
    all_results = []
    
    with ThreadPoolExecutor(max_workers=len(engines)) as executor:
        future_to_engine = {
            executor.submit(strategy, query, max_results, timeout): name
            for name, strategy in engines
        }
        
        for future in as_completed(future_to_engine):
            engine_name = future_to_engine[future]
            try:
                results = future.result(timeout=timeout)
                if results:
                    logger.info(f"{engine_name} returned {len(results)} results")
                    all_results.append(results)
                else:
                    logger.debug(f"{engine_name} returned 0 results")
            except Exception as e:
                logger.warning(f"{engine_name} failed: {e}")
    
    if not all_results:
        return []
    
    # Apply data fusion to combine all results
    fused_results = fusion_combine_results(all_results, max_results)
    
    logger.info(f"Fusion complete: {len(fused_results)} unique results from {len(all_results)} engines")
    return fused_results

# ── Fallback: Waterfall (your original approach) ────────────────────────────
def search_waterfall(
    query: str,
    max_results: int = 10,
    timeout: int = 15,
    retry_delay: float = 1.0,
) -> List[Dict[str, Any]]:
    """Original waterfall approach - returns first engine that works"""
    STRATEGIES = [
        ("SearXNG", _searxng),
        ("Mojeek", _mojeek),
        ("Bing", _bing),
    ]
    
    for name, strategy in STRATEGIES:
        try:
            logger.info("Waterfall search via %s for: %r", name, query)
            results = strategy(query, max_results, timeout)
            if results:
                logger.info("%s returned %d results", name, len(results))
                # Convert RankedResult to dict for compatibility
                return [{
                    "title": r.title,
                    "content": r.snippet[:800],
                    "url": r.url,
                    "source": r.source,
                    "published": "",
                    "query": query,
                    "collector": "web",
                } for r in results[:max_results]]
        except Exception as e:
            logger.warning("%s error: %s", name, e)
        time.sleep(retry_delay + random.uniform(0.1, 0.5))
    
    return []

# ── Main search with mode selection ─────────────────────────────────────────
def search(
    query: str,
    max_results: int = 10,
    timeout: int = 15,
    mode: str = "parallel",  # "parallel" (fusion) or "waterfall"
) -> List[Dict[str, Any]]:
    """
    Search the web using metasearch techniques.
    
    Args:
        mode: "parallel" - Query all engines, fuse results (better quality)
              "waterfall" - Try engines sequentially (faster, less reliable)
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    
    query = query.strip()
    
    if mode == "parallel":
        return search_parallel(query, max_results, timeout)
    else:
        return search_waterfall(query, max_results, timeout)

# ── CLI with metasearch info ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        query = input("Search query: ").strip()
    
    if not query:
        print("No query.")
        sys.exit(1)
    
    print(f"\n🔍 Metasearch: {query}")
    print("   Querying multiple engines in parallel with result fusion...\n")
    
    # Use parallel fusion mode for better results
    results = search(query, mode="parallel", max_results=15)
    
    if results:
        print(f"✅ Fused {len(results)} unique results from multiple engines:\n")
        for idx, r in enumerate(results, 1):
            fusion_info = f" [score: {r.get('fusion_score', 'N/A')}]" if 'fusion_score' in r else ""
            print(f"{idx}. {r['title']}{fusion_info}")
            print(f"   {r['url']}")
            if r['content']:
                print(f"   📝 {r['content'][:150]}...")
            print()
    else:
        print("❌ No results found.")
