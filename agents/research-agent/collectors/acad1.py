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
        
        # FIXED: Removed optional chaining operators (?.)
        paper_data = evaluate_cdp(ws, f"""
        (function() {{
            const results = [];
            const maxResults = {max_results};
            
            // Try different selectors
            const selectors = [
                '.paper-card',
                '.search-result',
                '[data-test-id="paper-card"]',
                '.result-item',
                '.paper-row',
                'article'
            ];
            
            let items = [];
            for (let i = 0; i < selectors.length; i++) {{
                const found = document.querySelectorAll(selectors[i]);
                if (found.length > 0) {{
                    items = found;
                    break;
                }}
            }}
            
            // If no items found, try to get links directly
            if (items.length === 0) {{
                const links = document.querySelectorAll('a[href^="/paper/"]');
                const uniqueLinks = new Set();
                links.forEach(function(link) {{
                    if (link.href && !uniqueLinks.has(link.href)) {{
                        uniqueLinks.add(link.href);
                        const title = link.textContent.trim() || 'Unknown title';
                        let paperId = '';
                        const parts = link.href.split('/paper/');
                        if (parts.length > 1) {{
                            paperId = parts[1].split('?')[0] || '';
                        }}
                        results.push({{
                            title: title,
                            url: link.href,
                            paperId: paperId
                        }});
                    }}
                }});
                return results.slice(0, maxResults);
            }}
            
            // Process found items
            for (let i = 0; i < items.length && results.length < maxResults; i++) {{
                const item = items[i];
                
                const titleLink = item.querySelector('a[href^="/paper/"]');
                if (titleLink) {{
                    const title = titleLink.textContent.trim() || 'Unknown title';
                    const url = titleLink.href;
                    let paperId = '';
                    const parts = url.split('/paper/');
                    if (parts.length > 1) {{
                        paperId = parts[1].split('?')[0] || '';
                    }}
                    
                    const authors = item.querySelector('.authors, .author-list, [data-test-id="authors"]');
                    const authorText = authors ? authors.textContent.trim() : '';
                    
                    const abstract = item.querySelector('.abstract, .paper-abstract, [data-test-id="abstract"]');
                    const abstractText = abstract ? abstract.textContent.trim() : '';
                    
                    const citations = item.querySelector('.citations, [data-test-id="citation-count"]');
                    const citationText = citations ? citations.textContent.trim() : '';
                    
                    const year = item.querySelector('.year, .publication-date, [data-test-id="year"]');
                    const yearText = year ? year.textContent.trim() : '';
                    
                    results.push({{
                        title: title,
                        url: url,
                        paperId: paperId,
                        authors: authorText,
                        abstract: abstractText.substring(0, 300),
                        citations: citationText,
                        year: yearText
                    }});
                }}
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
                    if (link.href) unique.add(link.href);
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
                        'year': ''
                    })
        
        return results
        
    except Exception as e:
        console.print(f"[red]Scrape error: {e}[/red]")
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

def save_results(query, results, output_dir="semantic_results"):
    """Save scraped results to organized files"""
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
        f.write("Title\tPaperID\tURL\tAuthors\tCitations\tYear\tAbstract\n")
        for r in results:
            title = r.get('title', '').replace('\t', ' ').replace('\n', ' ')
            paper_id = r.get('paperId', '')
            url = r.get('url', '')
            authors = r.get('authors', '').replace('\t', ' ').replace('\n', ' ')
            citations = r.get('citations', '').replace('\t', ' ')
            year = r.get('year', '').replace('\t', ' ')
            abstract = r.get('abstract', '').replace('\t', ' ').replace('\n', ' ')[:500]
            f.write(f"{title}\t{paper_id}\t{url}\t{authors}\t{citations}\t{year}\t{abstract}\n")
    console.print(f"[green]✓ Saved TSV: {tsv_file}[/green]")
    
    ids_file = os.path.join(output_dir, f"{safe_query}_{timestamp}_ids.txt")
    with open(ids_file, 'w') as f:
        for r in results:
            if r.get('paperId'):
                f.write(f"{r['paperId']}\n")
    console.print(f"[green]✓ Saved paper IDs: {ids_file}[/green]")
    
    return json_file, tsv_file

def display_results(results):
    """Display results in a rich table"""
    if not results:
        console.print("[yellow]No results to display[/yellow]")
        return
    
    table = Table(title=f"Semantic Scholar Results ({len(results)} papers)")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan", width=40)
    table.add_column("Paper ID", style="green", width=20)
    table.add_column("Year", style="yellow", width=8)
    table.add_column("Citations", style="magenta", width=10)
    
    for i, paper in enumerate(results[:20], 1):
        title = paper.get('title', 'Unknown')[:50]
        paper_id = paper.get('paperId', '')[:20]
        year = paper.get('year', '')[:8]
        citations = paper.get('citations', '').replace('Citations', '').strip()[:10]
        table.add_row(str(i), title, paper_id, year, citations)
    
    console.print(table)
    
    if len(results) > 20:
        console.print(f"[dim]... and {len(results)-20} more papers[/dim]")

def main():
    """Command line interface for quick queries"""
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
        console.print(f"[bold blue]🔍 Searching for: {query}[/bold blue]")
        
        results = scrape_semantic_scholar(query, 30)
        
        if results:
            display_results(results)
            save_results(query, results)
            
            # Show paper IDs for API use
            paper_ids = [r.get('paperId') for r in results if r.get('paperId')]
            if paper_ids:
                console.print(f"\n[green]Ready for API: {len(paper_ids)} paper IDs extracted[/green]")
                console.print("[dim]Use these IDs with: https://api.semanticscholar.org/graph/v1/paper/[/dim]")
                console.print(f"\n[cyan]First 10 paper IDs:[/cyan]")
                for pid in paper_ids[:10]:
                    console.print(f"  {pid}")
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
        
        console.print("\n[cyan]1.[/cyan] 🔍 Search and Scrape Papers")
        console.print("[cyan]2.[/cyan] 📄 View Saved Results")
        console.print("[cyan]3.[/cyan] 🚪 Exit")
        
        choice = Prompt.ask("\nChoice", choices=["1", "2", "3"])
        
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
            if os.path.exists("semantic_results"):
                files = [f for f in os.listdir("semantic_results") if f.endswith('.json')]
                if files:
                    console.print("[cyan]Saved result files:[/cyan]")
                    for f in sorted(files)[-10:]:
                        console.print(f"  • {f}")
                    
                    file_choice = Prompt.ask("Enter filename to view (or 'q' to cancel)", default="q")
                    if file_choice != 'q':
                        try:
                            with open(os.path.join("semantic_results", file_choice), 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                console.print(Panel.fit(
                                    f"[bold]Query: {data.get('query', 'Unknown')}[/bold]\n"
                                    f"Papers: {data.get('total', 0)}\n"
                                    f"Date: {data.get('timestamp', 'Unknown')}",
                                    border_style="cyan"
                                ))
                                results = data.get('results', [])
                                display_results(results)
                        except Exception as e:
                            console.print(f"[red]Error loading file: {e}[/red]")
                else:
                    console.print("[yellow]No saved result files found[/yellow]")
            else:
                console.print("[yellow]No results directory found[/yellow]")
                
        elif choice == "3":
            cleanup()
            console.print("[bold red]Goodbye![/bold red]")
            break
        
        if choice != "3":
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
