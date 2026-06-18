#!/usr/bin/env python3
"""
Production-ready arXiv collector with caching, rate limiting,
rich metadata, optional full-text extraction, and advanced querying.
"""

from typing import List, Dict, Any, Optional
import arxiv
import logging
import hashlib
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
import requests

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ArxivCollector:
    """
    Production-ready arXiv collector with caching, rate limiting,
    rich metadata, optional full-text extraction, and advanced querying.
    """
    def __init__(
        self,
        cache_db: str = "arxiv_cache.db",
        rate_limit: float = 3.0,  # Increased to 3 seconds to avoid rate limiting
        full_text_enabled: bool = False,
        cache_ttl_days: int = 7,
        max_results_cap: int = 1000
    ):
        self.full_text_enabled = full_text_enabled
        self.cache_ttl_days = cache_ttl_days
        self.max_results_cap = max_results_cap

        self.client = arxiv.Client(
            page_size=50,  # Reduced page size
            delay_seconds=max(1, int(1 / rate_limit)) if rate_limit > 0 else 3,
            num_retries=3  # Reduced retries
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
                if row[1]:  # full_text exists
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
        """Build arXiv search query with filters - simplified version."""
        parts = []
        
        # Handle main query
        if query and query.strip():
            parts.append(f"all:{query}")
        
        # Handle categories
        if categories:
            cat_filter = " OR ".join(f"cat:{cat}" for cat in categories)
            parts.append(f"({cat_filter})")
        
        # Handle date filters - simplified to avoid API issues
        if since_date:
            # Use simpler date format
            date_str = since_date.strftime('%Y%m%d')
            parts.append(f"submittedDate:[{date_str} TO 99991231]")
        
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
        """Extract text from PDF using pdfplumber."""
        pdfplumber = self._get_pdfplumber()
        if not pdfplumber:
            return None

        try:
            cache_dir = Path("arxiv_pdf_cache")
            cache_dir.mkdir(exist_ok=True)
            pdf_hash = hashlib.md5(pdf_url.encode()).hexdigest()
            pdf_path = cache_dir / f"{pdf_hash}.pdf"

            if not pdf_path.exists():
                logger.info(f"Downloading PDF: {pdf_url}")
                response = requests.get(pdf_url, stream=True, timeout=30)
                response.raise_for_status()
                with open(pdf_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

            logger.info(f"Extracting text from {pdf_path.name}")
            text_parts = []
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return "\n\n".join(text_parts)
        except Exception as e:
            logger.warning(f"Failed to extract full text from {pdf_url}: {e}")
            return None

    def search(
        self,
        query: str,
        max_results: int = 10,
        categories: Optional[List[str]] = None,
        since_date: Optional[datetime] = None,
        until_date: Optional[datetime] = None,
        sort_by: str = "relevance"
    ) -> List[Dict[str, Any]]:
        """Main search method to retrieve papers from arXiv."""
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
            
            for result in results:
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

            logger.info(f"Retrieved {len(papers)} papers for query: '{query}'")
            return papers
            
        except arxiv.HTTPError as e:
            logger.error(f"HTTP Error for query '{query}': {e}")
            logger.info("Try simplifying your query (remove date filters or categories)")
            return []
        except Exception as e:
            logger.error(f"Error during search for '{query}': {e}", exc_info=True)
            return []

    def batch_search(
        self,
        queries: List[str],
        max_results: int = 10,
        max_workers: int = 2,  # Reduced workers to avoid rate limiting
        **search_kwargs
    ) -> Dict[str, List[Dict]]:
        """Run multiple searches in parallel."""
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_query = {
                executor.submit(self.search, q, max_results, **search_kwargs): q
                for q in queries
            }
            for future in as_completed(future_to_query):
                q = future_to_query[future]
                try:
                    results[q] = future.result()
                except Exception as e:
                    logger.error(f"Batch search failed for '{q}': {e}")
                    results[q] = []
            return results

    def export_to_json(self, papers: List[Dict], output_file: str):
        """Export papers to JSON file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(papers, f, indent=2, default=str)
        logger.info(f"Exported {len(papers)} papers to {output_file}")

    def export_to_csv(self, papers: List[Dict], output_file: str):
        """Export basic metadata to CSV."""
        import csv
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


# ====================== COMMAND-LINE INTERFACE ======================
if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description="arXiv Research Collector - Search and download academic papers",
        epilog="""
Examples:
  python arxiv_1.py "transformer neural networks"
  python arxiv_1.py "machine learning" --max 20 --categories cs.LG cs.AI
  python arxiv_1.py "quantum computing" --since 2025-01-01 --sort submitted
  python arxiv_1.py "llm reasoning" --full-text --max 5
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("query", nargs="*", help="Search query (e.g., 'transformer neural networks')")
    parser.add_argument("--max", "-m", type=int, default=10, help="Maximum results (default: 10)")
    parser.add_argument("--categories", "-c", nargs="+", help="Categories (e.g., cs.AI cs.LG cs.CL)")
    parser.add_argument("--since", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--until", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--sort", choices=["relevance", "submitted", "last_updated"], 
                       default="relevance", help="Sort by (default: relevance)")
    parser.add_argument("--full-text", "-f", action="store_true", help="Extract full text from PDF (SLOW)")
    parser.add_argument("--output", "-o", type=str, help="Output JSON file (default: arxiv_results.json)")
    parser.add_argument("--csv", action="store_true", help="Also export to CSV")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--rate-limit", type=float, default=3.0, help="Rate limit in seconds (default: 3.0)")
    
    args = parser.parse_args()
    
    # Parse the query
    query = " ".join(args.query).strip()
    if not query:
        print("❌ Error: Please provide a search query")
        print("Example: python arxiv_1.py 'machine learning' --max 5")
        sys.exit(1)
    
    # Parse dates if provided
    since_date = None
    until_date = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            print(f"❌ Error: Invalid date format for --since. Use YYYY-MM-DD")
            sys.exit(1)
    if args.until:
        try:
            until_date = datetime.strptime(args.until, "%Y-%m-%d")
        except ValueError:
            print(f"❌ Error: Invalid date format for --until. Use YYYY-MM-DD")
            sys.exit(1)
    
    # Setup logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.WARNING)  # Suppress arXiv logs
    
    # Initialize collector
    print(f"\n🚀 Starting arXiv Collector...")
    print(f"🔍 Query: '{query}'")
    if args.categories:
        print(f"📂 Categories: {', '.join(args.categories)}")
    if since_date:
        print(f"📅 From: {since_date.strftime('%Y-%m-%d')}")
    if until_date:
        print(f"📅 To: {until_date.strftime('%Y-%m-%d')}")
    print(f"📊 Max results: {args.max}")
    print(f"🎯 Sort by: {args.sort}")
    if args.full_text:
        print(f"⚠️  Full-text extraction ENABLED (this will be slow)")
    print()
    
    collector = ArxivCollector(
        full_text_enabled=args.full_text,
        rate_limit=args.rate_limit,
        cache_ttl_days=7,
        max_results_cap=1000
    )
    
    # Clean stale cache
    collector.clean_stale_cache()
    
    # Perform search
    try:
        papers = collector.search(
            query=query,
            max_results=args.max,
            categories=args.categories,
            since_date=since_date,
            until_date=until_date,
            sort_by=args.sort
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Search interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error during search: {e}")
        sys.exit(1)
    
    # Display results
    if not papers:
        print("\n❌ No papers found. Try:")
        print("   - Removing date filters")
        print("   - Using fewer categories")
        print("   - Checking your query spelling")
        sys.exit(0)
    
    print(f"\n✅ Found {len(papers)} papers\n")
    print("=" * 100)
    
    for i, paper in enumerate(papers, 1):
        print(f"\n📄 Paper {i}:")
        print(f"   Title: {paper['title']}")
        
        # Show authors (limit to first 3)
        authors = paper['authors']
        if authors:
            author_names = [a['name'] for a in authors[:3]]
            author_str = ", ".join(author_names)
            if len(authors) > 3:
                author_str += f" and {len(authors) - 3} more"
            print(f"   Authors: {author_str}")
        
        print(f"   arXiv ID: {paper['id']}")
        print(f"   Published: {paper['published'][:10] if paper['published'] else 'N/A'}")
        print(f"   Category: {paper['primary_category']}")
        print(f"   Categories: {', '.join(paper['categories'][:3])}")
        if paper.get('doi'):
            print(f"   DOI: {paper['doi']}")
        
        # Show abstract preview
        abstract = paper['abstract']
        if len(abstract) > 200:
            print(f"   Abstract: {abstract[:200]}...")
        else:
            print(f"   Abstract: {abstract}")
        
        if args.full_text and paper.get('full_text'):
            text_len = len(paper['full_text'])
            print(f"   📝 Full text extracted: {text_len:,} characters")
        
        print("-" * 100)
    
    # Save results
    output_file = args.output or f"arxiv_{query.replace(' ', '_')[:50]}.json"
    collector.export_to_json(papers, output_file)
    
    if args.csv:
        csv_file = output_file.replace('.json', '.csv')
        collector.export_to_csv(papers, csv_file)
    
    print(f"\n💾 Results saved to: {output_file}")
    if args.csv:
        print(f"   CSV saved to: {csv_file}")
    
    # Show summary
    print(f"\n📊 Summary:")
    print(f"   Total papers: {len(papers)}")
    print(f"   Categories found: {', '.join(set(p['primary_category'] for p in papers))}")
    
    # Optional: Show cache stats
    with sqlite3.connect(collector.cache_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        print(f"   Cache size: {count} papers")
