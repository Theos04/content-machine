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

console = Console()
SCRAPED_DATA_FILE = "pinterest_scraping_history.json"
PIN_URLS_FILE = "pin_urls.txt"

chrome_process = None

def cleanup():
    global chrome_process
    if chrome_process:
        chrome_process.terminate()

atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda sig, frame: cleanup())

def start_chrome_auto():
    global chrome_process
    subprocess.run(["pkill", "-f", "remote-debugging-port=2222"], capture_output=True)
    time.sleep(2)
    
    chrome_cmd = shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chrome_cmd:
        console.print("[red]Chrome not found![/red]")
        return False
    
    env = os.environ.copy()
    env["DISPLAY"] = ":1"
    
    user_data_dir = os.path.expanduser('~/chrome-cdp')
    os.makedirs(user_data_dir, exist_ok=True)
    
    cmd = [
        chrome_cmd, "--remote-debugging-port=2222", "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}", "--no-sandbox", "--disable-gpu",
        "--disable-dev-shm-usage", "--window-size=1920,1080"
    ]
    
    chrome_process = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    for i in range(15):
        time.sleep(1)
        try:
            requests.get("http://127.0.0.1:2222/json/version", timeout=2)
            console.print("[green]Chrome ready[/green]")
            return True
        except:
            continue
    return False

def get_ws_url():
    try:
        tabs = requests.get("http://127.0.0.1:2222/json/list", timeout=5).json()
        if tabs:
            return tabs[0].get("webSocketDebuggerUrl")
    except:
        pass
    return None

def connect_cdp():
    ws_url = get_ws_url()
    if not ws_url:
        return None
    
    ws = websocket.create_connection(ws_url, timeout=30)
    for method in ["Page.enable", "Runtime.enable", "Network.enable"]:
        ws.send(json.dumps({"id": 1, "method": method}))
    
    time.sleep(0.5)
    while True:
        try:
            ws.recv()
        except:
            break
    return ws

def send_cdp(ws, _id, method, params=None):
    ws.send(json.dumps({"id": _id, "method": method, "params": params or {}}))

def recv_cdp(ws, expected_id=None):
    while True:
        try:
            res = json.loads(ws.recv())
            if "id" in res and (expected_id is None or res["id"] == expected_id):
                return res
        except:
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
    send_cdp(ws, 1000, "Page.navigate", {"url": url})
    time.sleep(5)
    
    # Wait for pins to load
    for _ in range(20):
        pins = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
        if pins and pins > 0:
            console.print(f"[green]Loaded {pins} pins[/green]")
            return True
        time.sleep(1)
    return False

def scroll_page_properly(ws, times=10):
    """Proper scrolling that triggers Pinterest's infinite scroll"""
    previous_count = 0
    
    for i in range(times):
        # Get current pin count before scroll
        before_count = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
        
        # Multiple scroll methods to ensure it triggers
        console.print(f"[dim]Scroll {i+1}/{times} - Current pins: {before_count}[/dim]")
        
        # Method 1: Smooth scroll to bottom
        evaluate_cdp(ws, """
            window.scrollTo({
                top: document.body.scrollHeight,
                behavior: 'smooth'
            });
        """)
        time.sleep(1)
        
        # Method 2: Dispatch scroll event
        evaluate_cdp(ws, """
            window.dispatchEvent(new Event('scroll'));
            document.dispatchEvent(new Event('scroll'));
        """)
        time.sleep(1)
        
        # Method 3: Force load more by clicking load more button if exists
        evaluate_cdp(ws, """
            let loadMore = document.querySelector('[data-test-id="loadMoreButton"], button:contains("Load more")');
            if (loadMore) loadMore.click();
        """)
        time.sleep(1.5)
        
        # Method 4: Scroll again after small delay
        evaluate_cdp(ws, "window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)
        
        # Check if new content loaded
        after_count = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
        new_pins = after_count - before_count if after_count and before_count else 0
        
        if new_pins > 0:
            console.print(f"[green]  + Loaded {new_pins} new pins[/green]")
        elif after_count == before_count and i > 3:
            console.print(f"[yellow]  No new pins loaded. Stopping scroll.[/yellow]")
            break
        
        previous_count = after_count or before_count
        time.sleep(1)
    
    final_count = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
    console.print(f"[bold cyan]Total pins loaded: {final_count}[/bold cyan]")
    return True

def extract_pin_urls(ws):
    """Extract only the pin URLs from the current page"""
    pin_urls = evaluate_cdp(ws, """
        (function() {
            let urls = [];
            // Get all pin links
            let links = document.querySelectorAll('a[href*="/pin/"]');
            links.forEach(link => {
                let href = link.href;
                if (href && href.includes('/pin/') && !href.includes('/pin/create/')) {
                    // Clean up the URL (remove tracking parameters)
                    let cleanUrl = href.split('?')[0];
                    urls.push(cleanUrl);
                }
            });
            // Remove duplicates
            return [...new Set(urls)];
        })()
    """)
    
    return pin_urls if pin_urls else []

def save_pin_urls(urls, topic):
    """Save pin URLs to file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pin_urls_{topic.replace(' ', '_')}_{timestamp}.txt"
    
    with open(filename, 'w') as f:
        f.write(f"# Pinterest Pin URLs for: {topic}\n")
        f.write(f"# Total: {len(urls)}\n")
        f.write(f"# Scraped: {datetime.now().isoformat()}\n\n")
        for url in urls:
            f.write(f"{url}\n")
    
    # Also save to master file
    with open(PIN_URLS_FILE, 'a') as f:
        f.write(f"\n# {topic} - {timestamp}\n")
        for url in urls:
            f.write(f"{url}\n")
    
    console.print(f"[green]Saved {len(urls)} pin URLs to {filename}[/green]")
    return filename

def scrape_pinterest_urls(topic, scrolls=10):
    """Scrape only pin URLs from Pinterest"""
    ws = None
    try:
        ws = connect_cdp()
        if not ws:
            return []
        
        search_url = f"https://www.pinterest.com/search/pins/?q={quote(topic)}"
        console.print(f"[cyan]Searching: {search_url}[/cyan]")
        
        if not navigate_cdp(ws, search_url):
            console.print("[red]Failed to load page[/red]")
            return []
        
        # Small delay for initial load
        time.sleep(2)
        
        # Get initial pin count
        initial_pins = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
        console.print(f"[cyan]Initial pins: {initial_pins}[/cyan]")
        
        console.print(f"[cyan]Scrolling {scrolls} times to load more content...[/cyan]")
        scroll_page_properly(ws, times=scrolls)
        
        console.print("[cyan]Extracting pin URLs...[/cyan]")
        pin_urls = extract_pin_urls(ws)
        
        console.print(f"[green]Found {len(pin_urls)} unique pin URLs[/green]")
        
        # Show first 5 URLs as preview
        for i, url in enumerate(pin_urls[:5], 1):
            console.print(f"  {i}. {url}")
        
        if len(pin_urls) > 5:
            console.print(f"  ... and {len(pin_urls) - 5} more")
        
        return pin_urls
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return []
    finally:
        if ws:
            ws.close()

def scrape_and_save(topic, scrolls=10):
    """Main function to scrape and save pin URLs"""
    console.print(f"[bold green]🎬 Scraping Pinterest URLs for: {topic}[/bold green]")
    
    # Start VNC
    subprocess.run(["vncserver", ":1"], capture_output=True)
    
    if not start_chrome_auto():
        console.print("[red]Failed to start Chrome[/red]")
        return
    
    time.sleep(2)
    
    pin_urls = scrape_pinterest_urls(topic, scrolls)
    
    if pin_urls:
        filename = save_pin_urls(pin_urls, topic)
        
        # Save to JSON as well
        json_file = filename.replace('.txt', '.json')
        with open(json_file, 'w') as f:
            json.dump({
                "topic": topic,
                "timestamp": datetime.now().isoformat(),
                "total": len(pin_urls),
                "urls": pin_urls
            }, f, indent=2)
        console.print(f"[green]Saved JSON to {json_file}[/green]")
        
        # Summary
        console.print(f"\n[bold green]✓ Success! {len(pin_urls)} pin URLs saved[/bold green]")
        console.print(f"[dim]Files created:[/dim]")
        console.print(f"  • {filename}")
        console.print(f"  • {json_file}")
    else:
        console.print("[yellow]No pin URLs found[/yellow]")

def view_saved_urls():
    """View previously saved pin URLs"""
    if os.path.exists(PIN_URLS_FILE):
        with open(PIN_URLS_FILE, 'r') as f:
            content = f.read()
            lines = content.split('\n')
            recent = '\n'.join(lines[-50:])
            console.print(Panel(recent, title="Recent Pin URLs (last 50 lines)", border_style="cyan"))
    else:
        console.print("[yellow]No saved URLs yet[/yellow]")

def menu():
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold green]🎬 PINTEREST PIN URL SCRAPER[/bold green]\nExtracts only pin URLs - no video downloading",
            border_style="green"
        ))
        
        console.print("\n[cyan]1.[/cyan] 🔗 Scrape Pin URLs")
        console.print("[cyan]2.[/cyan] 📄 View Saved URLs")
        console.print("[cyan]3.[/cyan] 🚪 Exit")
        
        choice = Prompt.ask("\nChoice", choices=["1", "2", "3"])
        
        if choice == "1":
            topic = Prompt.ask("Search topic", default="explosion green screen")
            scrolls = int(Prompt.ask("Number of scrolls", default="15"))
            scrape_and_save(topic, scrolls)
        elif choice == "2":
            view_saved_urls()
        elif choice == "3":
            cleanup()
            console.print("[bold red]Goodbye![/bold red]")
            break
        
        if choice != "3":
            Prompt.ask("\nPress Enter...", default="")

if __name__ == "__main__":
    try:
        import websocket
    except ImportError:
        subprocess.run(["pip", "install", "websocket-client"], capture_output=True)
    
    subprocess.run(["vncserver", ":1"], capture_output=True)
    menu()
