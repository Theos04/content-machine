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

console = Console()
SCRAPED_DATA_FILE = "pinterest_scraping_history.json"
PIN_URLS_FILE = "pin_urls.txt"

chrome_process = None


# ------------------- yt-dlp helpers -------------------
def ensure_ytdlp():
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
    try:
        result = subprocess.run(
            ['yt-dlp', '-j', '--skip-download', pin_url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return False
        info = json.loads(result.stdout)
        if 'formats' in info:
            for f in info['formats']:
                if f.get('vcodec', 'none') != 'none' and f.get('ext') in ['mp4', 'webm', 'mov', 'm4v']:
                    return True
        if info.get('duration', 0) > 0:
            return True
        return False
    except Exception as e:
        console.print(f"[dim]Check failed for {pin_url}: {e}[/dim]")
        return False

def download_pin_video(pin_url, output_dir='downloads'):
    os.makedirs(output_dir, exist_ok=True)
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
            time.sleep(1)
        else:
            console.print("[yellow]✗ Not a video pin, skipping[/yellow]")
    return downloaded

def download_from_file(file_path, output_dir='downloads'):
    if not os.path.exists(file_path):
        console.print(f"[red]File not found: {file_path}[/red]")
        return
    with open(file_path, 'r') as f:
        lines = f.readlines()
    urls = [l.strip() for l in lines if l.strip() and not l.startswith('#') and '/pin/' in l]
    if not urls:
        console.print("[yellow]No pin URLs found in file[/yellow]")
        return
    console.print(f"[cyan]Found {len(urls)} pin URLs in {file_path}[/cyan]")
    downloaded = download_videos_from_urls(urls, output_dir)
    console.print(f"[bold green]Downloaded {downloaded} videos[/bold green]")


# ------------------- Chrome startup (FIXED) -------------------

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


def ensure_vnc_display():
    """
    Start VNC server on :1 and wait until the display is actually usable.
    Returns True if display :1 is ready, False otherwise.
    """
    display = ":1"

    # Check if VNC is already running on :1
    lock_file = "/tmp/.X1-lock"
    if os.path.exists(lock_file):
        console.print("[green]✓ VNC display :1 already running[/green]")
        return True

    console.print("[cyan]Starting VNC server on :1 ...[/cyan]")
    result = subprocess.run(
        ["vncserver", display, "-geometry", "1920x1080", "-depth", "24"],
        capture_output=True, text=True
    )

    if result.returncode != 0 and "already" not in result.stderr.lower():
        console.print(f"[yellow]vncserver stderr: {result.stderr.strip()}[/yellow]")

    # Wait up to 10 seconds for the lock file to appear
    for _ in range(10):
        if os.path.exists(lock_file):
            console.print("[green]✓ VNC display :1 ready[/green]")
            return True
        time.sleep(1)

    console.print("[yellow]VNC did not start within 10s[/yellow]")
    return False


def is_cdp_alive():
    """Check if Chrome's debugging port is responding."""
    try:
        requests.get("http://127.0.0.1:2222/json/version", timeout=2)
        return True
    except Exception:
        return False


def start_chrome_auto():
    """
    Launch Chrome with CDP on port 2222.
    Strategy:
      1. Try with VNC display (:1)  — full rendering, needed for JS-heavy sites
      2. Fall back to headless mode — no VNC needed, lighter
    Returns True when CDP port is confirmed open.
    """
    global chrome_process

    # Kill any stale instance
    subprocess.run(["pkill", "-f", "remote-debugging-port=2222"], capture_output=True)
    time.sleep(1)

    chrome_cmd = find_chrome()
    if not chrome_cmd:
        return False

    user_data_dir = os.path.expanduser('~/chrome-cdp')
    os.makedirs(user_data_dir, exist_ok=True)

    base_flags = [
        chrome_cmd,
        "--remote-debugging-port=2222",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
        "--disable-extensions",
        "--disable-background-networking",
    ]

    # --- Attempt 1: VNC display ---
    vnc_ok = ensure_vnc_display()
    if vnc_ok:
        console.print("[cyan]Launching Chrome with VNC display...[/cyan]")
        env = os.environ.copy()
        env["DISPLAY"] = ":1"
        try:
            chrome_process = subprocess.Popen(
                base_flags,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Wait up to 20 s for CDP port
            for i in range(20):
                time.sleep(1)
                if is_cdp_alive():
                    console.print(f"[green]✓ Chrome ready (VNC mode, {i+1}s)[/green]")
                    return True
                # Check process hasn't crashed
                if chrome_process.poll() is not None:
                    console.print("[yellow]Chrome process exited early, trying headless...[/yellow]")
                    break
            else:
                console.print("[yellow]CDP port not responding after 20s, trying headless...[/yellow]")
        except Exception as e:
            console.print(f"[yellow]VNC launch error: {e}[/yellow]")

    # --- Attempt 2: Headless ---
    console.print("[cyan]Launching Chrome in headless mode...[/cyan]")
    subprocess.run(["pkill", "-f", "remote-debugging-port=2222"], capture_output=True)
    time.sleep(1)

    headless_flags = base_flags + ["--headless=new"]
    try:
        chrome_process = subprocess.Popen(
            headless_flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        for i in range(20):
            time.sleep(1)
            if is_cdp_alive():
                console.print(f"[green]✓ Chrome ready (headless mode, {i+1}s)[/green]")
                return True
            if chrome_process.poll() is not None:
                rc = chrome_process.returncode
                console.print(f"[red]Chrome crashed (exit code {rc})[/red]")
                break
    except Exception as e:
        console.print(f"[red]Headless launch error: {e}[/red]")

    console.print("[red]Failed to start Chrome. Troubleshooting tips:[/red]")
    console.print("[yellow]  • Install chromium: pkg install chromium[/yellow]")
    console.print("[yellow]  • Install VNC: pkg install tigervnc[/yellow]")
    console.print("[yellow]  • Free memory: close other apps[/yellow]")
    return False


# ------------------- CDP helpers (unchanged) -------------------

def get_ws_url():
    try:
        tabs = requests.get("http://127.0.0.1:2222/json/list", timeout=5).json()
        if tabs:
            return tabs[0].get("webSocketDebuggerUrl")
    except Exception:
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
        except Exception:
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
    send_cdp(ws, 1000, "Page.navigate", {"url": url})
    time.sleep(5)
    for _ in range(20):
        pins = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
        if pins and pins > 0:
            console.print(f"[green]Loaded {pins} pins[/green]")
            return True
        time.sleep(1)
    # Return True anyway — page may have loaded without matching selector
    console.print("[yellow]Pin selector not found yet, continuing anyway...[/yellow]")
    return True

def scroll_page_properly(ws, times=10):
    for i in range(times):
        before_count = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length") or 0
        console.print(f"[dim]Scroll {i+1}/{times} - pins so far: {before_count}[/dim]")
        evaluate_cdp(ws, "window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });")
        time.sleep(1)
        evaluate_cdp(ws, "window.dispatchEvent(new Event('scroll')); document.dispatchEvent(new Event('scroll'));")
        time.sleep(1)
        evaluate_cdp(ws, "window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)
        after_count = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length") or 0
        new_pins = after_count - before_count
        if new_pins > 0:
            console.print(f"[green] + {new_pins} new pins[/green]")
        elif after_count == before_count and i > 3:
            console.print("[yellow]No new pins. Stopping early.[/yellow]")
            break
        time.sleep(1)
    final = evaluate_cdp(ws, "document.querySelectorAll('[data-test-id=\"pin\"]').length")
    console.print(f"[bold cyan]Total pins loaded: {final}[/bold cyan]")

def extract_pin_urls(ws):
    pin_urls = evaluate_cdp(ws, """
    (function() {
        let urls = [];
        document.querySelectorAll('a[href*="/pin/"]').forEach(link => {
            let href = link.href;
            if (href && href.includes('/pin/') && !href.includes('/pin/create/')) {
                urls.push(href.split('?')[0]);
            }
        });
        return [...new Set(urls)];
    })()
    """)
    return pin_urls if pin_urls else []

def save_pin_urls(urls, topic):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pin_urls_{topic.replace(' ', '_')}_{timestamp}.txt"
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
            console.print("[red]Could not connect to Chrome CDP[/red]")
            return []
        search_url = f"https://www.pinterest.com/search/pins/?q={quote(topic)}"
        console.print(f"[cyan]Navigating to: {search_url}[/cyan]")
        navigate_cdp(ws, search_url)
        time.sleep(2)
        console.print(f"[cyan]Scrolling {scrolls} times...[/cyan]")
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
        console.print(f"[red]Scrape error: {e}[/red]")
        return []
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass

def scrape_and_save(topic, scrolls=10):
    console.print(f"[bold green]🎬 Scraping Pinterest URLs for: {topic}[/bold green]")

    if not start_chrome_auto():
        console.print("[red]Could not start Chrome. Cannot proceed.[/red]")
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
        console.print(f"[dim]Files: {filename}, {json_file}[/dim]")

        download_choice = Prompt.ask("\nDownload video pins now?", choices=["y", "n"], default="n")
        if download_choice == "y":
            if ensure_ytdlp():
                downloaded = download_videos_from_urls(pin_urls)
                console.print(f"[bold green]Downloaded {downloaded} videos[/bold green]")
    else:
        console.print("[yellow]No pin URLs found[/yellow]")


# ------------------- Menu -------------------

def view_saved_urls():
    if os.path.exists(PIN_URLS_FILE):
        with open(PIN_URLS_FILE, 'r') as f:
            lines = f.read().split('\n')
        recent = '\n'.join(lines[-50:])
        console.print(Panel(recent, title="Recent Pin URLs (last 50 lines)", border_style="cyan"))
    else:
        console.print("[yellow]No saved URLs yet[/yellow]")

def download_videos_menu():
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
            "[bold green]🎬 PINTEREST PIN URL SCRAPER v1.5[/bold green]\nExtracts pin URLs + yt-dlp video downloader",
            border_style="green"
        ))
        console.print("\n[cyan]1.[/cyan] 🔗 Scrape Pin URLs (+ optional video download)")
        console.print("[cyan]2.[/cyan] 📄 View Saved URLs")
        console.print("[cyan]3.[/cyan] ⬇️  Download videos from saved URL file")
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
        console.print("[yellow]Installing websocket-client...[/yellow]")
        subprocess.run([sys.executable, "-m", "pip", "install", "websocket-client"], check=True)
        import websocket  # noqa: F811
    menu()
