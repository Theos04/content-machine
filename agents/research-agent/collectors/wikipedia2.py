#!/usr/bin/env python3
"""
Wikipedia Research Collector with Hyperlink Preservation
Fetches Wikipedia articles and saves them as Markdown with all internal links preserved
"""

from typing import List, Dict, Any
import logging
import requests
import time
import re
import html as html_unescape
from pathlib import Path
import argparse
import sys

# Try to import html2text for better markdown conversion
try:
    import html2text
    HAS_HTML2TEXT = True
except ImportError:
    HAS_HTML2TEXT = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WikipediaCollector:
    """Wikipedia article collector with hyperlink preservation"""
    
    def __init__(self, rate_limit: float = 0.5):
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
    def _preprocess_html(html_content: str) -> str:
        """Remove navigation templates and other cruft before conversion"""
        if not html_content:
            return ""
        
        # Remove edit links and brackets
        html_content = re.sub(r'<span class="mw-editsection">.*?</span>', '', html_content, flags=re.DOTALL)
        html_content = re.sub(r'<span class="mw-editsection-bracket">.*?</span>', '', html_content, flags=re.DOTALL)
        
        # Remove navigation tables (toc, infobox, navboxes)
        html_content = re.sub(r'<table[^>]*class="[^"]*navbox[^"]*"[^>]*>.*?</table>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<div[^>]*class="[^"]*navbox[^"]*"[^>]*>.*?</div>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<table[^>]*class="[^"]*vertical-navbox[^"]*"[^>]*>.*?</table>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove "v · t · e" navigation text
        html_content = re.sub(r'<span[^>]*class="[^"]*navbar[^"]*"[^>]*>.*?</span>', '', html_content, flags=re.DOTALL)
        
        # Remove hidden categories
        html_content = re.sub(r'<div[^>]*class="[^"]*mw-hidden-catlinks[^"]*"[^>]*>.*?</div>', '', html_content, flags=re.DOTALL)
        
        # Remove citation needed spans but keep the text
        html_content = re.sub(r'<span[^>]*class="[^"]*noprint[^"]*"[^>]*>.*?</span>', '', html_content, flags=re.DOTALL)
        
        # Remove superscript citation numbers
        html_content = re.sub(r'<sup[^>]*class="[^"]*reference[^"]*"[^>]*>.*?</sup>', '', html_content, flags=re.DOTALL)
        
        return html_content

    @staticmethod
    def _html_to_markdown_with_links(html_content: str) -> str:
        """Convert HTML to markdown while preserving all hyperlinks"""
        if not html_content:
            return ""
        
        # Preprocess to remove navigation cruft
        html_content = WikipediaCollector._preprocess_html(html_content)
        
        if HAS_HTML2TEXT:
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.ignore_emphasis = False
            h.body_width = 0  # Don't wrap lines
            h.unicode_snob = True
            h.skip_internal_links = False
            h.inline_links = True  # Keep links inline, not as footnotes
            h.mark_code = True
            h.google_doc = False
            result = h.handle(html_content)
            return result
        
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
                import urllib.parse
                page_title = urllib.parse.unquote(href[6:])
                return f"[{text}](https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')})"
            # Handle absolute links
            if href.startswith('http'):
                return f"[{text}]({href})"
            return text
        
        # Apply link conversions
        html_content = re.sub(r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>', replace_wiki_link, html_content, flags=re.IGNORECASE)
        
        # Remove other HTML tags
        html_content = re.sub(r'<[^>]+>', '', html_content)
        
        # Unescape HTML entities
        html_content = html_unescape.unescape(html_content)
        
        return html_content

    @staticmethod
    def clean_wikipedia_text(text: str) -> str:
        """Clean Wikipedia HTML-to-markdown conversion artifacts"""
        if not text:
            return ""
        
        # Remove template navigation markers [v], [t], [e]
        text = re.sub(r'\s*\[[vte]+\]\s*', ' ', text, flags=re.IGNORECASE)
        
        # Fix malformed markdown links with double titles
        # [Text](/wiki/Page "Tooltip") -> [Text](/wiki/Page)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\s+"[^"]+"\)', r'[\1](\2)', text)
        
        # Remove standalone tooltip artifacts
        text = re.sub(r'\s+"[^"]+"\)', ')', text)
        
        # Remove raw namespace markers like "fr:Le Ravi" in links
        text = re.sub(r'\([a-z]{2}:[^)]+\)', '', text)
        
        # Remove empty links
        text = re.sub(r'\[\]\(\)', '', text)
        
        # Remove "hide" and "show" links
        text = re.sub(r'\[hide\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[show\]', '', text, flags=re.IGNORECASE)
        
        # Fix heading levels (markdown style)
        text = re.sub(r'(?m)^\*{3}\s*(.+?)\s*\*{3}$', r'### \1', text)
        text = re.sub(r'(?m)^\*{2}\s*(.+?)\s*\*{2}$', r'## \1', text)
        
        # Remove "Related categories" section and its content
        text = re.split(r'(?i)^#{1,3}\s*related categories', text)[0]
        text = re.split(r'(?i)^#{1,3}\s*navigation menu', text)[0]
        text = re.split(r'(?i)^#{1,3}\s*see also$', text)[0]  # Keep see also content but remove heading
        
        # Remove leftover list markers with no content
        text = re.sub(r'(?m)^\s*[\*\-\+]\s*$', '', text)
        
        # Remove multiple consecutive blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove trailing whitespace on each line
        text = '\n'.join(line.rstrip() for line in text.split('\n'))
        
        # Remove empty lines at start and end
        text = text.strip()
        
        return text

    def search(self, query: str, max_results: int = 5, full_content: bool = False) -> List[Dict[str, Any]]:
        """Search Wikipedia and fetch articles with preserved hyperlinks"""
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

            for idx, result in enumerate(search_results[:max_results], 1):
                title = result['title']
                logger.info(f"Fetching {idx}/{max_results}: {title}")
                
                # Fetch full HTML content with links preserved
                self._throttle()
                content_params = {
                    'action': 'parse',
                    'page': title,
                    'format': 'json',
                    'origin': '*',
                    'prop': 'text|links|categories|displaytitle',
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
                
                # Clean up the content
                clean_content = self.clean_wikipedia_text(markdown_content)
                
                # Extract related links
                links = []
                if 'links' in parse_data['parse']:
                    seen = set()
                    for link in parse_data['parse']['links'][:50]:
                        if link.get('ns') == 0:  # Only main namespace
                            link_title = link.get('*', '')
                            if link_title and link_title != title and link_title not in seen:
                                seen.add(link_title)
                                links.append({
                                    'title': link_title,
                                    'url': f"https://en.wikipedia.org/wiki/{link_title.replace(' ', '_')}"
                                })
                
                # Extract categories
                categories = []
                if 'categories' in parse_data['parse']:
                    for cat in parse_data['parse']['categories']:
                        cat_title = cat.get('*', '')
                        if cat_title and cat.get('hidden') != '':  # Skip hidden categories
                            categories.append(cat_title)
                    categories = categories[:20]  # Limit to 20 categories
                
                article = {
                    'title': parse_data['parse'].get('displaytitle', title),
                    'content': clean_content,
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

            logger.info(f"Successfully retrieved {len(articles)} articles")
            return articles

        except Exception as e:
            logger.error(f"Wikipedia search error: {e}")
            return []

    def _save_article(self, article: Dict):
        """Save article to disk as markdown file"""
        output_dir = Path("wikipedia_articles")
        output_dir.mkdir(exist_ok=True)

        # Create safe filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in article['title'])[:100]
        filepath = output_dir / f"{safe_title}.md"

        # Build markdown content
        md = f"# {article['title']}\n\n"
        md += f"**URL**: {article['url']}\n"
        md += f"**Collected**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if article.get('categories'):
            md += f"**Categories**: {', '.join(article['categories'][:10])}\n"
        
        md += "\n---\n\n"
        
        # Add main content
        md += article['content']
        
        # Add related links section if there are any
        if article.get('links'):
            md += "\n\n---\n\n"
            md += "## 🔗 Related Wikipedia Articles\n\n"
            # Remove duplicates
            seen = set()
            unique_links = []
            for link in article['links']:
                if link['title'] not in seen and link['title'] != article['title']:
                    seen.add(link['title'])
                    unique_links.append(link)
            
            for link in unique_links[:30]:  # Limit to 30 related links
                md += f"- [{link['title']}]({link['url']})\n"

        # Write to file
        filepath.write_text(md, encoding='utf-8')
        
        # Calculate statistics
        link_count = len(re.findall(r'\[([^\]]+)\]\([^\)]+\)', article['content']))
        word_count = len(article['content'].split())
        
        print(f"    💾 Saved: {filepath.name} ({len(article['content']):,} chars, {word_count:,} words, {link_count} links)")


# ====================== MAIN ENTRY POINT ======================
def main():
    parser = argparse.ArgumentParser(
        description="Wikipedia Research Collector - Fetches articles with preserved hyperlinks",
        epilog="Example: python wikipedia.py 'nuclear reactor' --max 10 --full"
    )
    parser.add_argument("query", nargs="*", help="Search query (enclose in quotes if multiple words)")
    parser.add_argument("--max", "-m", type=int, default=5, help="Maximum number of results (default: 5)")
    parser.add_argument("--full", "-f", action="store_true", help="Save full article content to disk")
    parser.add_argument("--rate-limit", "-r", type=float, default=0.5, help="Rate limit in seconds between requests (default: 0.5)")

    args = parser.parse_args()
    
    # Handle query
    if not args.query:
        print("\n❌ Error: Please provide a search query")
        print("Example: python wikipedia.py 'artificial intelligence' --max 5 --full\n")
        parser.print_help()
        sys.exit(1)
    
    query = " ".join(args.query).strip()

    # Check for html2text
    if not HAS_HTML2TEXT:
        print("\n⚠️  Warning: html2text not installed. Using fallback link conversion.")
        print("   For better results, install it with: pip install html2text\n")

    # Run the collector
    with WikipediaCollector(rate_limit=args.rate_limit) as collector:
        results = collector.search(query, max_results=args.max, full_content=args.full)

        # Print summary
        mode = "FULL + HYPERLINKS" if args.full else "PREVIEW"
        print(f"\n🔍 Wikipedia results for: '{query}' ({mode}, max={args.max})")
        print("=" * 100)

        for i, article in enumerate(results, 1):
            print(f"\n[{i}] {article['title']}")
            print(f"    URL: {article['url']}")
            if article.get('categories'):
                print(f"    Categories: {', '.join(article['categories'][:5])}")
            
            # Count links in content
            link_count = len(re.findall(r'\[([^\]]+)\]\([^\)]+\)', article['content']))
            word_count = len(article['content'].split())
            
            print(f"    Stats: {len(article['content']):,} chars, {word_count:,} words, {link_count} links")
            
            if args.full:
                print(f"    📝 Saved to disk")
            
            # Show first 100 chars of content as preview
            if not args.full:
                preview = article['content'][:150].replace('\n', ' ')
                print(f"    Preview: {preview}...")
            
            print("-" * 90)

        # Summary statistics
        if results:
            total_links = sum(len(re.findall(r'\[([^\]]+)\]\([^\)]+\)', a['content'])) for a in results)
            total_words = sum(len(a['content'].split()) for a in results)
            print(f"\n📊 Summary: Retrieved {len(results)} articles")
            print(f"   Total content: {total_words:,} words, {total_links:,} hyperlinks")
            if args.full:
                print(f"   Saved to: ./wikipedia_articles/")


if __name__ == "__main__":
    main()
