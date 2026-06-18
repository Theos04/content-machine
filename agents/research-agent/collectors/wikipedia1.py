from typing import List, Dict, Any
import logging
import requests
import time
import re
import html as html_unescape
from pathlib import Path
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import html2text for better markdown conversion
try:
    import html2text
    HAS_HTML2TEXT = True
except ImportError:
    HAS_HTML2TEXT = False
    logger.warning("html2text not installed. Install with: pip install html2text")


class WikipediaCollector:
    def __init__(self, rate_limit: float = 0.3):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ResearchCollector/1.0 (https://github.com/yourname/research-collectors)',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
        })
        self.rate_limit = rate_limit
        self.last_request_time = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.session.close()

    def _throttle(self):
        """Respectful rate limiting"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    @staticmethod
    def _html_to_markdown_with_links(html_content: str) -> str:
        """Convert HTML to markdown while preserving all hyperlinks"""
        if not html_content:
            return ""
        
        if HAS_HTML2TEXT:
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.ignore_emphasis = False
            h.body_width = 0  # Don't wrap lines
            h.unicode_snob = True
            h.skip_internal_links = False
            return h.handle(html_content)
        
        # Fallback manual conversion if html2text not installed
        # Convert Wikipedia internal links: <a href="/wiki/Page_Name">Text</a>
        def replace_wiki_link(match):
            href = match.group(1)
            text = match.group(2)
            # Skip anchor links
            if href.startswith('#'):
                return text
            # Handle relative Wikipedia links
            if href.startswith('/wiki/'):
                # Decode URL-encoded characters
                import urllib.parse
                page_title = urllib.parse.unquote(href[6:])
                return f"[{text}](https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')})"
            # Handle absolute links
            if href.startswith('http'):
                return f"[{text}]({href})"
            return text
        
        # Convert external links: <a href="http://...">Text</a>
        def replace_external_link(match):
            href = match.group(1)
            text = match.group(2)
            return f"[{text}]({href})"
        
        # Apply link conversions
        html_content = re.sub(r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>', replace_wiki_link, html_content, flags=re.IGNORECASE)
        
        # Remove other HTML tags
        html_content = re.sub(r'<[^>]+>', '', html_content)
        
        # Unescape HTML entities
        html_content = html_unescape.unescape(html_content)
        
        return html_content

    @staticmethod
    def clean_wikipedia_text(text: str) -> str:
        """Clean and format Wikipedia text while preserving markdown links"""
        if not text:
            return ""

        # Fix heading levels (wikitext style)
        text = re.sub(r'(?m)^=\s*(.+?)\s*=$', r'# \1', text)
        text = re.sub(r'(?m)^==\s*(.+?)\s*==$', r'## \1', text)
        text = re.sub(r'(?m)^===\s*(.+?)\s*===$', r'### \1', text)
        text = re.sub(r'(?m)^====\s*(.+?)\s*====$', r'#### \1', text)

        # Remove citation markers like [1], [2], [citation needed]
        text = re.sub(r'\[\d+\]', '', text)
        text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)
        
        # Remove edit markers
        text = re.sub(r'\[edit\]', '', text)

        # Don't remove reference sections completely, but clean them
        # Fix multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    def search(self, query: str, max_results: int = 5, full_content: bool = False) -> List[Dict[str, Any]]:
        try:
            self._throttle()
            search_url = "https://en.wikipedia.org/w/api.php"

            # Search phase
            search_params = {
                'action': 'query',
                'list': 'search',
                'srsearch': query,
                'format': 'json',
                'srlimit': min(max_results, 50),
                'origin': '*'
            }

            logger.info(f"Searching Wikipedia for: '{query}' (max={max_results})")
            response = self.session.get(search_url, params=search_params, timeout=15)
            response.raise_for_status()

            search_results = response.json().get('query', {}).get('search', [])
            if not search_results:
                logger.info("No results found")
                return []

            articles = []

            for result in search_results[:max_results]:
                title = result['title']
                
                # Fetch full HTML content with links preserved
                self._throttle()
                content_params = {
                    'action': 'parse',
                    'page': title,
                    'format': 'json',
                    'origin': '*',
                    'prop': 'text|links|categories',
                    'disableeditsection': True,
                    'disablelimitreport': True,
                }
                
                content_response = self.session.get(search_url, params=content_params, timeout=15)
                content_response.raise_for_status()
                
                parse_data = content_response.json()
                
                if 'parse' not in parse_data:
                    logger.warning(f"Could not parse article: {title}")
                    continue
                
                # Extract HTML content
                html_content = parse_data['parse'].get('text', {}).get('*', '')
                
                # Convert HTML to markdown with preserved links
                markdown_content = self._html_to_markdown_with_links(html_content)
                
                # Extract related links
                links = []
                if 'links' in parse_data['parse']:
                    for link in parse_data['parse']['links'][:40]:
                        if link.get('ns') == 0:  # Only main namespace
                            link_title = link.get('*', '')
                            links.append({
                                'title': link_title,
                                'url': f"https://en.wikipedia.org/wiki/{link_title.replace(' ', '_')}"
                            })
                
                # Extract categories
                categories = []
                if 'categories' in parse_data['parse']:
                    categories = [cat.get('*', '') for cat in parse_data['parse']['categories'] if cat.get('hidden') != ''][:20]
                
                article = {
                    'title': title,
                    'content': markdown_content,
                    'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    'source': 'Wikipedia',
                    'published': '',
                    'query': query,
                    'collector': 'wikipedia',
                    'links': links,
                    'categories': categories
                }

                if full_content:
                    self._save_article(article)
                
                articles.append(article)
                self._throttle()  # Be nice to Wikipedia's servers

            logger.info(f"Successfully retrieved {len(articles)} articles")
            return articles

        except Exception as e:
            logger.error(f"Wikipedia search error: {e}")
            return []

    def _save_article(self, article: Dict):
        output_dir = Path("wikipedia_articles")
        output_dir.mkdir(exist_ok=True)

        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in article['title'])[:100]
        filepath = output_dir / f"{safe_title}.md"

        # Clean the content while preserving markdown links
        clean_content = self.clean_wikipedia_text(article['content'])
        
        # Truncate if too long? No, keep full content
        # But remove duplicate newlines

        md = f"# {article['title']}\n\n"
        md += f"**URL**: {article['url']}\n"
        md += f"**Collected**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        md += f"**Categories**: {', '.join(article.get('categories', [])[:10])}\n\n"
        md += "---\n\n"
        md += clean_content + "\n\n"

        if article.get('links'):
            md += "---\n\n"
            md += "## 🔗 Related Wikipedia Articles\n\n"
            # Deduplicate links
            seen = set()
            unique_links = []
            for link in article['links'][:30]:
                if link['title'] not in seen and link['title'] != article['title']:
                    seen.add(link['title'])
                    unique_links.append(link)
            for link in unique_links[:25]:
                md += f"- [{link['title']}]({link['url']})\n"

        filepath.write_text(md, encoding='utf-8')
        
        content_preview = clean_content[:200].replace('\n', ' ')
        print(f"    💾 Saved: {filepath.name} ({len(clean_content):,} chars) - {content_preview[:80]}...")


# ====================== STANDALONE TESTING ======================
if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Wikipedia Research Collector with Hyperlink Preservation")
    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument("--max", type=int, default=5, help="Maximum results (default: 5)")
    parser.add_argument("--full", "-f", action="store_true", help="Fetch full article content with links")

    args = parser.parse_args()
    query = " ".join(args.query).strip() or "artificial intelligence"

    if not HAS_HTML2TEXT:
        print("\n⚠️  Warning: html2text not installed. Link formatting will be basic.")
        print("   For better results, run: pip install html2text\n")

    with WikipediaCollector(rate_limit=0.5) as collector:  # Slightly slower to be respectful
        results = collector.search(query, max_results=args.max, full_content=args.full)

        mode = "FULL + HYPERLINKS" if args.full else "PREVIEW"
        print(f"\n🔍 Wikipedia results for: '{query}' ({mode}, max={args.max})")
        print("=" * 100)

        for i, article in enumerate(results, 1):
            print(f"\n[{i}] {article['title']}")
            print(f"    URL: {article['url']}")
            if article.get('categories'):
                print(f"    Categories: {', '.join(article['categories'][:5])}")
            if args.full:
                print(f"    📝 Saved to disk")
                
                # Show a sample of links in the content
                link_count = len(re.findall(r'\[([^\]]+)\]\([^\)]+\)', article['content']))
                if link_count > 0:
                    print(f"    🔗 Links in content: {link_count}")
            print("-" * 90)
