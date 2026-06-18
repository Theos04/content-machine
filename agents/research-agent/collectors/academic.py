#!/usr/bin/env python3
"""
Production Academic Paper Harvester for Termux
Sources: OpenAlex, Semantic Scholar, Internet Archive, CrossRef, CORE
No Wikipedia - dedicated academic sources only
"""

import json
import time
import re
import sys
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote_plus
import hashlib

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("❌ Install requests: pip install requests")
    sys.exit(1)

class AcademicPaper:
    """Academic paper model"""
    def __init__(self, paper_id, title, abstract, authors, source,
                 published_date=None, pdf_url=None, doi=None, url=None,
                 citation_count=None, publisher=None):
        self.id = paper_id
        self.title = title
        self.abstract = abstract[:2000] if abstract else "No abstract available"
        self.authors = authors[:5] if authors else ["Unknown"]
        self.source = source
        self.published_date = published_date
        self.pdf_url = pdf_url
        self.doi = doi
        self.url = url
        self.citation_count = citation_count
        self.publisher = publisher
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'abstract': self.abstract,
            'authors': self.authors,
            'source': self.source,
            'published_date': self.published_date,
            'pdf_url': self.pdf_url,
            'doi': self.doi,
            'url': self.url,
            'citation_count': self.citation_count,
            'publisher': self.publisher
        }

class ProductionAcademicHarvester:
    """Production-ready harvester for academic sources"""
    
    def __init__(self):
        self.session = self._create_session()
        self.results_cache = {}
        
    def _create_session(self):
        """Create session with proper headers and retry logic"""
        session = requests.Session()
        
        # Professional User-Agent to avoid blocking
        session.headers.update({
            'User-Agent': 'AcademicResearchBot/1.0 (Educational Research; mailto:research@institution.edu)',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate'
        })
        
        # Retry strategy for rate limits
        retry_strategy = Retry(
            total=3,
            backoff_factor=3,  # Wait 3, 6, 9 seconds
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=True
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    def _safe_request(self, url, params=None, max_retries=2):
        """Make request with exponential backoff"""
        for attempt in range(max_retries):
            try:
                time.sleep(attempt * 0.5)  # Small delay between retries
                response = self.session.get(url, params=params, timeout=20)
                
                if response.status_code == 429:
                    wait_time = (attempt + 1) * 2
                    print(f"      Rate limited, waiting {wait_time}s...", end='', flush=True)
                    time.sleep(wait_time)
                    continue
                
                return response
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(1)
        return None
    
    # ==================== OPENALEX ====================
    def search_openalex(self, query: str, max_results: int = 25) -> List[AcademicPaper]:
        """Search OpenAlex - Best general academic database"""
        papers = []
        
        # Enhance query for historical research
        enhanced_query = f"{query} history OR historical OR flood OR coastal"
        encoded_query = quote_plus(enhanced_query)
        url = f"https://api.openalex.org/works"
        
        params = {
            "search": enhanced_query,
            "per-page": min(max_results, 25),
            "sort": "relevance_score:desc",
            "filter": "type:article|book|dissertation"
        }
        
        try:
            print(f"  📚 OpenAlex: Searching...", end='', flush=True)
            response = self._safe_request(url, params)
            
            if response and response.status_code == 200:
                data = response.json()
                
                for work in data.get('results', []):
                    # Extract PDF URL
                    pdf_url = None
                    if work.get('open_access', {}).get('oa_url'):
                        pdf_url = work['open_access']['oa_url']
                    
                    # Extract authors
                    authors = []
                    for auth in work.get('authorships', [])[:5]:
                        if auth.get('author', {}).get('display_name'):
                            authors.append(auth['author']['display_name'])
                    
                    # Extract abstract
                    abstract = work.get('abstract', '')
                    if abstract:
                        # Remove HTML tags
                        abstract = re.sub('<[^<]+?>', '', abstract)
                    
                    # Check relevance to historical floods
                    title_lower = work.get('title', '').lower()
                    is_relevant = any(term in title_lower for term in ['flood', 'bristol', '1607', 'severn', 'tsunami', 'storm surge'])
                    
                    paper = AcademicPaper(
                        paper_id=work['id'].split('/')[-1],
                        title=work.get('title', 'No title'),
                        abstract=abstract or 'No abstract available',
                        authors=authors if authors else ["Unknown"],
                        source="OpenAlex",
                        published_date=work.get('publication_date', '')[:10],
                        pdf_url=pdf_url,
                        doi=work.get('doi'),
                        url=work.get('id'),
                        citation_count=work.get('cited_by_count', 0),
                        publisher=work.get('host_venue', {}).get('display_name') if work.get('host_venue') else None
                    )
                    
                    # Boost relevance score by putting relevant papers first
                    if is_relevant:
                        papers.insert(0, paper)
                    else:
                        papers.append(paper)
                    
                    if len(papers) >= max_results:
                        break
                
                print(f" ✓ {len(papers)} found")
            else:
                print(f" ✗ Service unavailable")
        except Exception as e:
            print(f" ✗ Error: {str(e)[:40]}")
        
        return papers
    
    # ==================== SEMANTIC SCHOLAR ====================
    def search_semantic_scholar(self, query: str, max_results: int = 25) -> List[AcademicPaper]:
        """Search Semantic Scholar - AI-powered academic search"""
        papers = []
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        
        params = {
            "query": query,
            "limit": min(max_results, 50),
            "fields": "title,abstract,authors,year,openAccessPdf,url,doi,citationCount,venue"
        }
        
        try:
            print(f"  🔬 Semantic Scholar: Searching...", end='', flush=True)
            response = self._safe_request(url, params)
            
            if response and response.status_code == 200:
                data = response.json()
                
                for paper_data in data.get('data', [])[:max_results]:
                    # Extract authors
                    authors = []
                    for author in paper_data.get('authors', [])[:5]:
                        if author.get('name'):
                            authors.append(author['name'])
                    
                    # Extract PDF URL
                    pdf_url = None
                    if paper_data.get('openAccessPdf'):
                        pdf_url = paper_data['openAccessPdf'].get('url')
                    
                    paper = AcademicPaper(
                        paper_id=paper_data.get('paperId', ''),
                        title=paper_data.get('title', 'No title'),
                        abstract=paper_data.get('abstract') or 'No abstract available',
                        authors=authors if authors else ["Unknown"],
                        source="Semantic Scholar",
                        published_date=str(paper_data.get('year', '')) if paper_data.get('year') else '',
                        pdf_url=pdf_url,
                        doi=paper_data.get('doi'),
                        url=paper_data.get('url'),
                        citation_count=paper_data.get('citationCount', 0),
                        publisher=paper_data.get('venue')
                    )
                    papers.append(paper)
                
                print(f" ✓ {len(papers)} found")
            elif response and response.status_code == 429:
                print(f" ⚠️ Rate limited, try again later")
            else:
                print(f" ✗ Error {response.status_code if response else 'No response'}")
        except Exception as e:
            print(f" ✗ Error: {str(e)[:40]}")
        
        return papers
    
    # ==================== INTERNET ARCHIVE ====================
    def search_internet_archive(self, query: str, max_results: int = 20) -> List[AcademicPaper]:
        """Search Internet Archive - Historical books and documents"""
        papers = []
        url = "https://archive.org/advancedsearch.php"
        
        # Focus on historical texts
        enhanced_query = f"({query}) AND (history OR flood OR bristol OR severn)"
        
        params = {
            "q": enhanced_query,
            "fl": "identifier,title,creator,description,date,publisher,language",
            "rows": max_results,
            "page": 1,
            "output": "json",
            "sort": "downloads desc"
        }
        
        try:
            print(f"  📖 Internet Archive: Searching...", end='', flush=True)
            response = self._safe_request(url, params)
            
            if response and response.status_code == 200:
                data = response.json()
                docs = data.get('response', {}).get('docs', [])
                
                for doc in docs[:max_results]:
                    # Extract title
                    title = doc.get('title', 'No title')
                    if isinstance(title, list):
                        title = title[0] if title else 'No title'
                    
                    # Extract creator
                    creator = doc.get('creator', 'Unknown')
                    if isinstance(creator, list):
                        creator = creator[0] if creator else 'Unknown'
                    
                    # Extract description
                    description = doc.get('description', '')
                    if isinstance(description, list):
                        description = description[0] if description else ''
                    
                    # Extract publisher
                    publisher = doc.get('publisher', '')
                    if isinstance(publisher, list):
                        publisher = publisher[0] if publisher else ''
                    
                    paper = AcademicPaper(
                        paper_id=doc.get('identifier', ''),
                        title=title[:200],
                        abstract=description[:1000] if description else f"Historical document about {query}",
                        authors=[creator],
                        source="Internet Archive",
                        published_date=str(doc.get('date', ''))[:10] if doc.get('date') else '',
                        url=f"https://archive.org/details/{doc.get('identifier', '')}",
                        publisher=publisher
                    )
                    papers.append(paper)
                
                print(f" ✓ {len(papers)} found")
            else:
                print(f" ✗ Service error")
        except Exception as e:
            print(f" ✗ Error: {str(e)[:40]}")
        
        return papers
    
    # ==================== CROSSREF ====================
    def search_crossref(self, query: str, max_results: int = 20) -> List[AcademicPaper]:
        """Search CrossRef - DOI registration agency"""
        papers = []
        url = "https://api.crossref.org/works"
        
        params = {
            "query": query,
            "rows": min(max_results, 20),
            "sort": "relevance",
            "select": "DOI,title,abstract,author,issued,URL,reference-count"
        }
        
        try:
            print(f"  🔗 CrossRef: Searching...", end='', flush=True)
            response = self._safe_request(url, params)
            
            if response and response.status_code == 200:
                data = response.json()
                items = data.get('message', {}).get('items', [])
                
                for item in items[:max_results]:
                    # Extract authors
                    authors = []
                    for author in item.get('author', [])[:5]:
                        name_parts = []
                        if author.get('given'):
                            name_parts.append(author['given'])
                        if author.get('family'):
                            name_parts.append(author['family'])
                        if name_parts:
                            authors.append(' '.join(name_parts))
                    
                    # Extract date
                    published_date = ''
                    if item.get('issued', {}).get('date-parts'):
                        date_parts = item['issued']['date-parts'][0]
                        published_date = '-'.join(str(p) for p in date_parts[:3])
                    
                    paper = AcademicPaper(
                        paper_id=item.get('DOI', ''),
                        title=item.get('title', ['No title'])[0],
                        abstract=item.get('abstract', 'No abstract available')[:1000],
                        authors=authors if authors else ["Unknown"],
                        source="CrossRef",
                        published_date=published_date,
                        doi=item.get('DOI'),
                        url=f"https://doi.org/{item.get('DOI')}" if item.get('DOI') else None,
                        citation_count=item.get('reference-count', 0)
                    )
                    papers.append(paper)
                
                print(f" ✓ {len(papers)} found")
            else:
                print(f" ✗ Error {response.status_code if response else 'No response'}")
        except Exception as e:
            print(f" ✗ Error: {str(e)[:40]}")
        
        return papers
    
    # ==================== CORE ACADEMIC ====================
    def search_core(self, query: str, max_results: int = 15) -> List[AcademicPaper]:
        """Search CORE - Open access aggregator"""
        papers = []
        url = "https://core.ac.uk/api/v3/search/works"
        
        # Note: CORE allows anonymous requests but with lower limits
        params = {
            "q": query,
            "limit": min(max_results, 15),
            "page": 1
        }
        
        try:
            print(f"  📦 CORE: Searching...", end='', flush=True)
            response = self._safe_request(url, params)
            
            if response and response.status_code == 200:
                data = response.json()
                
                for item in data.get('data', [])[:max_results]:
                    # Extract authors
                    authors = []
                    for author in item.get('authors', [])[:5]:
                        if isinstance(author, dict):
                            authors.append(author.get('name', ''))
                        elif isinstance(author, str):
                            authors.append(author)
                    
                    paper = AcademicPaper(
                        paper_id=str(item.get('id', '')),
                        title=item.get('title', 'No title'),
                        abstract=item.get('abstract', 'No abstract available')[:1000],
                        authors=authors if authors else ["Unknown"],
                        source="CORE",
                        published_date=str(item.get('year', '')) if item.get('year') else '',
                        pdf_url=item.get('downloadUrl'),
                        doi=item.get('doi'),
                        url=item.get('url'),
                        publisher=item.get('publisher')
                    )
                    papers.append(paper)
                
                print(f" ✓ {len(papers)} found")
            elif response and response.status_code == 403:
                print(f" ⚠️ Access limited (no API key)")
            else:
                print(f" ✗ Error {response.status_code if response else 'No response'}")
        except Exception as e:
            print(f" ✗ Error: {str(e)[:40]}")
        
        return papers
    
    # ==================== UNIFIED SEARCH ====================
    def search(self, query: str, sources: List[str] = None, max_per_source: int = 20) -> List[AcademicPaper]:
        """Search across multiple academic sources"""
        
        if sources is None:
            sources = ["openalex", "semantic_scholar", "internet_archive", "crossref", "core"]
        
        source_map = {
            "openalex": self.search_openalex,
            "semantic_scholar": self.search_semantic_scholar,
            "internet_archive": self.search_internet_archive,
            "crossref": self.search_crossref,
            "core": self.search_core
        }
        
        print(f"\n🔍 Academic Search: '{query}'\n")
        print("=" * 50)
        
        all_papers = []
        selected_sources = [s for s in sources if s in source_map]
        
        for source in selected_sources:
            papers = source_map[source](query, max_per_source)
            all_papers.extend(papers)
            time.sleep(1)  # Be respectful to APIs
        
        # Deduplicate by DOI or title
        seen = set()
        unique_papers = []
        for paper in all_papers:
            key = paper.doi if paper.doi else paper.title.lower()[:100]
            if key not in seen:
                seen.add(key)
                unique_papers.append(paper)
        
        # Sort by citation count (if available)
        unique_papers.sort(key=lambda x: x.citation_count or 0, reverse=True)
        
        return unique_papers
    
    # ==================== EXPORT ====================
    def export_json(self, papers: List[AcademicPaper], filename: str):
        """Export to JSON"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump([p.to_dict() for p in papers], f, indent=2, ensure_ascii=False)
        print(f"\n💾 JSON exported: {filename}")
    
    def export_markdown(self, papers: List[AcademicPaper], filename: str, query: str):
        """Export to Markdown with proper academic formatting"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Academic Research Results\n\n")
            f.write(f"**Query:** {query}\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Total papers:** {len(papers)}\n\n")
            f.write("---\n\n")
            
            # Group by source
            by_source = {}
            for paper in papers:
                if paper.source not in by_source:
                    by_source[paper.source] = []
                by_source[paper.source].append(paper)
            
            for source, source_papers in by_source.items():
                f.write(f"## {source} ({len(source_papers)} papers)\n\n")
                
                for i, paper in enumerate(source_papers, 1):
                    f.write(f"### {i}. {paper.title}\n\n")
                    
                    f.write(f"- **Authors:** {', '.join(paper.authors)}\n")
                    if paper.published_date:
                        f.write(f"- **Year:** {paper.published_date}\n")
                    if paper.citation_count:
                        f.write(f"- **Citations:** {paper.citation_count}\n")
                    if paper.publisher:
                        f.write(f"- **Publisher:** {paper.publisher}\n")
                    if paper.doi:
                        f.write(f"- **DOI:** `{paper.doi}`\n")
                    if paper.url:
                        f.write(f"- **URL:** {paper.url}\n")
                    if paper.pdf_url:
                        f.write(f"- **PDF:** {paper.pdf_url}\n")
                    
                    f.write(f"\n**Abstract:**\n{paper.abstract}\n\n")
                    f.write("---\n\n")
        
        print(f"📝 Markdown exported: {filename}")

# ==================== MAIN ====================
def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Production Academic Paper Harvester",
        epilog="Example: python academic_harvester.py 'Bristol Channel floods 1607' --max 30 --markdown"
    )
    
    parser.add_argument("query", help="Search query")
    parser.add_argument("--sources", "-s", nargs="+", 
                        default=["openalex", "semantic_scholar", "internet_archive", "crossref"],
                        choices=["openalex", "semantic_scholar", "internet_archive", "crossref", "core"],
                        help="Academic sources to search")
    parser.add_argument("--max", "-m", type=int, default=25, help="Max results per source")
    parser.add_argument("--output", "-o", type=str, help="Output file base name")
    parser.add_argument("--markdown", "-md", action="store_true", help="Export as Markdown")
    parser.add_argument("--json", action="store_true", help="Export as JSON")
    
    args = parser.parse_args()
    
    # Initialize harvester
    harvester = ProductionAcademicHarvester()
    
    # Search
    papers = harvester.search(args.query, args.sources, args.max)
    
    if not papers:
        print("\n❌ No academic papers found. Try different search terms.")
        sys.exit(1)
    
    # Display summary
    print("\n" + "=" * 50)
    print(f"✅ TOTAL: {len(papers)} academic papers found\n")
    
    print("📊 TOP RESULTS BY CITATIONS:\n")
    for i, paper in enumerate(papers[:10], 1):
        citation_info = f" [{paper.citation_count} citations]" if paper.citation_count else ""
        print(f"{i}. {citation_info} [{paper.source}] {paper.title[:90]}")
        print(f"   Authors: {', '.join(paper.authors[:3])}")
        if paper.published_date:
            print(f"   Year: {paper.published_date}")
        print()
    
    # Export
    output_base = args.output or f"academic_{args.query.replace(' ', '_')[:40].replace('/', '_')}"
    
    if args.json:
        harvester.export_json(papers, f"{output_base}.json")
    
    if args.markdown or (not args.json):
        harvester.export_markdown(papers, f"{output_base}.md", args.query)
    
    print(f"\n✨ Research complete! Found {len(papers)} academic papers")

if __name__ == "__main__":
    main()
