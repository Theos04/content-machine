#!/usr/bin/env python3
"""
Academic Paper Harvester - RELIABLE SOURCES ONLY
Focuses on sources with proven working APIs
"""

import json
import time
import re
import sys
from datetime import datetime
from typing import List
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("❌ Install requests: pip install requests")
    sys.exit(1)

class AcademicPaper:
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

class AcademicHarvester:
    def __init__(self, max_workers: int = 8):
        self.max_workers = max_workers
        self.session = self._create_session()
        self.print_lock = threading.Lock()
        self.results_lock = threading.Lock()
        self.all_papers = []

    def _create_session(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; AcademicBot/1.0)',
            'Accept': 'application/json',
        })
        retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _safe_print(self, msg, end='\n'):
        with self.print_lock:
            print(msg, end=end, flush=True)

    def _add_papers(self, papers):
        with self.results_lock:
            self.all_papers.extend(papers)

    def _safe_request(self, url, params=None, timeout=15):
        try:
            return self.session.get(url, params=params, timeout=timeout)
        except:
            return None

    # ==================== RELIABLE SOURCES ====================
    
    def search_openalex(self, query: str, max_results: int = 25) -> List[AcademicPaper]:
        """OpenAlex - Most reliable, largest database"""
        papers = []
        url = "https://api.openalex.org/works"
        
        params = {
            "search": query,
            "per-page": min(max_results, 25),
            "sort": "cited_by_count:desc",
        }

        try:
            self._safe_print(f"  📚 OpenAlex: Searching...", end='')
            response = self._safe_request(url, params)

            if response and response.status_code == 200:
                data = response.json()
                for work in data.get('results', []):
                    authors = [a.get('author', {}).get('display_name', '') for a in work.get('authorships', [])[:5]]
                    authors = [a for a in authors if a]
                    
                    abstract = work.get('abstract', '')
                    if abstract:
                        abstract = re.sub('<[^<]+?>', '', abstract)

                    paper = AcademicPaper(
                        paper_id=work.get('id', '').split('/')[-1],
                        title=work.get('title', 'No title'),
                        abstract=abstract or 'No abstract available',
                        authors=authors or ["Unknown"],
                        source="OpenAlex",
                        published_date=work.get('publication_date', '')[:10],
                        doi=work.get('doi'),
                        url=work.get('id'),
                        citation_count=work.get('cited_by_count', 0),
                        publisher=work.get('host_venue', {}).get('display_name') if work.get('host_venue') else None
                    )
                    papers.append(paper)
                    if len(papers) >= max_results:
                        break
                self._safe_print(f" ✓ {len(papers)} found")
            else:
                self._safe_print(f" ✗ No response")
        except Exception as e:
            self._safe_print(f" ✗ Error")
        return papers

    def search_semantic_scholar(self, query: str, max_results: int = 25) -> List[AcademicPaper]:
        """Semantic Scholar - Best for citations and AI"""
        papers = []
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        
        params = {
            "query": query,
            "limit": min(max_results, 50),
            "fields": "title,abstract,authors,year,openAccessPdf,url,doi,citationCount,venue"
        }

        try:
            self._safe_print(f"  🔬 Semantic Scholar: Searching...", end='')
            response = self._safe_request(url, params)

            if response and response.status_code == 200:
                data = response.json()
                for p in data.get('data', [])[:max_results]:
                    authors = [a.get('name', '') for a in p.get('authors', [])[:5]]
                    authors = [a for a in authors if a]
                    
                    pdf_url = p.get('openAccessPdf', {}).get('url') if p.get('openAccessPdf') else None

                    paper = AcademicPaper(
                        paper_id=p.get('paperId', ''),
                        title=p.get('title', 'No title'),
                        abstract=p.get('abstract') or 'No abstract available',
                        authors=authors or ["Unknown"],
                        source="Semantic Scholar",
                        published_date=str(p.get('year', '')) if p.get('year') else '',
                        pdf_url=pdf_url,
                        doi=p.get('doi'),
                        url=p.get('url'),
                        citation_count=p.get('citationCount', 0),
                        publisher=p.get('venue')
                    )
                    papers.append(paper)
                self._safe_print(f" ✓ {len(papers)} found")
            else:
                self._safe_print(f" ✗ No response")
        except Exception as e:
            self._safe_print(f" ✗ Error")
        return papers

    def search_crossref(self, query: str, max_results: int = 20) -> List[AcademicPaper]:
        """CrossRef - DOI registry, good for exact matches"""
        papers = []
        url = "https://api.crossref.org/works"
        
        params = {
            "query": query,
            "rows": min(max_results, 20),
            "sort": "relevance",
        }

        try:
            self._safe_print(f"  🔗 CrossRef: Searching...", end='')
            response = self._safe_request(url, params)

            if response and response.status_code == 200:
                data = response.json()
                for item in data.get('message', {}).get('items', []):
                    authors = []
                    for author in item.get('author', [])[:5]:
                        name = []
                        if author.get('given'):
                            name.append(author['given'])
                        if author.get('family'):
                            name.append(author['family'])
                        if name:
                            authors.append(' '.join(name))

                    date = ''
                    if item.get('issued', {}).get('date-parts'):
                        date = '-'.join(str(p) for p in item['issued']['date-parts'][0][:3])

                    paper = AcademicPaper(
                        paper_id=item.get('DOI', ''),
                        title=item.get('title', ['No title'])[0],
                        abstract=item.get('abstract', 'No abstract available')[:1000],
                        authors=authors or ["Unknown"],
                        source="CrossRef",
                        published_date=date,
                        doi=item.get('DOI'),
                        url=f"https://doi.org/{item.get('DOI')}" if item.get('DOI') else None,
                        citation_count=item.get('reference-count', 0)
                    )
                    papers.append(paper)
                    if len(papers) >= max_results:
                        break
                self._safe_print(f" ✓ {len(papers)} found")
            else:
                self._safe_print(f" ✗ No response")
        except Exception as e:
            self._safe_print(f" ✗ Error")
        return papers

    def search_arxiv(self, query: str, max_results: int = 20) -> List[AcademicPaper]:
        """arXiv - Preprints, very reliable"""
        papers = []
        url = "http://export.arxiv.org/api/query"
        
        params = {
            "search_query": f"all:{query}",
            "max_results": min(max_results, 20),
            "sortBy": "relevance"
        }

        try:
            self._safe_print(f"  📄 arXiv: Searching...", end='')
            response = self._safe_request(url, params, timeout=10)

            if response and response.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.content)
                
                for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                    title = entry.find('{http://www.w3.org/2005/Atom}title')
                    summary = entry.find('{http://www.w3.org/2005/Atom}summary')
                    
                    authors = []
                    for author in entry.findall('{http://www.w3.org/2005/Atom}author'):
                        name = author.find('{http://www.w3.org/2005/Atom}name')
                        if name is not None:
                            authors.append(name.text)
                    
                    pub_date = entry.find('{http://www.w3.org/2005/Atom}published')
                    
                    paper = AcademicPaper(
                        paper_id=entry.find('{http://www.w3.org/2005/Atom}id').text.split('/')[-1] if entry.find('{http://www.w3.org/2005/Atom}id') else '',
                        title=title.text if title is not None else 'No title',
                        abstract=summary.text[:1000] if summary is not None else 'No abstract',
                        authors=authors[:5] or ["Unknown"],
                        source="arXiv",
                        published_date=pub_date.text[:10] if pub_date is not None else '',
                        url=entry.find('{http://www.w3.org/2005/Atom}id').text if entry.find('{http://www.w3.org/2005/Atom}id') else None
                    )
                    papers.append(paper)
                self._safe_print(f" ✓ {len(papers)} found")
            else:
                self._safe_print(f" ✗ No response")
        except Exception as e:
            self._safe_print(f" ✗ Error")
        return papers

    def search_pubmed(self, query: str, max_results: int = 15) -> List[AcademicPaper]:
        """PubMed - Biomedical literature"""
        papers = []
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": min(max_results, 15),
            "retmode": "json"
        }

        try:
            self._safe_print(f"  🏥 PubMed: Searching...", end='')
            response = self._safe_request(url, params)

            if response and response.status_code == 200:
                data = response.json()
                ids = data.get('esearchresult', {}).get('idlist', [])
                
                if ids:
                    # Fetch details
                    fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                    fetch_params = {
                        "db": "pubmed",
                        "id": ",".join(ids[:10]),
                        "retmode": "json"
                    }
                    fetch_response = self._safe_request(fetch_url, fetch_params)
                    
                    if fetch_response and fetch_response.status_code == 200:
                        fetch_data = fetch_response.json()
                        for uid, info in fetch_data.get('result', {}).items():
                            if uid == 'uids':
                                continue
                            authors = info.get('authors', [])
                            author_names = [a.get('name', '') for a in authors[:5] if a.get('name')]
                            
                            paper = AcademicPaper(
                                paper_id=uid,
                                title=info.get('title', 'No title'),
                                abstract=info.get('abstract', 'No abstract available')[:1000],
                                authors=author_names or ["Unknown"],
                                source="PubMed",
                                published_date=info.get('pubdate', '')[:10],
                                url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"
                            )
                            papers.append(paper)
                self._safe_print(f" ✓ {len(papers)} found")
            else:
                self._safe_print(f" ✗ No response")
        except Exception as e:
            self._safe_print(f" ✗ Error")
        return papers

    # ==================== SEARCH ====================
    def search(self, query: str, sources: List[str] = None, max_per_source: int = 20) -> List[AcademicPaper]:
        """Search in parallel"""
        
        if sources is None:
            sources = ["openalex", "semantic_scholar", "crossref", "arxiv", "pubmed"]

        source_map = {
            "openalex": self.search_openalex,
            "semantic_scholar": self.search_semantic_scholar,
            "crossref": self.search_crossref,
            "arxiv": self.search_arxiv,
            "pubmed": self.search_pubmed,
        }

        print(f"\n🔍 Academic Search: '{query}'")
        print("=" * 60)
        print(f"🚀 Searching {len(sources)} sources in parallel...\n")

        self.all_papers = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(search_func, query, max_per_source): name
                for name, search_func in source_map.items() 
                if name in sources
            }

            for future in as_completed(futures):
                try:
                    papers = future.result(timeout=30)
                    if papers:
                        self._add_papers(papers)
                except Exception as e:
                    self._safe_print(f"  ❌ {futures[future]}: Timeout")

        # Deduplicate
        seen = set()
        unique = []
        for p in self.all_papers:
            key = p.doi if p.doi else p.title.lower()[:100]
            if key not in seen:
                seen.add(key)
                unique.append(p)

        unique.sort(key=lambda x: x.citation_count or 0, reverse=True)
        return unique

    # ==================== EXPORT ====================
    def export_json(self, papers: List[AcademicPaper], filename: str):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump([p.to_dict() for p in papers], f, indent=2, ensure_ascii=False)
        print(f"\n💾 JSON: {filename}")

    def export_markdown(self, papers: List[AcademicPaper], filename: str, query: str):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Academic Research: {query}\n\n")
            f.write(f"**Total papers:** {len(papers)}\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")

            for i, p in enumerate(papers, 1):
                f.write(f"## {i}. {p.title}\n\n")
                f.write(f"- **Authors:** {', '.join(p.authors)}\n")
                if p.published_date:
                    f.write(f"- **Year:** {p.published_date}\n")
                if p.citation_count:
                    f.write(f"- **Citations:** {p.citation_count}\n")
                if p.source:
                    f.write(f"- **Source:** {p.source}\n")
                if p.doi:
                    f.write(f"- **DOI:** `{p.doi}`\n")
                if p.url:
                    f.write(f"- **URL:** {p.url}\n")
                if p.pdf_url:
                    f.write(f"- **PDF:** {p.pdf_url}\n")
                f.write(f"\n**Abstract:**\n{p.abstract}\n\n")
                f.write("---\n\n")

        print(f"📝 Markdown: {filename}")

# ==================== MAIN ====================
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Academic Paper Harvester")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--sources", "-s", nargs="+",
                        default=["openalex", "semantic_scholar"],
                        choices=["openalex", "semantic_scholar", "crossref", "arxiv", "pubmed"],
                        help="Sources to search")
    parser.add_argument("--max", "-m", type=int, default=20, help="Max per source")
    parser.add_argument("--workers", "-w", type=int, default=8, help="Parallel workers")
    parser.add_argument("--output", "-o", type=str, help="Output file name")
    parser.add_argument("--markdown", "-md", action="store_true", help="Export Markdown")
    parser.add_argument("--json", action="store_true", help="Export JSON")

    args = parser.parse_args()

    harvester = AcademicHarvester(max_workers=args.workers)
    
    start = time.time()
    papers = harvester.search(args.query, args.sources, args.max)
    elapsed = time.time() - start

    if not papers:
        print("\n❌ No papers found")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"✅ Found {len(papers)} papers in {elapsed:.1f}s\n")

    print("📊 Top Results:\n")
    for i, p in enumerate(papers[:10], 1):
        citation = f" [{p.citation_count} citations]" if p.citation_count else ""
        print(f"{i}. {citation} [{p.source}] {p.title[:80]}")
        print(f"   Authors: {', '.join(p.authors[:3])}")
        if p.published_date:
            print(f"   Year: {p.published_date}")
        print()

    base = args.output or f"academic_{args.query.replace(' ', '_')[:30]}"
    
    if args.json:
        harvester.export_json(papers, f"{base}.json")
    if args.markdown or (not args.json and not args.markdown):
        harvester.export_markdown(papers, f"{base}.md", args.query)

    print(f"\n✨ Complete in {elapsed:.1f}s")

if __name__ == "__main__":
    main()
