#!/usr/bin/env python3
"""
Production-ready arXiv collector with caching, rate limiting,
rich metadata, optional full-text extraction, PDF download,
progress bars, improved date filtering, and Markdown export.
"""
from typing import List, Dict, Any, Optional
import arxiv
import logging
import hashlib
import time
import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
import requests
import sys
import csv

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    tqdm = lambda x, **kwargs: x  # fallback

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ArxivCollector:
    """
    Enhanced arXiv collector with PDF download, progress, better dates, Markdown.
    """
    def __init__(
        self,
        cache_db: str = "arxiv_cache.db",
        rate_limit: float = 3.0,
        full_text_enabled: bool = False,
        cache_ttl_days: int = 7,
        max_results_cap: int = 1000,
        pdf_dir: str = "arxiv_pdfs"
    ):
        self.full_text_enabled = full_text_enabled
        self.cache_ttl_days = cache_ttl_days
        self.max_results_cap = max_results_cap
        self.pdf_dir = Path(pdf_dir)
        self.pdf_dir.mkdir(exist_ok=True)

        self.client = arxiv.Client(
            page_size=50,
            delay_seconds=max(1, int(1 / rate_limit)) if rate_limit > 0 else 3,
            num_retries=3
        )
        self.cache_db = cache_db
        self._init_cache_db()

    def _init_cache_db(self):
        """Initialize SQLite cache database."""
        with sqlite3.connect(self.cache_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    arxiv_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    full_text TEXT,
                    cached_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cached_at ON papers(cached_at)")

    def _is_cache_stale(self, cached_at: float) -> bool:
        """Check if cache entry is stale based on TTL."""
        return (time.time() - cached_at) > (self.cache_ttl_days * 86400)

    def _get_cached(self, arxiv_id: str) -> Optional[Dict]:
        """Retrieve cached paper if not stale."""
        with sqlite3.connect(self.cache_db) as conn:
            row = conn.execute(
                "SELECT data, full_text, cached_at FROM papers WHERE arxiv_id = ?",
                (arxiv_id,)
            ).fetchone()
            if row:
                data = json.loads(row[0])
                if row[1]:
                    data['full_text'] = row[1]
                if not self._is_cache_stale(row[2]):
                    return data
        return None

    def _cache_paper(self, paper: Dict):
        """Cache a paper in the database."""
        arxiv_id = paper['id']
        full_text = paper.pop('full_text', None)
        data_json = json.dumps({k: v for k, v in paper.items() if k != 'full_text'})
        with sqlite3.connect(self.cache_db) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO papers (arxiv_id, data, full_text, cached_at)
                VALUES (?, ?, ?, ?)
            """, (arxiv_id, data_json, full_text, time.time()))

    def clean_stale_cache(self):
        """Remove stale cache entries."""
        cutoff = time.time() - (self.cache_ttl_days * 86400)
        with sqlite3.connect(self.cache_db) as conn:
            result = conn.execute("DELETE FROM papers WHERE cached_at < ?", (cutoff,))
            deleted = result.rowcount
            if deleted:
                logger.info(f"Removed {deleted} stale cache entries")
                conn.execute("VACUUM")

    def _build_query(self, query: str, categories=None, since_date=None, until_date=None) -> str:
        """Improved arXiv search query builder."""
        parts = []
        if query and query.strip():
            parts.append(f"all:{query}")

        if categories:
            cat_filter = " OR ".join(f"cat:{cat}" for cat in categories)
            parts.append(f"({cat_filter})")

        # Improved date filtering
        if since_date or until_date:
            date_parts = []
            if since_date:
                date_parts.append(since_date.strftime('%Y%m%d'))
            else:
                date_parts.append("00010101")
            if until_date:
                date_parts.append(until_date.strftime('%Y%m%d'))
            else:
                date_parts.append("99991231")
            parts.append(f"submittedDate:[{date_parts[0]} TO {date_parts[1]}]")

        query_str = " AND ".join(parts) if parts else "all:arxiv"
        logger.info(f"Built query: {query_str}")
        return query_str

    def _parse_paper(self, result: arxiv.Result) -> Dict[str, Any]:
        """Parse arXiv result into standard dictionary format."""
        return {
            'id': result.entry_id.split('/')[-1],
            'title': result.title,
            'abstract': result.summary,
            'authors': [{'name': a.name, 'orcid': getattr(a, 'orcid', None)} for a in result.authors],
            'categories': result.categories,
            'primary_category': result.primary_category,
            'published': result.published.isoformat() if result.published else None,
            'updated': result.updated.isoformat() if result.updated else None,
            'doi': result.doi,
            'journal_ref': result.journal_ref,
            'comments': result.comment,
            'pdf_url': result.pdf_url,
            'entry_id': result.entry_id,
            'source': 'arXiv',
            'collector': 'arxiv',
            'query': None
        }

    def _get_pdfplumber(self):
        """Lazy import of pdfplumber."""
        try:
            import pdfplumber
            return pdfplumber
        except ImportError:
            logger.warning("pdfplumber not installed. Install with: pip install pdfplumber")
            return None

    def _extract_full_text(self, pdf_url: str) -> Optional[str]:
        """Extract text from PDF using pdfplumber with better error handling."""
        pdfplumber = self._get_pdfplumber()
        if not pdfplumber:
            return None
        try:
            cache_dir = Path("arxiv_pdf_cache")
            cache_dir.mkdir(exist_ok=True)
            pdf_hash = hashlib.md5(pdf_url.encode()).hexdigest()
            pdf_path = cache_dir / f"{pdf_hash}.pdf"

            if not pdf_path.exists():
                logger.info(f"Downloading PDF for extraction: {pdf_url}")
                response = requests.get(pdf_url, stream=True, timeout=60)
                response.raise_for_status()
                with open(pdf_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

            logger.info(f"Extracting text from {pdf_path.name}")
            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text(x_tolerance=3, y_tolerance=3)
                    if page_text:
                        text_parts.append(page_text.strip())
            return "\n\n".join(text_parts)
        except Exception as e:
            logger.warning(f"Failed to extract full text from {pdf_url}: {e}")
            return None

    def _download_pdf(self, paper: Dict, pdf_dir: Path) -> Optional[Path]:
        """Download PDF for a paper."""
        if not paper.get('pdf_url'):
            return None
        arxiv_id = paper['id']
        pdf_path = pdf_dir / f"{arxiv_id.replace('/', '_')}.pdf"

        if pdf_path.exists():
            logger.info(f"PDF already exists: {pdf_path.name}")
            return pdf_path

        try:
            logger.info(f"Downloading PDF: {paper['title'][:60]}...")
            response = requests.get(paper['pdf_url'], stream=True, timeout=60)
            response.raise_for_status()
            with open(pdf_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"✅ Downloaded: {pdf_path.name}")
            return pdf_path
        except Exception as e:
            logger.warning(f"Failed to download PDF for {arxiv_id}: {e}")
            return None

    def search(
        self,
        query: str,
        max_results: int = 10,
        categories: Optional[List[str]] = None,
        since_date: Optional[datetime] = None,
        until_date: Optional[datetime] = None,
        sort_by: str = "relevance",
        download_pdfs: bool = False
    ) -> List[Dict[str, Any]]:
        """Main search method with progress and optional PDF download."""
        actual_max = min(max_results, self.max_results_cap)
        if max_results > self.max_results_cap:
            logger.warning(f"Capping results from {max_results} to {actual_max}")

        try:
            search_query = self._build_query(query, categories, since_date, until_date)
            sort_map = {
                "relevance": arxiv.SortCriterion.Relevance,
                "submitted": arxiv.SortCriterion.SubmittedDate,
                "last_updated": arxiv.SortCriterion.LastUpdatedDate,
            }
            sort_criterion = sort_map.get(sort_by.lower(), arxiv.SortCriterion.Relevance)

            search = arxiv.Search(
                query=search_query,
                max_results=actual_max,
                sort_by=sort_criterion
            )

            papers = []
            results = list(self.client.results(search))

            # Progress bar for processing
            progress_bar = tqdm(results, desc="Processing papers", disable=not TQDM_AVAILABLE) if TQDM_AVAILABLE else results

            for result in progress_bar:
                arxiv_id = result.entry_id.split('/')[-1]
                cached = self._get_cached(arxiv_id)
                if cached:
                    papers.append(cached)
                    continue

                paper = self._parse_paper(result)
                paper['query'] = query

                if self.full_text_enabled:
                    paper['full_text'] = self._extract_full_text(result.pdf_url)

                self._cache_paper(paper)
                papers.append(paper)

                # Download PDF if requested
                if download_pdfs:
                    self._download_pdf(paper, self.pdf_dir)

            logger.info(f"Retrieved {len(papers)} papers for query: '{query}'")
            return papers
        except arxiv.HTTPError as e:
            logger.error(f"HTTP Error for query '{query}': {e}")
            logger.info("Try simplifying your query (remove date filters or categories)")
            return []
        except Exception as e:
            logger.error(f"Error during search for '{query}': {e}", exc_info=True)
            return []

    def export_to_json(self, papers: List[Dict], output_file: str):
        """Export papers to JSON file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(papers, f, indent=2, default=str)
        logger.info(f"Exported {len(papers)} papers to {output_file}")

    def export_to_csv(self, papers: List[Dict], output_file: str):
        """Export basic metadata to CSV."""
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['id', 'title', 'published', 'primary_category', 'authors'])
            writer.writeheader()
            for paper in papers:
                writer.writerow({
                    'id': paper['id'],
                    'title': paper['title'],
                    'published': paper['published'],
                    'primary_category': paper['primary_category'],
                    'authors': ', '.join(a['name'] for a in paper['authors'][:5])
                })
        logger.info(f"Exported {len(papers)} papers to {output_file}")

    def export_to_markdown(self, papers: List[Dict], output_file: str):
        """Export to nice Markdown summary."""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"# arXiv Search Results\n\n")
            f.write(f"**Query:** {papers[0].get('query', 'N/A') if papers else 'N/A'}\n")
            f.write(f"**Total papers:** {len(papers)}\n\n")

            for i, paper in enumerate(papers, 1):
                f.write(f"## {i}. {paper['title']}\n\n")
                f.write(f"**arXiv ID:** [{paper['id']}](https://arxiv.org/abs/{paper['id']})\n")
                f.write(f"**Published:** {paper['published'][:10] if paper['published'] else 'N/A'}\n")
                f.write(f"**Category:** {paper['primary_category']}\n")

                authors = [a['name'] for a in paper['authors']]
                f.write(f"**Authors:** {', '.join(authors[:5])}{' et al.' if len(authors) > 5 else ''}\n\n")

                abstract = paper['abstract']
                f.write(f"**Abstract:**\n{abstract}\n\n")

                if paper.get('full_text'):
                    f.write(f"**Full Text Length:** {len(paper['full_text']):,} characters\n\n")

                f.write(f"[PDF]({paper.get('pdf_url', '#')})\n\n")
                f.write("---\n\n")
        logger.info(f"Exported Markdown summary to {output_file}")

# ====================== COMMAND-LINE INTERFACE ======================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Enhanced arXiv Research Collector",
        epilog="""
Examples:
  python arxiv_2.py "attention is all you need" --max 5 --download-pdfs
  python arxiv_2.py "machine learning" --max 20 --categories cs.LG cs.AI --markdown
  python arxiv_2.py "quantum computing" --since 2024-01-01 --sort submitted --full-text
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument("--max", "-m", type=int, default=10, help="Maximum results")
    parser.add_argument("--categories", "-c", nargs="+", help="Categories")
    parser.add_argument("--since", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--until", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--sort", choices=["relevance", "submitted", "last_updated"], default="relevance")
    parser.add_argument("--full-text", "-f", action="store_true", help="Extract full text")
    parser.add_argument("--download-pdfs", "-d", action="store_true", help="Download PDFs")
    parser.add_argument("--markdown", "-md", action="store_true", help="Export Markdown summary")
    parser.add_argument("--output", "-o", type=str, help="Output JSON file")
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--rate-limit", type=float, default=3.0)

    args = parser.parse_args()

    query = " ".join(args.query).strip()
    if not query:
        print("❌ Error: Please provide a search query")
        sys.exit(1)

    # Parse dates
    since_date = None
    until_date = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            print("❌ Invalid --since date. Use YYYY-MM-DD")
            sys.exit(1)
    if args.until:
        try:
            until_date = datetime.strptime(args.until, "%Y-%m-%d")
        except ValueError:
            print("❌ Invalid --until date. Use YYYY-MM-DD")
            sys.exit(1)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.WARNING)

    print(f"\n🚀 Starting Enhanced arXiv Collector...")
    print(f"🔍 Query: '{query}'")
    print(f"📊 Max results: {args.max}")
    if args.download_pdfs:
        print("📥 PDF downloads ENABLED")
    if args.full_text:
        print("📝 Full-text extraction ENABLED")

    collector = ArxivCollector(
        full_text_enabled=args.full_text,
        rate_limit=args.rate_limit,
        pdf_dir="arxiv_pdfs"
    )

    collector.clean_stale_cache()

    papers = collector.search(
        query=query,
        max_results=args.max,
        categories=args.categories,
        since_date=since_date,
        until_date=until_date,
        sort_by=args.sort,
        download_pdfs=args.download_pdfs
    )

    if not papers:
        print("\n❌ No papers found.")
        sys.exit(0)

    print(f"\n✅ Found {len(papers)} papers\n")

    # Display summary in console
    for i, paper in enumerate(papers[:5], 1):  # Show first 5
        print(f"📄 {i}. {paper['title'][:80]}...")
        print(f"   arXiv: {paper['id']} | {paper['primary_category']}")
        print("-" * 80)

    # Exports
    output_file = args.output or f"arxiv_{query.replace(' ', '_')[:50]}.json"
    collector.export_to_json(papers, output_file)

    if args.csv:
        csv_file = output_file.replace('.json', '.csv')
        collector.export_to_csv(papers, csv_file)

    if args.markdown:
        md_file = output_file.replace('.json', '.md')
        collector.export_to_markdown(papers, md_file)

    print(f"\n💾 Results saved to: {output_file}")
    if args.markdown:
        print(f"📝 Markdown summary: {md_file}")
    if args.download_pdfs:
        print(f"📂 PDFs saved to: arxiv_pdfs/")

    # Cache stats
    with sqlite3.connect(collector.cache_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        print(f"🗄️  Cache size: {count} papers")
