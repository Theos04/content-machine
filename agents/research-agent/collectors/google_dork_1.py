# google_dork_cdp.py
"""
Google Dorking Collector using Chrome CDP
Performs advanced Google searches with dork operators using the same CDP infrastructure
"""

import json
import time
import os
import sys
import re
import signal
import atexit
import shutil
import subprocess
import requests
import websocket
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import quote_plus
import logging

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich import box

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

console = Console()

# ============ CHROME MANAGEMENT (Reused from Semantic Scholar Scraper) ============
CHROME_PORT = 9222
chrome_process = None

def cleanup():
    """Terminate Chrome process on exit."""
    global chrome_process
    if chrome_process:
        try:
            chrome_process.terminate()
        except Exception:
            pass

atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda sig, frame: (cleanup(), exit(0)))

def find_chrome():
    """Find Chrome/Chromium binary on the system."""
    candidates = [
        "chromium-browser", "chromium", "google-chrome",
        "google-chrome-stable", "brave-browser"
    ]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return None

def is_cdp_alive():
    """Check if Chrome's debugging port is responding."""
    try:
        requests.get(f"http://127.0.0.1:{CHROME_PORT}/json/version", timeout=2)
        return True
    except Exception:
        return False

def start_chrome_headless():
    """Launch Chrome in headless mode with CDP enabled."""
    global chrome_process
    
    # Clean up existing instances
    subprocess.run(["pkill", "-f", f"remote-debugging-port={CHROME_PORT}"], capture_output=True)
    time.sleep(1)
    
    chrome_cmd = find_chrome()
    if not chrome_cmd:
        console.print("[red]✗ No Chrome/Chromium found. Install: pkg install chromium[/red]")
        return False
    
    user_data_dir = os.path.expanduser('~/chrome-cdp-dork')
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
        console.print("[cyan]Launching Chrome...[/cyan]")
        chrome_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("[cyan]Starting Chrome", total=30)
            for i in range(30):
                time.sleep(1)
                progress.update(task, advance=1)
                if is_cdp_alive():
                    console.print(f"[green]✓ Chrome ready ({i+1}s)[/green]")
                    return True
                if chrome_process.poll() is not None:
                    console.print(f"[red]✗ Chrome crashed (exit code {chrome_process.returncode})[/red]")
                    break
                    
    except Exception as e:
        console.print(f"[red]✗ Chrome launch error: {e}[/red]")
    
    return False

# ============ CDP CONNECTION ============
class CDPConnection:
    """Manages WebSocket connection to Chrome CDP"""
    
    def __init__(self, port=CHROME_PORT):
        self.port = port
        self.ws = None
        self.target_id = None
        self.target_ws = None
    
    def get_ws_url(self, target_id=None):
        """Get WebSocket URL from Chrome debugging port."""
        try:
            if target_id:
                tabs = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=5).json()
                for tab in tabs:
                    if tab.get('id') == target_id:
                        return tab.get('webSocketDebuggerUrl')
            else:
                tabs = requests.get(f"http://127.0.0.1:{self.port}/json/list", timeout=5).json()
                if tabs:
                    return tabs[0].get("webSocketDebuggerUrl")
        except Exception:
            pass
        return None
    
    def create_tab(self):
        """Create a new tab and return its ID."""
        try:
            response = requests.put(f"http://127.0.0.1:{self.port}/json/new", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.target_id = data.get('id')
                return self.target_id
        except Exception as e:
            logger.error(f"Failed to create tab: {e}")
        return None
    
    def close_tab(self, target_id=None):
        """Close a tab by its ID."""
        tab_id = target_id or self.target_id
        if tab_id:
            try:
                requests.post(f"http://127.0.0.1:{self.port}/json/close/{tab_id}", timeout=5)
            except Exception as e:
                logger.error(f"Failed to close tab: {e}")
    
    def connect_to_tab(self, target_id=None):
        """Connect to a specific tab."""
        tab_id = target_id or self.target_id
        ws_url = self.get_ws_url(tab_id)
        if not ws_url:
            return False
        
        try:
            if self.target_ws:
                try:
                    self.target_ws.close()
                except:
                    pass
            
            self.target_ws = websocket.create_connection(ws_url, timeout=10)
            
            # Enable required domains
            for method in ["Page.enable", "Runtime.enable", "Network.enable"]:
                self.target_ws.send(json.dumps({"id": 1, "method": method}))
                time.sleep(0.3)
            
            return True
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False
    
    def send_command(self, method: str, params: Dict = None, ws=None) -> Dict:
        """Send CDP command and wait for response."""
        ws = ws or self.target_ws
        if not ws:
            raise Exception("Not connected to Chrome")
        
        cmd_id = int(time.time() * 1000)
        message = {
            "id": cmd_id,
            "method": method,
            "params": params or {}
        }
        
        ws.send(json.dumps(message))
        
        # Wait for response
        while True:
            try:
                response = json.loads(ws.recv())
                if response.get("id") == cmd_id:
                    return response.get("result", {})
            except:
                break
        
        return {}
    
    def evaluate(self, expression: str, ws=None) -> Any:
        """Evaluate JavaScript in the browser context."""
        result = self.send_command("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True
        }, ws=ws)
        
        if result and "result" in result:
            return result["result"].get("value")
        return None
    
    def navigate(self, url: str, wait_time: int = 3) -> bool:
        """Navigate to a URL."""
        self.send_command("Page.navigate", {"url": url})
        time.sleep(wait_time)
        return True
    
    def get_page_content(self) -> str:
        """Get the page's HTML content."""
        return self.evaluate("document.documentElement.outerHTML")
    
    def get_page_text(self) -> str:
        """Get the page's text content."""
        return self.evaluate("document.body.innerText")
    
    def disconnect(self):
        """Close connections."""
        if self.target_ws:
            try:
                self.target_ws.close()
            except:
                pass
        
        if self.target_id:
            self.close_tab()
        
        self.target_ws = None
        self.target_id = None

# ============ GOOGLE DORK COLLECTOR ============
class GoogleDorkCollector:
    """Collector for Google dorking via Chrome CDP"""
    
    def __init__(self, port=CHROME_PORT):
        self.port = port
        self.cdp = CDPConnection(port)
        self.results_dir = "dork_results"
    
    def ensure_chrome(self) -> bool:
        """Ensure Chrome is running and accessible."""
        if not is_cdp_alive():
            if not start_chrome_headless():
                return False
        return True
    
    def search(self, query: str, max_results: int = 30, dork_type: str = "basic", max_pages: int = 3) -> List[Dict[str, Any]]:
        """
        Perform Google dorking search.
        
        Args:
            query: Search query (can include dork operators)
            max_results: Maximum number of results to return
            dork_type: Type of dork ('basic', 'advanced', 'vulnerability', 'security', 'data_leak', 'admin_panels')
            max_pages: Maximum number of search result pages to scrape
        """
        if not self.ensure_chrome():
            return []
        
        results = []
        search_queries = self._build_search_queries(query, dork_type)
        
        # Limit queries based on max_results
        if len(search_queries) * 20 > max_results * 2:
            search_queries = search_queries[:max(1, max_results // 10)]
        
        logger.info(f"Performing {len(search_queries)} Google dork searches")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        ) as progress:
            query_task = progress.add_task("[cyan]Processing dorks", total=len(search_queries))
            
            for i, dork_query in enumerate(search_queries):
                if len(results) >= max_results:
                    break
                
                progress.update(query_task, description=f"[cyan]Search: {dork_query[:40]}...")
                
                page_results = self._search_single_dork(dork_query, max_pages, max_results - len(results))
                results.extend(page_results)
                
                progress.update(query_task, advance=1)
        
        # Deduplicate results by URL
        unique_results = []
        seen_urls = set()
        for result in results:
            url = result.get('url')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        logger.info(f"Google dorking complete: {len(unique_results)} unique results")
        return unique_results[:max_results]
    
    def _build_search_queries(self, query: str, dork_type: str) -> List[str]:
        """Build search queries based on dork type."""
        # Pre-defined dork patterns
        dork_patterns = {
            "vulnerability": [
                'intitle:"index of" "config"',
                'intitle:"index of" "wp-config.php"',
                'inurl:admin "login"',
                'inurl:phpinfo.php',
                'intitle:"SQL Manager"',
                'inurl:".env" filetype:env',
                'intitle:"Dashboard" "admin"',
                'inurl:backup filetype:sql',
                'inurl:api "key"',
                'filetype:log "error"',
            ],
            "security": [
                'intitle:"index of" ".git"',
                'inurl:".git/config"',
                'filetype:conf "mysql"',
                'intitle:"index of" "password"',
                'inurl:".aws/credentials"',
                'filetype:pem "BEGIN RSA PRIVATE KEY"',
                'inurl:".ssh/id_rsa"',
                'intitle:"MongoDB Express"',
            ],
            "data_leak": [
                'filetype:xls "email" "password"',
                'filetype:pdf "confidential"',
                'intitle:"index of" "database"',
                'inurl:"/backup/"',
                'filetype:sql "INSERT INTO" "VALUES"',
                'intitle:"Index of" "logs"',
                'filetype:csv "credit card"',
            ],
            "admin_panels": [
                'intitle:"Admin Login"',
                'inurl:admin/login',
                'inurl:wp-admin',
                'inurl:administrator',
                'intitle:"Control Panel" login',
                'inurl:cpanel',
                'inurl:webmail',
            ],
            "basic": [
                f'"{query}"',
                f'intitle:"{query}"',
                f'inurl:{query}',
                f'allintext:{query}',
            ],
            "advanced": [
                f'intitle:"{query}"',
                f'inurl:{query}',
                f'"{query}" "pdf"',
                f'"{query}" site:edu',
                f'"{query}" filetype:pdf',
            ]
        }
        
        # Get patterns for the requested type
        patterns = dork_patterns.get(dork_type, dork_patterns["basic"])
        
        # If custom query, use it directly
        if dork_type == "custom" or ':' in query:
            return [query]
        
        # If query has operators already, use it
        if any(op in query for op in ['intitle:', 'inurl:', 'filetype:', 'site:']):
            return [query]
        
        # Apply the query to patterns
        search_queries = []
        for pattern in patterns:
            if '{query}' in pattern:
                search_queries.append(pattern.replace('{query}', query))
            elif ':' in pattern and '"' not in pattern:
                # For patterns like 'inurl:backup' we need to append the query
                parts = pattern.split(':')
                if len(parts) >= 2:
                    base = parts[0]
                    # If the pattern is like 'intitle:"index of"', it's a full dork
                    if '"' in pattern:
                        search_queries.append(pattern)
                    else:
                        search_queries.append(f'{base}:{query}')
                else:
                    search_queries.append(f'"{pattern} {query}"')
            else:
                search_queries.append(pattern)
        
        return search_queries
    
    def _search_single_dork(self, dork_query: str, max_pages: int = 3, max_results: int = 30) -> List[Dict[str, Any]]:
        """Search for a single dork query."""
        results = []
        
        try:
            # Create a new tab
            target_id = self.cdp.create_tab()
            if not target_id:
                return []
            
            # Connect to the tab
            if not self.cdp.connect_to_tab(target_id):
                self.cdp.close_tab(target_id)
                return []
            
            # Build search URL
            encoded_query = quote_plus(dork_query)
            google_url = f"https://www.google.com/search?q={encoded_query}&num=100"
            
            # Navigate
            self.cdp.navigate(google_url, wait_time=5)
            
            # Parse results from the page
            page_results = self._parse_google_results()
            
            for result in page_results:
                result['dork_query'] = dork_query
                result['search_timestamp'] = datetime.now().isoformat()
                results.append(result)
            
            # Try to get more pages
            for page in range(2, max_pages + 1):
                if len(results) >= max_results:
                    break
                
                # Check for next page button
                next_page = self.cdp.evaluate("""
                (function() {
                    const nextBtn = document.querySelector('a#pnnext, a[aria-label="Next"], a:contains("Next")');
                    if (nextBtn) {
                        nextBtn.click();
                        return true;
                    }
                    return false;
                })()
                """)
                
                if not next_page:
                    break
                
                time.sleep(3)
                
                page_results = self._parse_google_results()
                for result in page_results:
                    if len(results) >= max_results:
                        break
                    result['dork_query'] = dork_query
                    result['search_timestamp'] = datetime.now().isoformat()
                    results.append(result)
            
            # Clean up
            self.cdp.disconnect()
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            self.cdp.disconnect()
        
        return results
    
    def _parse_google_results(self) -> List[Dict[str, Any]]:
        """Parse Google search results from the current page."""
        results = []
        
        # Use JavaScript to extract results
        js_results = self.cdp.evaluate("""
        (function() {
            const results = [];
            
            // Try multiple selectors for Google result containers
            const selectors = [
                '.g',
                '.rc',
                '.tF2Cxc',
                '.srg .g',
                'div[data-hveid]'
            ];
            
            let containers = [];
            for (let i = 0; i < selectors.length; i++) {
                const found = document.querySelectorAll(selectors[i]);
                if (found.length > 0) {
                    containers = found;
                    break;
                }
            }
            
            containers.forEach(function(container) {
                try {
                    // Find title link
                    const link = container.querySelector('a[href^="http"]');
                    if (!link) return;
                    
                    const url = link.href;
                    if (!url || url.includes('google.com') || url.includes('youtube.com')) return;
                    
                    // Clean URL
                    let cleanUrl = url.replace(/&sa=.*$/, '').replace(/^\/url\?q=/, '');
                    cleanUrl = decodeURIComponent(cleanUrl);
                    
                    // Get title
                    const titleEl = container.querySelector('h3, .LC20lb, .DKV0Md');
                    const title = titleEl ? titleEl.textContent.trim() : 'No title';
                    
                    // Get description/snippet
                    const descEl = container.querySelector('.IsZvec, .VwiC3b, .aCOpRe, .lEBKkf');
                    const description = descEl ? descEl.textContent.trim() : '';
                    
                    // Get URL display
                    const citeEl = container.querySelector('cite, .TbwUpd, .iUh30');
                    const displayUrl = citeEl ? citeEl.textContent.trim() : '';
                    
                    // Get date if available
                    const dateEl = container.querySelector('.LEwnzc, .f, .sLP');
                    const date = dateEl ? dateEl.textContent.trim() : '';
                    
                    results.push({
                        title: title,
                        url: cleanUrl,
                        display_url: displayUrl,
                        description: description,
                        date: date,
                        source: 'google.com'
                    });
                } catch(e) {
                    // Skip errors
                }
            });
            
            return results;
        })()
        """)
        
        if isinstance(js_results, list):
            for item in js_results:
                if isinstance(item, dict):
                    results.append({
                        'title': item.get('title', ''),
                        'url': item.get('url', ''),
                        'content': item.get('description', ''),
                        'published': item.get('date', ''),
                        'source': 'google.com',
                        'display_url': item.get('display_url', '')
                    })
        
        return results
    
    def vulnerability_scan(self, target_domain: str) -> List[Dict[str, Any]]:
        """Perform vulnerability-focused dorking on a specific domain."""
        if not target_domain:
            return []
        
        dorks = [
            f'site:{target_domain} intitle:"index of"',
            f'site:{target_domain} inurl:admin',
            f'site:{target_domain} filetype:log',
            f'site:{target_domain} filetype:sql',
            f'site:{target_domain} inurl:backup',
            f'site:{target_domain} "config" filetype:php',
            f'site:{target_domain} "password" filetype:txt',
            f'site:{target_domain} "api key"',
            f'site:{target_domain} "database" filetype:sql',
            f'site:{target_domain} "wp-config"',
            f'site:{target_domain} ".env"',
            f'site:{target_domain} "debug"',
            f'site:{target_domain} filetype:env',
        ]
        
        results = []
        for dork in dorks:
            console.print(f"[dim]Testing: {dork}[/dim]")
            search_results = self.search(dork, max_results=5)
            results.extend(search_results)
            time.sleep(1)
        
        # Deduplicate
        seen = set()
        unique = []
        for r in results:
            url = r.get('url')
            if url and url not in seen:
                seen.add(url)
                unique.append(r)
        
        return unique
    
    def save_results(self, query: str, results: List[Dict], dork_type: str = "basic"):
        """Save results to JSON and CSV files."""
        os.makedirs(self.results_dir, exist_ok=True)
        
        safe_query = re.sub(r'[<>:"/\\|?*]', '_', query[:30])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_query}_{timestamp}"
        
        # Save JSON
        json_file = os.path.join(self.results_dir, f"{filename}.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump({
                "query": query,
                "dork_type": dork_type,
                "timestamp": timestamp,
                "total": len(results),
                "results": results
            }, f, indent=2, ensure_ascii=False)
        console.print(f"[green]✓ Saved JSON: {json_file}[/green]")
        
        # Save CSV
        csv_file = os.path.join(self.results_dir, f"{filename}.csv")
        import csv
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            if results:
                fieldnames = ['title', 'url', 'content', 'published', 'source', 'dork_query']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in results:
                    writer.writerow({k: r.get(k, '') for k in fieldnames})
        console.print(f"[green]✓ Saved CSV: {csv_file}[/green]")
        
        # Save URLs only
        urls_file = os.path.join(self.results_dir, f"{filename}_urls.txt")
        with open(urls_file, 'w', encoding='utf-8') as f:
            for r in results:
                if r.get('url'):
                    f.write(f"{r['url']}\n")
        console.print(f"[green]✓ Saved URLs: {urls_file}[/green]")
        
        return json_file, csv_file

def display_results(results, title="Results"):
    """Display results in a rich table."""
    if not results:
        console.print("[yellow]No results[/yellow]")
        return
    
    table = Table(title=f"{title} ({len(results)} results)", box=box.ROUNDED)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan", width=35)
    table.add_column("URL", style="green", width=35)
    table.add_column("Source", style="yellow", width=10)
    
    for i, result in enumerate(results[:20], 1):
        title = result.get('title', 'No title')[:33]
        url = result.get('url', 'No URL')[:33]
        source = result.get('source', '')[:10]
        table.add_row(str(i), title, url, source)
    
    console.print(table)
    if len(results) > 20:
        console.print(f"[dim]... and {len(results)-20} more[/dim]")

# ============ MAIN INTERFACE ============
def main():
    """Command line interface for Google Dork Collector."""
    # Check dependencies
    try:
        import websocket
    except ImportError:
        console.print("[yellow]Installing websocket-client...[/yellow]")
        subprocess.run([sys.executable, "-m", "pip", "install", "websocket-client"], check=True)
        import websocket
    
    # Command line mode
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
        console.print(f"[bold blue]🔍 Google Dork Search: {query}[/bold blue]")
        
        dork_type = Prompt.ask(
            "Dork type",
            choices=["basic", "vulnerability", "security", "data_leak", "admin_panels", "advanced", "custom"],
            default="basic"
        )
        
        max_results = int(Prompt.ask("Max results", default="30"))
        max_pages = int(Prompt.ask("Max pages", default="3"))
        
        collector = GoogleDorkCollector()
        results = collector.search(query, max_results, dork_type, max_pages)
        
        if results:
            display_results(results, f"Google Dork: {query}")
            collector.save_results(query, results, dork_type)
            
            # Statistics
            console.print(f"\n[bold green]✓ Complete![/bold green]")
            console.print(f"[dim]Results: {len(results)}[/dim]")
        else:
            console.print("[red]No results found[/red]")
        
        cleanup()
        return
    
    # Interactive mode
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold blue]🔍 GOOGLE DORK COLLECTOR[/bold blue]\n"
            "Advanced Google searching with dork operators",
            border_style="blue"
        ))
        
        console.print("\n[cyan]1.[/cyan] 🔎 Basic Search")
        console.print("[cyan]2.[/cyan] 🛡️ Vulnerability Scan")
        console.print("[cyan]3.[/cyan] 📁 View Saved Results")
        console.print("[cyan]4.[/cyan] 🚪 Exit")
        
        choice = Prompt.ask("Choice", choices=["1", "2", "3", "4"])
        
        if choice == "1":
            query = Prompt.ask("Search query")
            dork_type = Prompt.ask(
                "Dork type",
                choices=["basic", "vulnerability", "security", "data_leak", "admin_panels", "advanced", "custom"],
                default="basic"
            )
            max_results = int(Prompt.ask("Max results", default="30"))
            max_pages = int(Prompt.ask("Max pages", default="3"))
            
            collector = GoogleDorkCollector()
            results = collector.search(query, max_results, dork_type, max_pages)
            
            if results:
                display_results(results, f"Google Dork: {query}")
                collector.save_results(query, results, dork_type)
                console.print(f"\n[green]Results: {len(results)}[/green]")
            else:
                console.print("[red]No results[/red]")
                
        elif choice == "2":
            target = Prompt.ask("Target domain (e.g., example.com)")
            if target:
                collector = GoogleDorkCollector()
                console.print(f"[cyan]Scanning {target}...[/cyan]")
                results = collector.vulnerability_scan(target)
                
                if results:
                    display_results(results, f"Vulnerability Scan: {target}")
                    collector.save_results(f"vulnscan_{target}", results, "vulnerability")
                    console.print(f"\n[green]Found {len(results)} potential vulnerabilities[/green]")
                else:
                    console.print("[yellow]No vulnerabilities found[/yellow]")
                    
        elif choice == "3":
            if os.path.exists("dork_results"):
                json_files = [f for f in os.listdir("dork_results") if f.endswith('.json')]
                if json_files:
                    console.print("[cyan]Saved results:[/cyan]")
                    for f in sorted(json_files)[-10:]:
                        size = os.path.getsize(os.path.join("dork_results", f))
                        console.print(f"  • {f} ({size:,} bytes)")
                    
                    file_choice = Prompt.ask("File to view (or q)", default="q")
                    if file_choice != 'q':
                        matched = next((f for f in json_files if f == file_choice or f.startswith(file_choice)), None)
                        if matched:
                            with open(os.path.join("dork_results", matched), 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                console.print(Panel.fit(
                                    f"[bold]Query: {data.get('query', 'Unknown')}[/bold]\n"
                                    f"Type: {data.get('dork_type', 'Unknown')}\n"
                                    f"Results: {data.get('total', 0)}\n"
                                    f"Date: {data.get('timestamp', 'Unknown')}",
                                    border_style="cyan"
                                ))
                                display_results(data.get('results', []))
                        else:
                            console.print("[red]File not found[/red]")
                else:
                    console.print("[yellow]No saved results[/yellow]")
            else:
                console.print("[yellow]No results directory[/yellow]")
                
        elif choice == "4":
            cleanup()
            console.print("[bold red]Goodbye![/bold red]")
            break
        
        if choice != "4":
            Prompt.ask("Press Enter to continue...", default="")

if __name__ == "__main__":
    main()
