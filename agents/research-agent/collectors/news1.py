import feedparser
import urllib.parse
import urllib.request
import socket
import time
import hashlib
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional, List, Dict, Any, Tuple
from html.parser import HTMLParser

# Check for feedparser dependency
try:
    import feedparser
except ImportError:
    raise ImportError("Please install feedparser: pip install feedparser")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; NewsFetcher/1.0)"
MAX_RESULTS_LIMIT = 50
DEFAULT_MAX_RESULTS = 10
DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT = 10
DEFAULT_RETRY_DELAY = 1.5


class HTMLLinkExtractor(HTMLParser):
    """HTML parser to extract both text and hyperlinks from content."""
    
    def __init__(self, extract_links: bool = True):
        super().__init__()
        self.text_parts = []
        self.links = []  # Store (text, url) tuples
        self.current_text = []
        self.extract_links = extract_links
        self.skip_tags = {'script', 'style', 'nav', 'header', 'footer'}
        self.in_skip_tag = False
    
    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.in_skip_tag = True
        
        # Extract hyperlinks
        if self.extract_links and tag == 'a':
            for attr, value in attrs:
                if attr == 'href':
                    # Save any accumulated text before the link
                    if self.current_text:
                        text = ' '.join(self.current_text).strip()
                        if text:
                            self.text_parts.append(text)
                        self.current_text = []
                    
                    # Store that we're entering a link
                    self.current_link_url = value
                    self.current_link_text = []
                    return
        
        # Add space after block elements
        if tag in {'p', 'br', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'}:
            if self.current_text:
                self.current_text.append(' ')
    
    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.in_skip_tag = False
        
        # Handle link end
        if self.extract_links and tag == 'a' and hasattr(self, 'current_link_url'):
            link_text = ' '.join(self.current_link_text).strip()
            if link_text and self.current_link_url:
                # Store the link
                self.links.append({
                    'text': link_text,
                    'url': self.current_link_url
                })
                # Add the link text to main text with a placeholder
                self.text_parts.append(f"[{link_text}]({self.current_link_url})")
            elif self.current_link_url:
                # Link with no text (just URL)
                self.text_parts.append(self.current_link_url)
            
            # Clean up
            delattr(self, 'current_link_url')
            delattr(self, 'current_link_text')
            return
    
    def handle_data(self, data):
        if self.in_skip_tag:
            return
        
        if hasattr(self, 'current_link_url'):
            # Inside a link
            self.current_link_text.append(data.strip() if data else '')
        else:
            # Regular text
            if data.strip():
                self.current_text.append(data.strip())
    
    def get_result(self) -> Tuple[str, List[Dict[str, str]]]:
        """Return (cleaned_text, list_of_links) tuple."""
        # Flush any remaining text
        if self.current_text:
            self.text_parts.append(' '.join(self.current_text).strip())
        
        # Join all text parts
        text = ' '.join(self.text_parts)
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text, self.links


def clean_html_with_links(html_content: str, max_length: int = 500) -> Tuple[str, List[Dict[str, str]]]:
    """
    Convert HTML to plain text and extract hyperlinks.
    
    Args:
        html_content: HTML string to clean
        max_length: Maximum length of returned text
        
    Returns:
        Tuple of (cleaned_text, list_of_links_dict)
    """
    if not html_content:
        return "", []
    
    try:
        # Extract text and links using HTML parser
        extractor = HTMLLinkExtractor(extract_links=True)
        extractor.feed(html_content)
        text, links = extractor.get_result()
        
        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length].rsplit(' ', 1)[0] + "..."
        
        return text, links
        
    except Exception as e:
        logger.debug(f"HTML parsing error: {e}")
        # Fallback to regex-based cleaning
        text = re.sub(r'<[^>]+>', ' ', html_content)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Extract links with regex fallback
        links = []
        url_pattern = r'href=["\'](https?://[^"\']+)["\'][^>]*>([^<]+)</a>'
        for match in re.finditer(url_pattern, html_content, re.IGNORECASE):
            links.append({
                'text': match.group(2).strip(),
                'url': match.group(1)
            })
        
        if len(text) > max_length:
            text = text[:max_length].rsplit(' ', 1)[0] + "..."
        
        return text, links


def search(query: str, max_results: int = DEFAULT_MAX_RESULTS, clean_text: bool = True, extract_links: bool = True) -> List[Dict[str, Any]]:
    """
    Unified interface for news collection.

    Args:
        query: Search topic
        max_results: Maximum number of articles to return (1-50)
        clean_text: Whether to clean HTML from content field
        extract_links: Whether to extract hyperlinks from content

    Returns:
        List of articles with standardized fields:
            - title: Article title
            - content: Article summary/description (plain text)
            - content_html: Original HTML content (if needed)
            - links: List of hyperlinks found in content
            - url: Source URL
            - source: Publisher name
            - published: ISO timestamp
            - query: Original search query
            - collector: 'news'
            
    Raises:
        ValueError: If query is empty or max_results is invalid
        RuntimeError: If unable to fetch news after retries
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")
    
    max_results = max(1, min(max_results, MAX_RESULTS_LIMIT))
    
    articles = fetch_news_rss(
        query=query,
        max_results=max_results,
        max_retries=DEFAULT_RETRIES,
        timeout=DEFAULT_TIMEOUT,
        retry_delay=DEFAULT_RETRY_DELAY,
        deduplicate=True,
        language="en-US",
        country="US"
    )

    # Standardize output format
    result = []
    for a in articles:
        content_html = a['summary']
        content_text = ""
        links = []
        
        if clean_text and content_html:
            content_text, links = clean_html_with_links(content_html, max_length=500)
        elif content_html:
            content_text = content_html
        
        article_data = {
            'title': a['title'],
            'content': content_text,
            'content_html': content_html if extract_links else None,
            'links': links if extract_links else [],
            'url': a['url'],
            'source': a['source'],
            'published': a['published_iso'],
            'query': query,
            'collector': 'news'
        }
        
        result.append(article_data)
    
    return result


def fetch_news_rss(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    max_retries: int = DEFAULT_RETRIES,
    timeout: int = DEFAULT_TIMEOUT,
    retry_delay: float = DEFAULT_RETRY_DELAY,
    deduplicate: bool = True,
    language: str = "en-US",
    country: str = "US",
    user_agent: str = DEFAULT_USER_AGENT,
) -> List[dict]:
    """
    Fetch news articles from Google News RSS with robust error handling.
    
    Args:
        query: Search topic (non-empty string)
        max_results: Maximum number of articles (1-50)
        max_retries: Number of retry attempts for failed requests
        timeout: Request timeout in seconds
        retry_delay: Base delay between retries (exponential backoff)
        deduplicate: Remove duplicate articles by URL and title
        language: Language code (e.g., "en-US", "fr-FR")
        country: Country code (e.g., "US", "UK")
        user_agent: Custom User-Agent string
        
    Returns:
        List of article dictionaries with raw feed data
        
    Raises:
        ValueError: Invalid input parameters
        RuntimeError: Failed to fetch feed after all retries
    """
    # ── Input validation ──────────────────────────────────────────────────────
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    max_results = max(1, min(max_results, MAX_RESULTS_LIMIT))
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

            req = urllib.request.Request(
                rss_url,
                headers={"User-Agent": user_agent}
            )
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw_bytes = response.read()

            feed = feedparser.parse(raw_bytes)

            status = getattr(feed, "status", 200)
            if status == 429:
                raise RuntimeError(f"Rate-limited by Google News (HTTP 429)")
            if status >= 400:
                raise RuntimeError(f"HTTP {status} from Google News RSS")

            if feed.bozo and not feed.entries:
                logger.warning(f"Malformed RSS feed: {feed.bozo_exception}")

            break

        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            last_error = exc
            logger.warning("Network error on attempt %d: %s", attempt, exc)

        except RuntimeError as exc:
            last_error = exc
            logger.warning("Server error on attempt %d: %s", attempt, exc)
            if "429" in str(exc):
                time.sleep(retry_delay * 4)
                continue

        except Exception as exc:
            last_error = exc
            logger.error("Unexpected error on attempt %d: %s", attempt, exc)

        if attempt < max_retries:
            sleep_time = retry_delay * (2 ** (attempt - 1))
            logger.info("Retrying in %.1fs …", sleep_time)
            time.sleep(sleep_time)

    if feed is None:
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
    articles: List[dict] = []

    for entry in feed.entries:
        if len(articles) >= max_results:
            break

        title = _safe_text(getattr(entry, "title", None))
        url = _safe_text(getattr(entry, "link", None))

        if not title or not url:
            logger.debug("Skipping entry missing title or URL")
            continue

        if deduplicate:
            title_hash = hashlib.md5(title.lower().encode()).hexdigest()
            if url in seen_urls or title_hash in seen_title_hashes:
                logger.debug("Skipping duplicate: %s", title[:60])
                continue
            seen_urls.add(url)
            seen_title_hashes.add(title_hash)

        # Extract summary/description
        summary = _safe_text(getattr(entry, "summary", None))
        if not summary:
            summary = _safe_text(getattr(entry, "description", None))
        
        # Extract source name
        source_tag = getattr(entry, "source", None)
        source_name = (
            getattr(source_tag, "title", None) if source_tag else None
        ) or getattr(entry, "source", "Google News")
        source_name = _safe_text(source_name)

        # Parse dates
        raw_published = getattr(entry, "published", "")
        published_iso = _parse_date(raw_published)
        
        # Fallback to updated date if published is missing
        if not published_iso:
            raw_updated = getattr(entry, "updated", "")
            published_iso = _parse_date(raw_updated)

        articles.append({
            "title": title,
            "url": url,
            "summary": summary,
            "source": source_name,
            "published": raw_published,
            "published_iso": published_iso,
            "query_tag": query,
        })

    logger.info("Returned %d/%d articles for query: %r", len(articles), max_results, query)
    return articles


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
    Returns empty string if parsing fails.
    """
    if not raw:
        return ""
    
    try:
        dt = parsedate_to_datetime(raw)
        return dt.isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    
    try:
        struct = feedparser._parse_date(raw)
        if struct and len(struct) >= 6:
            return datetime(*struct[:6]).isoformat()
    except Exception:
        pass
    
    return ""


def search_multiple_queries(queries: List[str], max_results_per_query: int = 5, clean_text: bool = True, extract_links: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search for multiple queries and return results grouped by query.
    
    Args:
        queries: List of search topics
        max_results_per_query: Maximum articles per query
        clean_text: Whether to clean HTML from content
        extract_links: Whether to extract hyperlinks
        
    Returns:
        Dictionary mapping query to list of articles
    """
    results = {}
    
    for query in queries:
        try:
            logger.info("Searching for: %s", query)
            results[query] = search(query, max_results=max_results_per_query, clean_text=clean_text, extract_links=extract_links)
            time.sleep(1)  # Rate limiting between different queries
        except Exception as e:
            logger.error("Failed to search for '%s': %s", query, e)
            results[query] = []
    
    return results


def print_article_with_links(article: Dict[str, Any], index: int):
    """Pretty print an article with its extracted links."""
    print(f"\n📰 [{index}] {article['title']}")
    print(f"   📍 Source: {article['source']}")
    print(f"   📅 Published: {article['published']}")
    print(f"   🏷️  Collector: {article['collector']}")
    
    if article['content']:
        print(f"   📝 Summary: {article['content']}")
    
    if article.get('links') and len(article['links']) > 0:
        print(f"   🔗 Links found ({len(article['links'])}):")
        for i, link in enumerate(article['links'][:3], 1):  # Show first 3 links
            print(f"      {i}. {link['text']}")
            print(f"         → {link['url'][:80]}...")
    
    print(f"   🔗 Original RSS URL: {article['url'][:100]}...")


if __name__ == "__main__":
    import sys
    import json
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
        max_results = 3
    else:
        test_query = "artificial intelligence"
        max_results = 3
    
    print(f"\n🔍 Testing unified interface for: {test_query}")
    print("=" * 60)
    
    try:
        # Extract links from content (set extract_links=True)
        results = search(test_query, max_results=max_results, clean_text=True, extract_links=True)
        
        if not results:
            print("❌ No results found")
        else:
            for i, article in enumerate(results, 1):
                print_article_with_links(article, i)
        
        print(f"\n✅ Successfully fetched {len(results)} articles")
        
        # Show JSON export example
        if results:
            print("\n" + "=" * 60)
            print("📊 Sample JSON output (first article):")
            print("=" * 60)
            # Create a clean copy without HTML content for display
            clean_article = {k: v for k, v in results[0].items() if k != 'content_html'}
            print(json.dumps(clean_article, indent=2, ensure_ascii=False)[:800] + "...")
        
        # Test HTML cleaning with links
        print("\n" + "=" * 60)
        print("🧪 Testing HTML cleaning with hyperlinks:")
        sample_html = '<a href="https://example.com/article">Read full article</a> about <a href="https://example.com/nuclear">nuclear fusion</a>'
        cleaned_text, extracted_links = clean_html_with_links(sample_html)
        print(f"   Raw HTML: {sample_html}")
        print(f"   Clean text: {cleaned_text}")
        print(f"   Extracted links: {extracted_links}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
