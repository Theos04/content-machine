# semanticscholar_scraper.py
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
import subprocess
import os
import time
import json
import requests
import websocket
from urllib.parse import quote, urljoin, urlparse
import signal
import atexit
import shutil
from datetime import datetime
import sys
import re
import base64

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

def click_next_page(ws):
    """Click the next page button if available."""
    console.print("[cyan]Looking for next page...[/cyan]")
    
    # Check if next page exists and click it
    next_result = evaluate_cdp(ws, """
    (function() {
        // Find pagination controls
        const nextButton = document.querySelector('a[rel="next"], button[aria-label="Next"], .pagination .next, [data-test-id="next-page"]');
        if (nextButton) {
            const isDisabled = nextButton.disabled || nextButton.classList.contains('disabled');
            if (!isDisabled) {
                nextButton.click();
                return 'clicked';
            } else {
                return 'disabled';
            }
        }
        
        // Alternative: find any pagination links
        const pagination = document.querySelector('.pagination, .pager');
        if (pagination) {
            const links = pagination.querySelectorAll('a');
            let nextLink = null;
            links.forEach(function(link) {
                const text = link.textContent.trim().toLowerCase();
                if (text === 'next' || text === '>' || text === '→' || text.includes('next')) {
                    nextLink = link;
                }
            });
            if (nextLink) {
                nextLink.click();
                return 'clicked';
            }
        }
        
        return 'not_found';
    })()
    """)
    
    if next_result == 'clicked':
        console.print("[green]✓ Navigated to next page[/green]")
        time.sleep(3)
        return True
    elif next_result == 'disabled':
        console.print("[yellow]Next page button is disabled[/yellow]")
        return False
    else:
        console.print("[yellow]No next page found[/yellow]")
        return False

def get_all_paper_urls_from_search(ws, max_pages=5):
    """Get paper URLs from search results across multiple pages."""
    all_paper_urls = []
    current_page = 0
    
    while current_page < max_pages:
        current_page += 1
        console.print(f"[cyan]📄 Scraping page {current_page}...[/cyan]")
        
        # Extract paper URLs from current page
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
            console.print("[yellow]No papers found on this page[/yellow]")
            break
        
        # Add to our collection
        all_paper_urls.extend(paper_urls)
        console.print(f"[green]Found {len(paper_urls)} papers on page {current_page} (total: {len(all_paper_urls)})[/green]")
        
        # Try to go to next page
        if current_page < max_pages:
            if not click_next_page(ws):
                console.print("[yellow]No more pages available[/yellow]")
                break
    
    # Remove duplicates
    unique_urls = list(dict.fromkeys(all_paper_urls))
    console.print(f"[bold green]Total unique papers across {current_page} pages: {len(unique_urls)}[/bold green]")
    
    return unique_urls

def download_pdf(pdf_url, output_dir, paper_title):
    """Download a PDF file."""
    if not pdf_url:
        return None
    
    try:
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', paper_title[:50])
        filename = f"{safe_title}.pdf"
        filepath = os.path.join(output_dir, filename)
        
        if os.path.exists(filepath):
            console.print(f"[dim]PDF already exists: {filename}[/dim]")
            return filepath
        
        console.print(f"[cyan]Downloading PDF: {filename}[/cyan]")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(pdf_url, headers=headers, timeout=60, stream=True)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            console.print(f"[green]✓ Downloaded: {filename}[/green]")
            return filepath
        else:
            console.print(f"[yellow]Failed to download PDF (status {response.status_code})[/yellow]")
            return None
    except Exception as e:
        console.print(f"[red]PDF download error: {e}[/red]")
        return None

def scrape_paper_details_and_resources(ws, paper_url_or_id, output_dir="paper_resources"):
    """
    Scrape detailed information from a specific paper page and download resources.
    """
    if not paper_url_or_id.startswith('http'):
        paper_url = f"https://www.semanticscholar.org/paper/{paper_url_or_id}"
    else:
        paper_url = paper_url_or_id
    
    console.print(f"[dim]📄 Opening: {paper_url[:80]}...[/dim]")
    
    send_cdp(ws, 2000, "Page.navigate", {"url": paper_url})
    time.sleep(2)
    
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
    
    full_html = evaluate_cdp(ws, "document.documentElement.outerHTML")
    
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
            citationsCount: '',
            externalLinks: [],
            figures: [],
            codeRepos: []
        };
        
        const titleEl = document.querySelector('h1, .paper-title, [data-test-id="paper-title"]');
        if (titleEl) {
            info.title = titleEl.textContent.trim();
        }
        
        const authorEls = document.querySelectorAll('.author-list .author, [data-test-id="authors"] a, .authors .author');
        authorEls.forEach(function(el) {
            const name = el.textContent.trim();
            if (name && name.length > 1) {
                info.authors.push(name);
            }
        });
        
        const abstractEl = document.querySelector('.abstract, .paper-abstract, [data-test-id="abstract"], .description');
        if (abstractEl) {
            let abstractText = abstractEl.textContent.trim();
            abstractText = abstractText.replace(/^Abstract\\s*/i, '').trim();
            info.abstract = abstractText;
        }
        
        const yearMatch = document.body.textContent.match(/\\b(19|20)\\d{2}\\b/);
        if (yearMatch) {
            info.year = yearMatch[0];
        }
        
        const venueEl = document.querySelector('.venue, .journal, .publication-venue, [data-test-id="venue"]');
        if (venueEl) {
            info.venue = venueEl.textContent.trim();
        }
        
        const citEl = document.querySelector('.citation-count, [data-test-id="citation-count"], .citations .count');
        if (citEl) {
            const citText = citEl.textContent.trim();
            const citMatch = citText.match(/\\d+/);
            if (citMatch) {
                info.citationCount = citMatch[0];
            }
        }
        
        const doiEl = document.querySelector('a[href*="doi.org"]');
        if (doiEl) {
            const doiMatch = doiEl.href.match(/10\\.\\d+\\/.+/);
            if (doiMatch) {
                info.doi = doiMatch[0];
            }
        }
        
        const arxivEl = document.querySelector('a[href*="arxiv.org"]');
        if (arxivEl) {
            const arxivMatch = arxivEl.href.match(/\\d{4}\\.\\d{4,5}/);
            if (arxivMatch) {
                info.arxivId = arxivMatch[0];
            }
        }
        
        const pdfEl = document.querySelector('a[href*=".pdf"], a[href*="pdf"], [data-test-id="pdf-link"]');
        if (pdfEl) {
            info.pdfUrl = pdfEl.href;
        }
        
        const refEl = document.querySelector('.references .count, [data-test-id="references-count"]');
        if (refEl) {
            const refText = refEl.textContent.trim();
            const refMatch = refText.match(/\\d+/);
            if (refMatch) {
                info.referencesCount = refMatch[0];
            }
        }
        
        const links = document.querySelectorAll('a[href^="http"]');
        links.forEach(function(link) {
            const href = link.href;
            const text = link.textContent.trim().toLowerCase();
            if (href.includes('doi.org') || href.includes('arxiv.org')) return;
            if (text.includes('code') || text.includes('github') || 
                text.includes('data') || text.includes('dataset') ||
                text.includes('supplementary') || text.includes('additional')) {
                info.externalLinks.push({
                    url: href,
                    text: link.textContent.trim() || 'Link'
                });
            }
        });
        
        const figures = document.querySelectorAll('img, figure');
        figures.forEach(function(img) {
            const src = img.src || img.getAttribute('data-src');
            if (src && (src.includes('.png') || src.includes('.jpg') || src.includes('.jpeg') || src.includes('.gif'))) {
                info.figures.push(src);
            }
        });
        
        const githubLinks = document.querySelectorAll('a[href*="github.com"]');
        githubLinks.forEach(function(link) {
            info.codeRepos.push(link.href);
        });
        
        return info;
    })()
    """)
    
    paper_id = ''
    if '/paper/' in paper_url:
        parts = paper_url.split('/paper/')
        if len(parts) > 1:
            paper_id = parts[1].split('?')[0] or ''
    paper_info['paperId'] = paper_id
    paper_info['url'] = paper_url
    
    os.makedirs(output_dir, exist_ok=True)
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', paper_info.get('title', 'untitled')[:50])
    html_file = os.path.join(output_dir, f"{safe_title}_page.html")
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(full_html)
    paper_info['htmlFile'] = html_file
    console.print(f"[dim]✓ Saved HTML: {html_file}[/dim]")
    
    if paper_info.get('pdfUrl'):
        pdf_file = download_pdf(paper_info['pdfUrl'], output_dir, paper_info.get('title', 'untitled'))
        paper_info['pdfFile'] = pdf_file
    
    if paper_info.get('figures'):
        figures_dir = os.path.join(output_dir, 'figures')
        os.makedirs(figures_dir, exist_ok=True)
        downloaded_figures = []
        for i, fig_url in enumerate(paper_info['figures'][:5]):
            try:
                if fig_url.startswith('//'):
                    fig_url = 'https:' + fig_url
                elif fig_url.startswith('/'):
                    fig_url = 'https://www.semanticscholar.org' + fig_url
                
                if fig_url.startswith('http'):
                    response = requests.get(fig_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
                    if response.status_code == 200:
                        ext = fig_url.split('.')[-1].split('?')[0][:5]
                        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                            ext = 'jpg'
                        fig_file = os.path.join(figures_dir, f"figure_{i+1}.{ext}")
                        with open(fig_file, 'wb') as f:
                            f.write(response.content)
                        downloaded_figures.append(fig_file)
                        console.print(f"[dim]✓ Downloaded figure: figure_{i+1}.{ext}[/dim]")
            except Exception as e:
                console.print(f"[dim]Could not download figure {i+1}: {e}[/dim]")
        paper_info['downloadedFigures'] = downloaded_figures
    
    return paper_info

def scrape_multiple_papers(query, max_pages=3, max_papers_per_page=10, download_resources=True):
    """Scrape search results across multiple pages."""
    ws = None
    all_results = []
    
    try:
        if not is_cdp_alive():
            if not start_chrome_headless():
                console.print("[red]Could not start Chrome[/red]")
                return []
        
        ws = connect_cdp()
        if not ws:
            console.print("[red]Could not connect to CDP[/red]")
            return []
        
        # Navigate to search
        search_url = f"https://www.semanticscholar.org/search?q={quote(query)}"
        if not navigate_cdp(ws, search_url):
            console.print("[red]Navigation failed[/red]")
            return []
        
        time.sleep(2)
        
        # Get all paper URLs across pages
        all_paper_urls = get_all_paper_urls_from_search(ws, max_pages)
        
        if not all_paper_urls:
            console.print("[yellow]No paper URLs found[/yellow]")
            return []
        
        # Limit to max_papers_per_page * max_pages
        total_papers = min(len(all_paper_urls), max_pages * max_papers_per_page)
        paper_urls = all_paper_urls[:total_papers]
        
        console.print(f"[bold cyan]Processing {len(paper_urls)} papers...[/bold cyan]")
        
        # Create output directory
        safe_query = re.sub(r'[<>:"/\\|?*]', '_', query)
        query_dir = os.path.join("semantic_results", safe_query)
        os.makedirs(query_dir, exist_ok=True)
        
        # Process each paper
        for i, url in enumerate(paper_urls, 1):
            console.print(f"\n[cyan]📄 [{i}/{len(paper_urls)}] Extracting paper details...[/cyan]")
            
            paper_dir = os.path.join(query_dir, f"paper_{i}")
            
            paper_info = scrape_paper_details_and_resources(ws, url, paper_dir)
            
            if paper_info and paper_info.get('title'):
                all_results.append(paper_info)
                
                console.print(f"[green]✓ {paper_info.get('title', 'Unknown')[:60]}[/green]")
                if paper_info.get('authors'):
                    console.print(f"[dim]  Authors: {', '.join(paper_info['authors'][:3])}[/dim]")
                if paper_info.get('year'):
                    console.print(f"[dim]  Year: {paper_info['year']}[/dim]")
                if paper_info.get('citationCount'):
                    console.print(f"[dim]  Citations: {paper_info['citationCount']}[/dim]")
                if paper_info.get('doi'):
                    console.print(f"[dim]  DOI: {paper_info['doi']}[/dim]")
                if paper_info.get('pdfFile'):
                    console.print(f"[dim]  📄 PDF: {os.path.basename(paper_info['pdfFile'])}[/dim]")
                if paper_info.get('codeRepos'):
                    console.print(f"[dim]  💻 Code: {len(paper_info['codeRepos'])} repos[/dim]")
            else:
                console.print(f"[yellow]Could not extract details for paper {i}[/yellow]")
            
            if i < len(paper_urls):
                time.sleep(1.5)
        
        return all_results
        
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
    """Save scraped results to organized files."""
    os.makedirs(output_dir, exist_ok=True)
    safe_query = re.sub(r'[<>:"/\\|?*]', '_', query)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    json_file = os.path.join(output_dir, f"{safe_query}_{timestamp}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            "query": query,
            "timestamp": timestamp,
            "total": len(results),
            "results": results
        }, f, indent=2, ensure_ascii=False)
    console.print(f"[green]✓ Saved JSON: {json_file}[/green]")
    
    tsv_file = os.path.join(output_dir, f"{safe_query}_{timestamp}.tsv")
    with open(tsv_file, 'w', encoding='utf-8') as f:
        f.write("Title\tPaperID\tURL\tAuthors\tYear\tCitations\tVenue\tDOI\tarXiv\tPDF\tAbstract\n")
        for r in results:
            title = r.get('title', '').replace('\t', ' ').replace('\n', ' ')
            paper_id = r.get('paperId', '')
            url = r.get('url', '')
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
    
    ids_file = os.path.join(output_dir, f"{safe_query}_{timestamp}_ids.txt")
    with open(ids_file, 'w') as f:
        for r in results:
            if r.get('paperId'):
                f.write(f"{r['paperId']}\n")
    console.print(f"[green]✓ Saved paper IDs: {ids_file}[/green]")
    
    return json_file, tsv_file

def display_results(results):
    """Display results in a rich table."""
    if not results:
        console.print("[yellow]No results to display[/yellow]")
        return
    
    table = Table(title=f"Semantic Scholar Results ({len(results)} papers)")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan", width=30)
    table.add_column("Authors", style="green", width=20)
    table.add_column("Year", style="yellow", width=8)
    table.add_column("Citations", style="magenta", width=10)
    table.add_column("PDF", style="blue", width=8)
    
    for i, paper in enumerate(results[:20], 1):
        title = paper.get('title', 'Unknown')[:30]
        authors_raw = paper.get('authors', [])
        if isinstance(authors_raw, list):
            authors = ', '.join(authors_raw[:2])[:20]
            if len(authors_raw) > 2:
                authors += ' et al.'
        else:
            authors = str(authors_raw)[:20]
        year = paper.get('year', '')[:8]
        citations = paper.get('citationCount', '')[:10]
        has_pdf = "✅" if paper.get('pdfFile') else "❌"
        table.add_row(str(i), title, authors, year, citations, has_pdf)
    
    console.print(table)
    
    if len(results) > 20:
        console.print(f"[dim]... and {len(results)-20} more papers[/dim]")

def main():
    """Command line interface."""
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
        console.print(f"[bold blue]🔍 Searching for: {query}[/bold blue]")
        
        deep_scrape = Prompt.ask("Get full details for each paper? (slower but more data)", choices=["y", "n"], default="y")
        
        if deep_scrape == "y":
            max_pages = int(Prompt.ask("Number of pages to scrape", default="3"))
            max_papers_per_page = int(Prompt.ask("Papers per page", default="10"))
            
            console.print(f"\n[cyan]🔍 Deep scraping: {query}[/cyan]")
            console.print(f"[yellow]Pages: {max_pages}, Papers per page: {max_papers_per_page}[/yellow]")
            
            results = scrape_multiple_papers(query, max_pages, max_papers_per_page, download_resources=True)
        else:
            max_results = int(Prompt.ask("Max results", default="30"))
            results = scrape_semantic_scholar(query, max_results)
        
        if results:
            display_results(results)
            save_results(query, results)
            
            console.print(f"\n[bold green]✓ Complete![/bold green]")
            console.print(f"[dim]Papers: {len(results)}[/dim]")
            papers_with_pdf = len([r for r in results if r.get('pdfFile')])
            console.print(f"[dim]PDFs downloaded: {papers_with_pdf}[/dim]")
            console.print(f"[dim]Results saved in: semantic_results/[/dim]")
        else:
            console.print("[red]No results found[/red]")
        
        cleanup()
        return
    
    # Interactive menu
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold blue]📚 SEMANTIC SCHOLAR SCRAPER[/bold blue]\n"
            "Extract paper data with pagination support",
            border_style="blue"
        ))
        
        console.print("\n[cyan]1.[/cyan] 🔍 Quick Search (titles only)")
        console.print("[cyan]2.[/cyan] 📄 Deep Scrape (multiple pages + download resources)")
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
            else:
                console.print("[red]No results found[/red]")
                
        elif choice == "2":
            query = Prompt.ask("Search query", default="embeddings")
            max_pages = int(Prompt.ask("Number of pages to scrape", default="3"))
            max_papers_per_page = int(Prompt.ask("Papers per page", default="10"))
            
            console.print(f"\n[cyan]🔍 Deep scraping: {query}[/cyan]")
            console.print(f"[yellow]Pages: {max_pages}, Papers per page: {max_papers_per_page}[/yellow]")
            console.print("[yellow]This will open each paper page and download resources[/yellow]")
            
            results = scrape_multiple_papers(query, max_pages, max_papers_per_page, download_resources=True)
            
            if results:
                display_results(results)
                save_results(query, results)
                papers_with_pdf = len([r for r in results if r.get('pdfFile')])
                console.print(f"\n[green]✓ Downloaded {papers_with_pdf} PDFs[/green]")
            else:
                console.print("[red]No results found[/red]")
                
        elif choice == "3":
            if os.path.exists("semantic_results"):
                items = os.listdir("semantic_results")
                json_files = [f for f in items if f.endswith('.json')]
                dirs = [d for d in items if os.path.isdir(os.path.join("semantic_results", d))]
                
                if json_files:
                    console.print("[cyan]Saved result files:[/cyan]")
                    for f in sorted(json_files)[-10:]:
                        file_size = os.path.getsize(os.path.join("semantic_results", f))
                        console.print(f"  • {f} ({file_size:,} bytes)")
                
                if dirs:
                    console.print("\n[cyan]Paper resource directories:[/cyan]")
                    for d in sorted(dirs)[-5:]:
                        dir_path = os.path.join("semantic_results", d)
                        subdirs = [s for s in os.listdir(dir_path) if os.path.isdir(os.path.join(dir_path, s))]
                        console.print(f"  • {d}/ ({len(subdirs)} papers)")
                
                file_choice = Prompt.ask("Enter filename to view (or 'q' to cancel)", default="q")
                if file_choice != 'q':
                    try:
                        matched_file = None
                        for f in json_files:
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
    
    os.makedirs("semantic_results", exist_ok=True)
    console.print("[green]✓ Results directory: semantic_results[/green]")
    
    main()
