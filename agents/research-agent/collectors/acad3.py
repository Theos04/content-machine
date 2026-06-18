# semanticscholar_scraper.py
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
import subprocess
import os
import time
import json
import requests
import websocket
from urllib.parse import quote
import signal
import atexit
import shutil
from datetime import datetime
import sys
import re

console = Console()

# Configuration
CHROME_PORT = 9222
chrome_process = None

def cleanup():
    global chrome_process
    if chrome_process:
        try:
            chrome_process.terminate()
        except Exception:
            pass

atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda sig, frame: (cleanup(), exit(0)))

def find_chrome():
    """Find Chrome/Chromium binary."""
    candidates = [
        "chromium-browser", "chromium", "google-chrome",
        "google-chrome-stable", "brave-browser"
    ]
    for name in candidates:
        path = shutil.which(name)
        if path:
            console.print(f"[green]✓ Found browser: {path}[/green]")
            return path
    console.print("[red]No Chrome/Chromium binary found![/red]")
    console.print("[yellow]Install with: pkg install chromium[/yellow]")
    return None

def is_cdp_alive(port=CHROME_PORT):
    """Check if Chrome's debugging port is responding."""
    try:
        requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
        return True
    except Exception:
        return False

def start_chrome_headless():
    """Launch Chrome in headless mode with CDP."""
    global chrome_process
    
    # Kill any existing Chrome instances on our port
    subprocess.run(["pkill", "-f", f"remote-debugging-port={CHROME_PORT}"], capture_output=True)
    time.sleep(1)
    
    chrome_cmd = find_chrome()
    if not chrome_cmd:
        return False
    
    user_data_dir = os.path.expanduser('~/chrome-cdp-semantic')
    os.makedirs(user_data_dir, exist_ok=True)
    
    cmd = [
        chrome_cmd,
        f"--remote-debugging-port={CHROME_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
        "--headless=new",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-blink-features=AutomationControlled",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    
    try:
        console.print("[cyan]Launching Chrome in headless mode...[/cyan]")
        chrome_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        for i in range(30):
            time.sleep(1)
            if is_cdp_alive():
                console.print(f"[green]✓ Chrome ready (headless, {i+1}s)[/green]")
                return True
            if chrome_process.poll() is not None:
                rc = chrome_process.returncode
                console.print(f"[red]Chrome crashed (exit code {rc})[/red]")
                break
                
    except Exception as e:
        console.print(f"[red]Headless launch error: {e}[/red]")
    
    console.print("[red]Failed to start Chrome[/red]")
    return False

def get_ws_url():
    try:
        tabs = requests.get(f"http://127.0.0.1:{CHROME_PORT}/json/list", timeout=5).json()
        if tabs:
            return tabs[0].get("webSocketDebuggerUrl")
    except Exception as e:
        console.print(f"[yellow]Could not get WebSocket URL: {e}[/yellow]")
    return None

def connect_cdp():
    ws_url = get_ws_url()
    if not ws_url:
        return None
    
    console.print("[cyan]Connecting to Chrome CDP...[/cyan]")
    ws = websocket.create_connection(ws_url, timeout=30)
    
    for method in ["Page.enable", "Runtime.enable", "Network.enable"]:
        ws.send(json.dumps({"id": 1, "method": method}))
        time.sleep(0.3)
    
    ws.settimeout(0.1)
    while True:
        try:
            ws.recv()
        except:
            break
    ws.settimeout(None)
    
    return ws

def send_cdp(ws, _id, method, params=None):
    ws.send(json.dumps({"id": _id, "method": method, "params": params or {}}))

def recv_cdp(ws, expected_id=None):
    while True:
        try:
            res = json.loads(ws.recv())
            if "id" in res and (expected_id is None or res["id"] == expected_id):
                return res
        except Exception:
            continue

def evaluate_cdp(ws, expression, _id=100):
    send_cdp(ws, _id, "Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": True
    })
    result = recv_cdp(ws, _id)
    if "result" in result and "result" in result["result"]:
        return result["result"]["result"].get("value")
    return None

def navigate_cdp(ws, url):
    console.print(f"[cyan]Navigating to: {url}[/cyan]")
    send_cdp(ws, 1000, "Page.navigate", {"url": url})
    time.sleep(3)
    
    for attempt in range(20):
        content = evaluate_cdp(ws, """
        (function() {
            const results = document.querySelectorAll('.paper-card, .search-result, [data-test-id="paper-card"]');
            if (results.length > 0) return 'results';
            
            const loading = document.querySelector('.loading-controls, [data-test-id="icon-loading-serp"]');
            if (loading) return 'loading';
            
            const body = document.body.innerText;
            if (body && body.length > 100) return 'content';
            
            return 'empty';
        })()
        """)
        
        if content == 'results':
            console.print("[green]✓ Results found![/green]")
            return True
        elif content == 'loading':
            console.print(f"[dim]Still loading... ({attempt+1}/20)[/dim]")
            time.sleep(1)
        elif content == 'content':
            console.print("[yellow]Page has content but no results?[/yellow]")
            time.sleep(1)
        else:
            console.print(f"[dim]Waiting for content... ({attempt+1}/20)[/dim]")
            time.sleep(1)
    
    console.print("[yellow]Page may not have loaded fully[/yellow]")
    return True

def scrape_semantic_scholar(query, max_results=50, retries=3):
    """Scrape paper data from Semantic Scholar search results."""
    ws = None
    results = []
    
    try:
        if not is_cdp_alive():
            if not start_chrome_headless():
                console.print("[red]Could not start Chrome[/red]")
                return []
        
        ws = connect_cdp()
        if not ws:
            console.print("[red]Could not connect to CDP[/red]")
            return []
        
        search_url = f"https://www.semanticscholar.org/search?q={quote(query)}"
        if not navigate_cdp(ws, search_url):
            console.print("[red]Navigation failed[/red]")
            return []
        
        time.sleep(2)
        
        console.print("[cyan]Extracting paper data...[/cyan]")
        
        # Improved extraction with duplicate handling
        paper_data = evaluate_cdp(ws, f"""
        (function() {{
            const results = [];
            const maxResults = {max_results};
            const seen = new Set();
            
            // Find all paper links
            const links = document.querySelectorAll('a[href^="/paper/"]');
            
            for (let i = 0; i < links.length && results.length < maxResults; i++) {{
                const link = links[i];
                const href = link.href;
                
                // Skip citation/reference links
                if (href.includes('#citing-papers') || href.includes('#references')) {{
                    continue;
                }}
                
                // Get the parent card/container
                let card = link.closest('.paper-card, .search-result, [data-test-id="paper-card"], .result-item, .paper-row, article');
                if (!card) {{
                    card = link;
                }}
                
                // Extract paper ID
                let paperId = '';
                const parts = href.split('/paper/');
                if (parts.length > 1) {{
                    paperId = parts[1].split('?')[0] || '';
                }}
                
                // Skip duplicates
                if (seen.has(paperId)) continue;
                seen.add(paperId);
                
                // Get title
                const title = link.textContent.trim() || 'Unknown title';
                
                // Get authors
                let authors = '';
                const authorsSelectors = ['.authors', '.author-list', '[data-test-id="authors"]', '.authors-list'];
                for (let s = 0; s < authorsSelectors.length; s++) {{
                    const el = card.querySelector(authorsSelectors[s]);
                    if (el) {{
                        authors = el.textContent.trim();
                        break;
                    }}
                }}
                
                // Get abstract
                let abstract = '';
                const abstractSelectors = ['.abstract', '.paper-abstract', '[data-test-id="abstract"]', '.abstract-text'];
                for (let s = 0; s < abstractSelectors.length; s++) {{
                    const el = card.querySelector(abstractSelectors[s]);
                    if (el) {{
                        abstract = el.textContent.trim().substring(0, 500);
                        break;
                    }}
                }}
                
                // Get citations
                let citations = '';
                const citSelectors = ['.citations', '[data-test-id="citation-count"]', '.citation-count', '.cited-by'];
                for (let s = 0; s < citSelectors.length; s++) {{
                    const el = card.querySelector(citSelectors[s]);
                    if (el) {{
                        citations = el.textContent.trim().replace(/Citations?/i, '').trim();
                        break;
                    }}
                }}
                
                // Fallback: search text for citation pattern
                if (!citations) {{
                    const text = card.textContent || '';
                    const match = text.match(/(\\d+)\\s*[Cc]itations?/);
                    if (match) {{
                        citations = match[1];
                    }}
                }}
                
                // Get year
                let year = '';
                const yearSelectors = ['.year', '.publication-date', '[data-test-id="year"]', '.pub-year', '.date'];
                for (let s = 0; s < yearSelectors.length; s++) {{
                    const el = card.querySelector(yearSelectors[s]);
                    if (el) {{
                        year = el.textContent.trim();
                        break;
                    }}
                }}
                
                // Fallback: search for 4-digit year
                if (!year) {{
                    const text = card.textContent || '';
                    const match = text.match(/\\b(19|20)\\d{2}\\b/);
                    if (match) {{
                        year = match[0];
                    }}
                }}
                
                // Get venue
                let venue = '';
                const venueSelectors = ['.venue', '.journal', '[data-test-id="venue"]'];
                for (let s = 0; s < venueSelectors.length; s++) {{
                    const el = card.querySelector(venueSelectors[s]);
                    if (el) {{
                        venue = el.textContent.trim();
                        break;
                    }}
                }}
                
                results.push({{
                    title: title,
                    url: href,
                    paperId: paperId,
                    authors: authors,
                    abstract: abstract,
                    citations: citations,
                    year: year,
                    venue: venue
                }});
            }}
            
            return results;
        }})()
        """)
        
        if paper_data and isinstance(paper_data, list):
            results = paper_data
            console.print(f"[green]✓ Found {len(results)} papers[/green]")
        else:
            console.print("[yellow]No paper data extracted[/yellow]")
            # Fallback: just get URLs
            paper_urls = evaluate_cdp(ws, """
            (function() {
                const links = document.querySelectorAll('a[href^="/paper/"]');
                const unique = new Set();
                links.forEach(function(link) {
                    if (link.href && !link.href.includes('#citing-papers')) {
                        unique.add(link.href);
                    }
                });
                return Array.from(unique);
            })()
            """)
            
            if paper_urls:
                console.print(f"[green]✓ Found {len(paper_urls)} paper URLs[/green]")
                for url in paper_urls[:max_results]:
                    paper_id = ''
                    if '/paper/' in url:
                        parts = url.split('/paper/')
                        if len(parts) > 1:
                            paper_id = parts[1].split('?')[0] or ''
                    results.append({
                        'title': 'Unknown title',
                        'url': url,
                        'paperId': paper_id,
                        'authors': '',
                        'abstract': '',
                        'citations': '',
                        'year': '',
                        'venue': ''
                    })
        
        return results
        
    except Exception as e:
        console.print(f"[red]Scrape error: {e}[/red]")
        import traceback
        traceback.print_exc()
        if retries > 0:
            console.print(f"[yellow]Retrying... ({retries} attempts left)[/yellow]")
            time.sleep(2)
            return scrape_semantic_scholar(query, max_results, retries - 1)
        return []
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass

def scrape_paper_details(ws, paper_url_or_id):
    """
    Scrape detailed information from a specific paper page.
    
    Args:
        ws: WebSocket connection to CDP
        paper_url_or_id: Full URL or paper ID
    
    Returns:
        dict with detailed paper information
    """
    # Construct full URL if only ID is provided
    if not paper_url_or_id.startswith('http'):
        paper_url = f"https://www.semanticscholar.org/paper/{paper_url_or_id}"
    else:
        paper_url = paper_url_or_id
    
    console.print(f"[dim]📄 Opening: {paper_url[:80]}...[/dim]")
    
    # Navigate to paper page
    send_cdp(ws, 2000, "Page.navigate", {"url": paper_url})
    time.sleep(2)
    
    # Wait for page to load
    for attempt in range(15):
        loading = evaluate_cdp(ws, """
        (function() {
            const loading = document.querySelector('.loading, .spinner, .skeleton');
            if (loading) return 'loading';
            
            const content = document.querySelector('.paper-detail, .paper-content, article');
            if (content && content.textContent.length > 100) return 'loaded';
            
            return 'waiting';
        })()
        """)
        
        if loading == 'loaded':
            break
        elif loading == 'loading':
            time.sleep(1)
        else:
            time.sleep(1)
    
    # Extract detailed paper information
    paper_info = evaluate_cdp(ws, """
    (function() {
        const info = {
            title: '',
            authors: [],
            abstract: '',
            year: '',
            venue: '',
            citationCount: '',
            doi: '',
            arxivId: '',
            pdfUrl: '',
            referencesCount: '',
            citationsCount: ''
        };
        
        // Get title
        const titleEl = document.querySelector('h1, .paper-title, [data-test-id="paper-title"]');
        if (titleEl) {
            info.title = titleEl.textContent.trim();
        }
        
        // Get authors
        const authorEls = document.querySelectorAll('.author-list .author, [data-test-id="authors"] a, .authors .author');
        authorEls.forEach(function(el) {
            const name = el.textContent.trim();
            if (name && name.length > 1) {
                info.authors.push(name);
            }
        });
        
        // Get abstract
        const abstractEl = document.querySelector('.abstract, .paper-abstract, [data-test-id="abstract"], .description');
        if (abstractEl) {
            let abstractText = abstractEl.textContent.trim();
            abstractText = abstractText.replace(/^Abstract\\s*/i, '').trim();
            info.abstract = abstractText;
        }
        
        // Get year
        const yearMatch = document.body.textContent.match(/\\b(19|20)\\d{2}\\b/);
        if (yearMatch) {
            info.year = yearMatch[0];
        }
        
        // Get venue
        const venueEl = document.querySelector('.venue, .journal, .publication-venue, [data-test-id="venue"]');
        if (venueEl) {
            info.venue = venueEl.textContent.trim();
        }
        
        // Get citation count
        const citEl = document.querySelector('.citation-count, [data-test-id="citation-count"], .citations .count');
        if (citEl) {
            const citText = citEl.textContent.trim();
            const citMatch = citText.match(/\\d+/);
            if (citMatch) {
                info.citationCount = citMatch[0];
            }
        }
        
        // Get DOI
        const doiEl = document.querySelector('a[href*="doi.org"]');
        if (doiEl) {
            const doiMatch = doiEl.href.match(/10\\.\\d+\\/.+/);
            if (doiMatch) {
                info.doi = doiMatch[0];
            }
        }
        
        // Get arXiv ID
        const arxivEl = document.querySelector('a[href*="arxiv.org"]');
        if (arxivEl) {
            const arxivMatch = arxivEl.href.match(/\\d{4}\\.\\d{4,5}/);
            if (arxivMatch) {
                info.arxivId = arxivMatch[0];
            }
        }
        
        // Get PDF URL
        const pdfEl = document.querySelector('a[href*=".pdf"], a[href*="pdf"], [data-test-id="pdf-link"]');
        if (pdfEl) {
            info.pdfUrl = pdfEl.href;
        }
        
        // Get references count
        const refEl = document.querySelector('.references .count, [data-test-id="references-count"]');
        if (refEl) {
            const refText = refEl.textContent.trim();
            const refMatch = refText.match(/\\d+/);
            if (refMatch) {
                info.referencesCount = refMatch[0];
            }
        }
        
        return info;
    })()
    """)
    
    return paper_info

def scrape_multiple_papers(query, max_results=50):
    """Scrape search results and then get details for each paper."""
    ws = None
    results = []
    
    try:
        if not is_cdp_alive():
            if not start_chrome_headless():
                console.print("[red]Could not start Chrome[/red]")
                return []
        
        ws = connect_cdp()
        if not ws:
            console.print("[red]Could not connect to CDP[/red]")
            return []
        
        # First, search for papers
        search_url = f"https://www.semanticscholar.org/search?q={quote(query)}"
        if not navigate_cdp(ws, search_url):
            console.print("[red]Navigation failed[/red]")
            return []
        
        time.sleep(2)
        
        # Extract paper IDs/URLs from search results
        paper_urls = evaluate_cdp(ws, """
        (function() {
            const links = document.querySelectorAll('a[href^="/paper/"]');
            const unique = new Set();
            links.forEach(function(link) {
                const href = link.href;
                if (href && !href.includes('#citing-papers') && !href.includes('#references')) {
                    unique.add(href);
                }
            });
            return Array.from(unique);
        })()
        """)
        
        if not paper_urls:
            console.print("[yellow]No paper URLs found[/yellow]")
            return []
        
        console.print(f"[green]Found {len(paper_urls)} unique papers[/green]")
        
        # Limit to max_results
        paper_urls = paper_urls[:max_results]
        
        # Now visit each paper page and extract details
        for i, url in enumerate(paper_urls, 1):
            console.print(f"\n[cyan]📄 [{i}/{len(paper_urls)}] Extracting paper details...[/cyan]")
            
            paper_info = scrape_paper_details(ws, url)
            
            if paper_info and paper_info.get('title'):
                # Extract paper ID from URL
                paper_id = ''
                if '/paper/' in url:
                    parts = url.split('/paper/')
                    if len(parts) > 1:
                        paper_id = parts[1].split('?')[0] or ''
                paper_info['paperId'] = paper_id
                paper_info['url'] = url
                
                results.append(paper_info)
                
                # Show preview
                console.print(f"[green]✓ {paper_info.get('title', 'Unknown')[:60]}[/green]")
                if paper_info.get('authors'):
                    console.print(f"[dim]  Authors: {', '.join(paper_info['authors'][:3])}[/dim]")
                if paper_info.get('year'):
                    console.print(f"[dim]  Year: {paper_info['year']}[/dim]")
                if paper_info.get('citationCount'):
                    console.print(f"[dim]  Citations: {paper_info['citationCount']}[/dim]")
                if paper_info.get('doi'):
                    console.print(f"[dim]  DOI: {paper_info['doi']}[/dim]")
            else:
                console.print(f"[yellow]Could not extract details for paper {i}[/yellow]")
            
            # Be gentle - wait between page loads
            if i < len(paper_urls):
                time.sleep(1.5)
        
        return results
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        return []
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass

def save_results(query, results, output_dir="semantic_results"):
    """Save scraped results to organized files"""
    os.makedirs(output_dir, exist_ok=True)
    safe_query = re.sub(r'[<>:"/\\|?*]', '_', query)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save as JSON
    json_file = os.path.join(output_dir, f"{safe_query}_{timestamp}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            "query": query,
            "timestamp": timestamp,
            "total": len(results),
            "results": results
        }, f, indent=2, ensure_ascii=False)
    console.print(f"[green]✓ Saved JSON: {json_file}[/green]")
    
    # Save as TSV with all fields
    tsv_file = os.path.join(output_dir, f"{safe_query}_{timestamp}.tsv")
    with open(tsv_file, 'w', encoding='utf-8') as f:
        # Header with all possible fields
        f.write("Title\tPaperID\tURL\tAuthors\tYear\tCitations\tVenue\tDOI\tarXiv\tPDF\tAbstract\n")
        for r in results:
            title = r.get('title', '').replace('\t', ' ').replace('\n', ' ')
            paper_id = r.get('paperId', '')
            url = r.get('url', '')
            
            # Handle authors (could be list or string)
            authors_raw = r.get('authors', [])
            if isinstance(authors_raw, list):
                authors = ', '.join(authors_raw).replace('\t', ' ')
            else:
                authors = str(authors_raw).replace('\t', ' ')
            
            year = r.get('year', '').replace('\t', ' ')
            citations = r.get('citationCount', r.get('citations', '')).replace('\t', ' ')
            venue = r.get('venue', '').replace('\t', ' ')
            doi = r.get('doi', '').replace('\t', ' ')
            arxiv = r.get('arxivId', '').replace('\t', ' ')
            pdf = r.get('pdfUrl', '').replace('\t', ' ')
            abstract = r.get('abstract', '').replace('\t', ' ').replace('\n', ' ')[:500]
            f.write(f"{title}\t{paper_id}\t{url}\t{authors}\t{year}\t{citations}\t{venue}\t{doi}\t{arxiv}\t{pdf}\t{abstract}\n")
    console.print(f"[green]✓ Saved TSV: {tsv_file}[/green]")
    
    # Save paper IDs
    ids_file = os.path.join(output_dir, f"{safe_query}_{timestamp}_ids.txt")
    with open(ids_file, 'w') as f:
        for r in results:
            if r.get('paperId'):
                f.write(f"{r['paperId']}\n")
    console.print(f"[green]✓ Saved paper IDs: {ids_file}[/green]")
    
    # Save URLs
    urls_file = os.path.join(output_dir, f"{safe_query}_{timestamp}_urls.txt")
    with open(urls_file, 'w') as f:
        for r in results:
            if r.get('url'):
                f.write(f"{r['url']}\n")
    console.print(f"[green]✓ Saved URLs: {urls_file}[/green]")
    
    return json_file, tsv_file

def display_results(results):
    """Display results in a rich table"""
    if not results:
        console.print("[yellow]No results to display[/yellow]")
        return
    
    # Check if this is deep scrape results (has authors as list)
    is_deep = isinstance(results[0].get('authors'), list) if results else False
    
    if is_deep:
        table = Table(title=f"Semantic Scholar Results ({len(results)} papers)")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="cyan", width=30)
        table.add_column("Authors", style="green", width=20)
        table.add_column("Year", style="yellow", width=8)
        table.add_column("Citations", style="magenta", width=10)
        table.add_column("DOI", style="blue", width=15)
        
        for i, paper in enumerate(results[:20], 1):
            title = paper.get('title', 'Unknown')[:30]
            authors = ', '.join(paper.get('authors', [])[:2])[:20]
            if len(paper.get('authors', [])) > 2:
                authors += ' et al.'
            year = paper.get('year', '')[:8]
            citations = paper.get('citationCount', '')[:10]
            doi = paper.get('doi', '')[:15]
            table.add_row(str(i), title, authors, year, citations, doi)
    else:
        table = Table(title=f"Semantic Scholar Results ({len(results)} papers)")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="cyan", width=35)
        table.add_column("Year", style="yellow", width=8)
        table.add_column("Citations", style="magenta", width=10)
        table.add_column("Venue", style="green", width=15)
        
        for i, paper in enumerate(results[:20], 1):
            title = paper.get('title', 'Unknown')[:35]
            year = paper.get('year', '')[:8]
            citations = paper.get('citations', '').strip()[:10]
            venue = paper.get('venue', '')[:15]
            table.add_row(str(i), title, year, citations, venue)
    
    console.print(table)
    
    if len(results) > 20:
        console.print(f"[dim]... and {len(results)-20} more papers[/dim]")

def main():
    """Command line interface for quick queries"""
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
        console.print(f"[bold blue]🔍 Searching for: {query}[/bold blue]")
        
        # Ask if user wants deep scrape
        deep_scrape = Prompt.ask("Get full details for each paper? (slower but more data)", choices=["y", "n"], default="n")
        
        if deep_scrape == "y":
            max_results = int(Prompt.ask("Max papers to scrape (be gentle with rate limits)", default="5"))
            console.print(f"\n[cyan]🔍 Deep scraping: {query}[/cyan]")
            console.print("[yellow]This will open each paper page individually[/yellow]")
            results = scrape_multiple_papers(query, max_results)
        else:
            max_results = int(Prompt.ask("Max results", default="30"))
            results = scrape_semantic_scholar(query, max_results)
        
        if results:
            display_results(results)
            save_results(query, results)
            
            # Show paper IDs for API use
            paper_ids = [r.get('paperId') for r in results if r.get('paperId')]
            if paper_ids:
                console.print(f"\n[green]Ready for API: {len(paper_ids)} paper IDs extracted[/green]")
                console.print("[dim]Use these IDs with: https://api.semanticscholar.org/graph/v1/paper/[/dim]")
        else:
            console.print("[red]No results found[/red]")
        
        cleanup()
        return
    
    # Interactive menu
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold blue]📚 SEMANTIC SCHOLAR SCRAPER[/bold blue]\n"
            "Extract paper data using headless Chrome CDP",
            border_style="blue"
        ))
        
        console.print("\n[cyan]1.[/cyan] 🔍 Quick Search (titles only)")
        console.print("[cyan]2.[/cyan] 📄 Deep Scrape (get full paper details)")
        console.print("[cyan]3.[/cyan] 📊 View Saved Results")
        console.print("[cyan]4.[/cyan] 🚪 Exit")
        
        choice = Prompt.ask("\nChoice", choices=["1", "2", "3", "4"])
        
        if choice == "1":
            query = Prompt.ask("Search query", default="embeddings")
            max_results = int(Prompt.ask("Max results", default="50"))
            
            console.print(f"\n[cyan]🔍 Searching for: {query}[/cyan]")
            results = scrape_semantic_scholar(query, max_results)
            
            if results:
                display_results(results)
                save_results(query, results)
                
                paper_ids = [r.get('paperId') for r in results if r.get('paperId')]
                if paper_ids:
                    console.print(f"\n[green]Ready for API: {len(paper_ids)} paper IDs extracted[/green]")
            else:
                console.print("[red]No results found[/red]")
                
        elif choice == "2":
            query = Prompt.ask("Search query", default="embeddings")
            max_results = int(Prompt.ask("Max papers to scrape (be gentle)", default="5"))
            
            console.print(f"\n[cyan]🔍 Deep scraping: {query}[/cyan]")
            console.print("[yellow]This will open each paper page individually[/yellow]")
            
            results = scrape_multiple_papers(query, max_results)
            
            if results:
                display_results(results)
                save_results(query, results)
            else:
                console.print("[red]No results found[/red]")
                
        elif choice == "3":
            if os.path.exists("semantic_results"):
                files = [f for f in os.listdir("semantic_results") if f.endswith('.json')]
                if files:
                    console.print("[cyan]Saved result files:[/cyan]")
                    for f in sorted(files)[-10:]:
                        file_size = os.path.getsize(os.path.join("semantic_results", f))
                        console.print(f"  • {f} ({file_size:,} bytes)")
                    
                    file_choice = Prompt.ask("Enter filename to view (or 'q' to cancel)", default="q")
                    if file_choice != 'q':
                        try:
                            # Find exact match or partial match
                            matched_file = None
                            for f in files:
                                if f == file_choice or f.startswith(file_choice):
                                    matched_file = f
                                    break
                            
                            if matched_file:
                                with open(os.path.join("semantic_results", matched_file), 'r', encoding='utf-8') as f:
                                    data = json.load(f)
                                    console.print(Panel.fit(
                                        f"[bold]Query: {data.get('query', 'Unknown')}[/bold]\n"
                                        f"Papers: {data.get('total', 0)}\n"
                                        f"Date: {data.get('timestamp', 'Unknown')}",
                                        border_style="cyan"
                                    ))
                                    results = data.get('results', [])
                                    display_results(results)
                            else:
                                console.print("[red]File not found[/red]")
                        except Exception as e:
                            console.print(f"[red]Error loading file: {e}[/red]")
                else:
                    console.print("[yellow]No saved result files found[/yellow]")
            else:
                console.print("[yellow]No results directory found[/yellow]")
                
        elif choice == "4":
            cleanup()
            console.print("[bold red]Goodbye![/bold red]")
            break
        
        if choice != "4":
            Prompt.ask("\nPress Enter to continue...", default="")

if __name__ == "__main__":
    try:
        import websocket
    except ImportError:
        console.print("[yellow]Installing websocket-client...[/yellow]")
        subprocess.run([sys.executable, "-m", "pip", "install", "websocket-client"], check=True)
        import websocket
    
    # Create results directory
    os.makedirs("semantic_results", exist_ok=True)
    console.print("[green]✓ Results directory: semantic_results[/green]")
    
    main()
