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


class WikipediaCollector:
    def __init__(self, rate_limit: float = 0.3):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ResearchCollector/1.0[](https://github.com/yourname/research-collectors)',
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
    def clean_wikipedia_text(text: str) -> str:
        """Improved cleaning: headings, citations, entities"""
        if not text:
            return ""

        # Unescape HTML entities
        text = html_unescape.unescape(text)

        # Better heading conversion
        text = re.sub(r'^==\s*(.+?)\s*==$', r'## \1', text, flags=re.MULTILINE)
        text = re.sub(r'^===\s*(.+?)\s*===$', r'### \1', text, flags=re.MULTILINE)
        text = re.sub(r'^====\s*(.+?)\s*====$', r'#### \1', text, flags=re.MULTILINE)

        # Remove citation markers [1], [2], etc.
        text = re.sub(r'\[\d+\]', '', text)
        text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)

        # Remove unwanted sections
        sections = ['References', 'See also', 'External links', 'Further reading', 'Bibliography', 'Notes']
        for section in sections:
            text = re.split(rf'(?i)^##\s*{section}', text)[0]

        # Clean whitespace
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

            # Batch fetch
            titles = "|".join(r['title'] for r in search_results)
            content_params = {
                'action': 'query',
                'prop': 'extracts',
                'titles': titles,
                'format': 'json',
                'origin': '*',
                'explaintext': True,
            }

            if full_content:
                content_params.update({
                    'exlimit': 'max',
                    'prop': 'extracts|links',
                    'pllimit': 40
                })

            self._throttle()
            content_response = self.session.get(search_url, params=content_params, timeout=25)
            content_response.raise_for_status()

            pages = content_response.json().get('query', {}).get('pages', {})

            for page in pages.values():
                title = page.get('title', '')
                extract = page.get('extract', '')

                # Strong fallback for empty extracts
                if full_content and len(extract) < 200:
                    self._throttle()
                    extract = self._fetch_single_article(title)

                links = []
                if full_content and 'links' in page:
                    links = [
                        {'title': link.get('title'), 'url': f"https://en.wikipedia.org/wiki/{link['title'].replace(' ', '_')}"}
                        for link in page.get('links', []) if link.get('ns') == 0
                    ][:40]

                article = {
                    'title': title,
                    'content': extract,
                    'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    'source': 'Wikipedia',
                    'published': '',
                    'query': query,
                    'collector': 'wikipedia',
                    'links': links
                }

                if full_content:
                    self._save_article(article)

                articles.append(article)

            logger.info(f"Successfully retrieved {len(articles)} articles")
            return articles

        except Exception as e:
            logger.error(f"Wikipedia search error: {e}")
            return []

    def _fetch_single_article(self, title: str) -> str:
        try:
            params = {
                'action': 'query',
                'prop': 'extracts',
                'titles': title,
                'format': 'json',
                'origin': '*',
                'explaintext': True,
                'exlimit': 'max'
            }
            self._throttle()
            resp = self.session.get("https://en.wikipedia.org/w/api.php", params=params, timeout=15)
            resp.raise_for_status()
            page = next(iter(resp.json().get('query', {}).get('pages', {}).values()), {})
            return page.get('extract', '')
        except Exception as e:
            logger.debug(f"Single article fetch failed for {title}: {e}")
            return ""

    def _save_article(self, article: Dict):
        output_dir = Path("wikipedia_articles")
        output_dir.mkdir(exist_ok=True)

        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in article['title'])[:100]
        filepath = output_dir / f"{safe_title}.md"

        clean_content = self.clean_wikipedia_text(article['content'])

        md = f"# {article['title']}\n\n"
        md += f"**URL**: {article['url']}\n"
        md += f"**Collected**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        md += clean_content + "\n\n"

        if article.get('links'):
            md += "## 🔗 Related Wikipedia Articles\n\n"
            for link in article['links'][:25]:
                md += f"- [{link['title']}]({link['url']})\n"

        filepath.write_text(md, encoding='utf-8')
        print(f"    💾 Saved: {filepath.name} ({len(clean_content):,} chars)")


# ====================== STANDALONE TESTING ======================
if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Wikipedia Research Collector")
    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument("--max", type=int, default=5, help="Maximum results (default: 5)")
    parser.add_argument("--full", "-f", action="store_true", help="Fetch full article content")
    
    args = parser.parse_args()
    query = " ".join(args.query).strip() or "artificial intelligence"

    with WikipediaCollector(rate_limit=0.35) as collector:
        results = collector.search(query, max_results=args.max, full_content=args.full)

        mode = "FULL + CLEAN MARKDOWN" if args.full else "PREVIEW"
        print(f"\n🔍 Wikipedia results for: '{query}' ({mode}, max={args.max})")
        print("=" * 100)

        for i, article in enumerate(results, 1):
            print(f"\n[{i}] {article['title']}")
            print(f"    URL: {article['url']}")
            if args.full:
                print(f"    📝 Saved to disk")
            print("-" * 90)
