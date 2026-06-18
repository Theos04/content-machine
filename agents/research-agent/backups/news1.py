import feedparser
import urllib.parse
import urllib.request
import socket
import time
import hashlib
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_news_rss(
    query: str,
    max_results: int = 10,
    max_retries: int = 3,
    timeout: int = 10,
    retry_delay: float = 1.5,
    deduplicate: bool = True,
    language: str = "en-US",
    country: str = "US",
) -> list[dict]:
    """
    Fetch news articles from Google News RSS with robust error handling.

    Args:
        query:        Search query string.
        max_results:  Maximum number of articles to return (1–50).
        max_retries:  Number of retry attempts on transient failures.
        timeout:      HTTP request timeout in seconds.
        retry_delay:  Base delay (seconds) between retries; doubles each attempt.
        deduplicate:  Remove articles with duplicate titles or URLs.
        language:     BCP-47 language tag  (default: "en-US").
        country:      ISO 3166-1 alpha-2 country code (default: "US").

    Returns:
        List of article dicts with keys:
            title, url, summary, source, published, published_iso, query_tag
    """
    # ── Input validation ──────────────────────────────────────────────────────
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    max_results = max(1, min(max_results, 50))   # clamp to [1, 50]
    query = query.strip()

    encoded_query = urllib.parse.quote(query)
    rss_url = (
        f"https://news.google.com/rss/search"
        f"?q={encoded_query}"
        f"&hl={language}"
        f"&gl={country}"
        f"&ceid={country}:{language.split('-')[0]}"
    )

    # ── Fetch with retries ────────────────────────────────────────────────────
    feed = None
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Fetching RSS (attempt %d/%d): %s", attempt, max_retries, rss_url)

            # feedparser accepts a pre-fetched response; we use urllib so we
            # can enforce a timeout that feedparser itself doesn't expose.
            req = urllib.request.Request(
                rss_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; NewsFetcher/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw_bytes = response.read()

            feed = feedparser.parse(raw_bytes)

            # feedparser surfaces HTTP errors through .status
            status = getattr(feed, "status", 200)
            if status == 429:
                raise RuntimeError(f"Rate-limited by Google News (HTTP 429)")
            if status >= 400:
                raise RuntimeError(f"HTTP {status} from Google News RSS")

            # bozo flag means the feed is malformed XML
            if feed.bozo and not feed.entries:
                raise ValueError(f"Malformed RSS feed: {feed.bozo_exception}")

            break  # success

        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            last_error = exc
            logger.warning("Network error on attempt %d: %s", attempt, exc)

        except RuntimeError as exc:
            last_error = exc
            logger.warning("Server error on attempt %d: %s", attempt, exc)
            if "429" in str(exc):
                time.sleep(retry_delay * 4)   # back off longer on rate-limit
                continue

        if attempt < max_retries:
            sleep_time = retry_delay * (2 ** (attempt - 1))   # exponential back-off
            logger.info("Retrying in %.1fs …", sleep_time)
            time.sleep(sleep_time)

    if feed is None or not hasattr(feed, "entries"):
        raise RuntimeError(
            f"Failed to fetch RSS feed after {max_retries} attempts. "
            f"Last error: {last_error}"
        )

    if not feed.entries:
        logger.warning("Feed parsed successfully but returned 0 entries for query: %r", query)
        return []

    # ── Parse entries ─────────────────────────────────────────────────────────
    seen_urls: set[str] = set()
    seen_title_hashes: set[str] = set()
    articles: list[dict] = []

    for entry in feed.entries:
        if len(articles) >= max_results:
            break

        # — Required fields —
        title = _safe_text(getattr(entry, "title", None))
        url   = _safe_text(getattr(entry, "link",  None))

        if not title or not url:
            logger.debug("Skipping entry missing title or URL")
            continue

        # — Deduplication —
        if deduplicate:
            title_hash = hashlib.md5(title.lower().encode()).hexdigest()
            if url in seen_urls or title_hash in seen_title_hashes:
                logger.debug("Skipping duplicate: %s", title[:60])
                continue
            seen_urls.add(url)
            seen_title_hashes.add(title_hash)

        # — Optional fields —
        summary      = _safe_text(getattr(entry, "summary", None)) or ""
        source_tag   = getattr(entry, "source", None)
        source_name  = (
            getattr(source_tag, "title", None) if source_tag else None
        ) or "Google News"

        raw_published = entry.get("published", "")
        published_iso = _parse_date(raw_published)

        articles.append({
            "title":         title,
            "url":           url,
            "summary":       summary,
            "source":        source_name,
            "published":     raw_published,
            "published_iso": published_iso,
            "query_tag":     query,
        })

    logger.info("Returned %d/%d articles for query: %r", len(articles), max_results, query)
    return articles


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_text(value: object) -> str:
    """Return a stripped string, or '' for None / non-string types."""
    if value is None:
        return ""
    try:
        return str(value).strip()
    except Exception:
        return ""


def _parse_date(raw: str) -> str:
    """
    Parse an RFC 2822 date string to ISO-8601 (UTC).
    Returns '' on failure instead of raising.
    """
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        try:
            # feedparser sometimes returns a 9-tuple
            struct = feedparser._parse_date(raw)  # type: ignore[attr-defined]
            if struct:
                return datetime(*struct[:6]).isoformat()
        except Exception:
            pass
    return ""

if __name__ == "__main__":
    # ── Quick diagnostics ─────────────────────────────────────────────────────
    feed = feedparser.parse("https://news.google.com/rss/search?q=AI&hl=en-US&gl=US&ceid=US:en")
    print("Status :", getattr(feed, "status", "N/A"))
    print("Entries:", len(feed.entries))
    print("Bozo   :", feed.bozo)
    if feed.bozo:
        print("Bozo ex:", feed.bozo_exception)

    print("\n" + "─" * 60 + "\n")

    # ── Actual fetch ──────────────────────────────────────────────────────────
    articles = fetch_news_rss("artificial intelligence", max_results=5)
    for i, a in enumerate(articles, 1):
        print(f"\n[{i}] {a['title']}")
        print(f"    Source:    {a['source']}")
        print(f"    Published: {a['published_iso'] or a['published']}")
        print(f"    URL:       {a['url']}")
