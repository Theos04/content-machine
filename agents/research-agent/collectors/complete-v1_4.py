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
import sys  # <-- NEW for pip install

console = Console()
SCRAPED_DATA_FILE = "pinterest_scraping_history.json"
PIN_URLS_FILE = "pin_urls.txt"

chrome_process = None

# ------------------- yt-dlp helpers -------------------
def ensure_ytdlp():
    """Check if yt-dlp is installed, install if missing"""
    try:
        subprocess.run(['yt-dlp', '--version'], capture_output=True, check=True)
        console.print("[green]✓ yt-dlp found[/green]")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[yellow]yt-dlp not found. Installing...[/yellow]")
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'yt-dlp'], check=True)
            console.print("[green]✓ yt-dlp installed successfully[/green]")
            return True
        except subprocess.CalledProcessError:
            console.print("[red]Failed to install yt-dlp. Please install manually: pip install yt-dlp[/red]")
            return False

def is_video_pin(pin_url):
    """Check if a Pinterest pin URL contains a video using yt-dlp"""
    try:
        # Get JSON info without downloading
        result = subprocess.run(
            ['yt-dlp', '-j', '--skip-download', pin_url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return False
        info = json.loads(result.stdout)
        # Look for video formats
        if 'formats' in info:
            for f in info['formats']:
                if f.get('vcodec', 'none') != 'none' and f.get('ext') in ['mp4', 'webm', 'mov', 'm4v']:
                    return True
        # Alternative: duration > 0 suggests video
        if info.get('duration', 0) > 0:
            return True
        return False
    except Exception as e:
        console.print(f"[dim]Check failed for {pin_url}: {e}[/dim]")
        return False

def download_pin_video(pin_url, output_dir='downloads'):
    """Download a single pin video using yt-dlp"""
    os.makedirs(output_dir, exist_ok=True)
    # Template: downloads/Title.ext
    cmd = [
        'yt-dlp',
        '-o', f'{output_dir}/%(title)s.%(ext)s',
        '--no-overwrites',
        '--progress',
        pin_url
    ]
    try:
        console.print(f"[dim]Downloading: {pin_url}[/dim]")
        subprocess.run(cmd, check=True, timeout=300)
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Download failed: {e}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return False

def download_videos_from_urls(urls, output_dir='downloads'):
    """Scan a list of pin URLs, download only video pins"""
    if not ensure_ytdlp():
        console.print("[red]Cannot proceed without yt-dlp[/red]")
        return 0
    downloaded = 0
    total = len(urls)
    for i, url in enumerate(urls, 1):
        console.print(f"[cyan]Checking {i}/{total}: {url}[/cyan]")
        if is_video_pin(url):
            console.print("[green]✓ Video detected, downloading...[/green]")
            if download_pin_video(url, output_dir):
                downloaded += 1
            # Polite delay between downloads
            time.sleep(1)
        else:
            console.print("[yellow]✗ Not a video pin, skipping[/yellow]")
    return downloaded

def download_from_file(file_path, output_dir='downloads'):
    """Read a file containing pin URLs (one per line) and download videos"""
    if not os.path.exists(file_path):
        console.print(f"[red]File not found: {file_path}[/red]")
        return
    with open(file_path, 'r') as f:
        lines = f.readlines()
    urls = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and '/pin/' in line:
            urls.append(line)
    if not urls:
        console.print("[yellow]No pin URLs found in file[/yellow]")
        return
    console.print(f"[cyan]Found {len(urls)} pin URLs in {file_path}[/cyan]")
    downloaded = download_videos_from_urls(urls, output_dir)
    console.print(f"[bold green]Downloaded {downloaded} videos[/bold green]")

# ------------------- existing code (unchanged except added yt-dlp integration in scrape_and_save) -------------------
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
        chrome_cmd,
        "--remote-debugging-port=2222",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080"
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
    for _ in range(20):
        pins = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
        if pins and pins > 0:
            console.print(f"[green]Loaded {pins} pins[/green]")
            return True
        time.sleep(1)
    return False

def scroll_page_properly(ws, times=10):
    previous_count = 0
    for i in range(times):
        before_count = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
        console.print(f"[dim]Scroll {i+1}/{times} - Current pins: {before_count}[/dim]")
        evaluate_cdp(ws, """ window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }); """)
        time.sleep(1)
        evaluate_cdp(ws, """ window.dispatchEvent(new Event('scroll')); document.dispatchEvent(new Event('scroll')); """)
        time.sleep(1)
        evaluate_cdp(ws, """ let loadMore = document.querySelector('[data-test-id="loadMoreButton"], button:contains("Load more")'); if (loadMore) loadMore.click(); """)
        time.sleep(1.5)
        evaluate_cdp(ws, "window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)
        after_count = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
        new_pins = after_count - before_count if after_count and before_count else 0
        if new_pins > 0:
            console.print(f"[green] + Loaded {new_pins} new pins[/green]")
        elif after_count == before_count and i > 3:
            console.print(f"[yellow] No new pins loaded. Stopping scroll.[/yellow]")
            break
        previous_count = after_count or before_count
        time.sleep(1)
    final_count = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
    console.print(f"[bold cyan]Total pins loaded: {final_count}[/bold cyan]")
    return True

def extract_pin_urls(ws):
    pin_urls = evaluate_cdp(ws, """
    (function() {
        let urls = [];
        let links = document.querySelectorAll('a[href*="/pin/"]');
        links.forEach(link => {
            let href = link.href;
            if (href && href.includes('/pin/') && !href.includes('/pin/create/')) {
                let cleanUrl = href.split('?')[0];
                urls.push(cleanUrl);
            }
        });
        return [...new Set(urls)];
    })()
    """)
    return pin_urls if pin_urls else []

def save_pin_urls(urls, topic):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pin_urls_{topic.replace(' ', '')}_{timestamp}.txt"  # fixed underscore
    with open(filename, 'w') as f:
        f.write(f"# Pinterest Pin URLs for: {topic}\n")
        f.write(f"# Total: {len(urls)}\n")
        f.write(f"# Scraped: {datetime.now().isoformat()}\n\n")
        for url in urls:
            f.write(f"{url}\n")
    with open(PIN_URLS_FILE, 'a') as f:
        f.write(f"\n# {topic} - {timestamp}\n")
        for url in urls:
            f.write(f"{url}\n")
    console.print(f"[green]Saved {len(urls)} pin URLs to {filename}[/green]")
    return filename

def scrape_pinterest_urls(topic, scrolls=10):
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
        time.sleep(2)
        initial_pins = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
        console.print(f"[cyan]Initial pins: {initial_pins}[/cyan]")
        console.print(f"[cyan]Scrolling {scrolls} times to load more content...[/cyan]")
        scroll_page_properly(ws, times=scrolls)
        console.print("[cyan]Extracting pin URLs...[/cyan]")
        pin_urls = extract_pin_urls(ws)
        console.print(f"[green]Found {len(pin_urls)} unique pin URLs[/green]")
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
    console.print(f"[bold green]🎬 Scraping Pinterest URLs for: {topic}[/bold green]")
    subprocess.run(["vncserver", ":1"], capture_output=True)
    if not start_chrome_auto():
        console.print("[red]Failed to start Chrome[/red]")
        return
    time.sleep(2)
    pin_urls = scrape_pinterest_urls(topic, scrolls)
    if pin_urls:
        filename = save_pin_urls(pin_urls, topic)
        json_file = filename.replace('.txt', '.json')
        with open(json_file, 'w') as f:
            json.dump({
                "topic": topic,
                "timestamp": datetime.now().isoformat(),
                "total": len(pin_urls),
                "urls": pin_urls
            }, f, indent=2)
        console.print(f"[green]Saved JSON to {json_file}[/green]")
        console.print(f"\n[bold green]✓ Success! {len(pin_urls)} pin URLs saved[/bold green]")
        console.print(f"[dim]Files created:[/dim]")
        console.print(f" • {filename}")
        console.print(f" • {json_file}")

        # -------- NEW: ask to download videos --------
        download_choice = Prompt.ask("\nDownload video pins now?", choices=["y", "n"], default="n")
        if download_choice == "y":
            if ensure_ytdlp():
                downloaded = download_videos_from_urls(pin_urls)
                console.print(f"[bold green]Downloaded {downloaded} videos[/bold green]")
            else:
                console.print("[red]yt-dlp not available, skipping download[/red]")
    else:
        console.print("[yellow]No pin URLs found[/yellow]")

def view_saved_urls():
    if os.path.exists(PIN_URLS_FILE):
        with open(PIN_URLS_FILE, 'r') as f:
            content = f.read()
            lines = content.split('\n')
            recent = '\n'.join(lines[-50:])
            console.print(Panel(recent, title="Recent Pin URLs (last 50 lines)", border_style="cyan"))
    else:
        console.print("[yellow]No saved URLs yet[/yellow]")

def download_videos_menu():
    """Menu to download videos from a saved URL file"""
    console.print("[cyan]📁 Available pin URL files:[/cyan]")
    files = [f for f in os.listdir('.') if f.startswith('pin_urls_') and f.endswith('.txt')]
    if not files:
        console.print("[yellow]No pin URL files found[/yellow]")
        return
    for i, f in enumerate(files, 1):
        console.print(f"  {i}. {f}")
    choice = Prompt.ask("Select file number (or 'q' to cancel)", default="q")
    if choice.lower() == 'q':
        return
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            download_from_file(files[idx])
        else:
            console.print("[red]Invalid selection[/red]")
    except ValueError:
        console.print("[red]Invalid input[/red]")

def menu():
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold green]🎬 PINTEREST PIN URL SCRAPER[/bold green]\nExtracts pin URLs + yt-dlp video downloader",
            border_style="green"
        ))
        console.print("\n[cyan]1.[/cyan] 🔗 Scrape Pin URLs and optionally download videos")
        console.print("[cyan]2.[/cyan] 📄 View Saved URLs")
        console.print("[cyan]3.[/cyan] ⬇️ Download videos from a saved URL file")
        console.print("[cyan]4.[/cyan] 🚪 Exit")
        choice = Prompt.ask("\nChoice", choices=["1", "2", "3", "4"])
        if choice == "1":
            topic = Prompt.ask("Search topic", default="explosion green screen")
            scrolls = int(Prompt.ask("Number of scrolls", default="15"))
            scrape_and_save(topic, scrolls)
        elif choice == "2":
            view_saved_urls()
        elif choice == "3":
            download_videos_menu()
        elif choice == "4":
            cleanup()
            console.print("[bold red]Goodbye![/bold red]")
            break
        if choice != "4":
            Prompt.ask("\nPress Enter...", default="")

if __name__ == "__main__":
    try:
        import websocket
    except ImportError:
        subprocess.run(["pip", "install", "websocket-client"], capture_output=True)
    subprocess.run(["vncserver", ":1"], capture_output=True)
    menu()
