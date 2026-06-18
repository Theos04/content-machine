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

# Define base directories
TERMUX_HOME = "/data/data/com.termux/files/home"
STORAGE_DOWNLOADS = os.path.join(TERMUX_HOME, "storage/downloads")
DEFAULT_BASE_DIR = STORAGE_DOWNLOADS

# Create downloads directory if it doesn't exist
os.makedirs(STORAGE_DOWNLOADS, exist_ok=True)

SCRAPED_DATA_FILE = "pinterest_scraping_history.json"
PIN_URLS_FILE = "pin_urls.txt"

chrome_process = None


# ------------------- Folder Management -------------------
def sanitize_folder_name(name):
    """Create a safe folder name from topic"""
    # Replace spaces and special chars with underscores
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
    safe_name = re.sub(r'[\s]+', '_', safe_name)
    safe_name = safe_name.strip('_')
    return safe_name.lower()

def create_topic_folder(topic, base_dir=None):
    """Create folder structure for a topic"""
    if base_dir is None:
        base_dir = DEFAULT_BASE_DIR
    
    safe_topic = sanitize_folder_name(topic)
    
    # Create main topic folder
    topic_folder = os.path.join(base_dir, safe_topic)
    os.makedirs(topic_folder, exist_ok=True)
    
    # Create subfolders for organization
    subfolders = {
        'videos': os.path.join(topic_folder, 'videos'),
        'urls': os.path.join(topic_folder, 'urls'),
        'metadata': os.path.join(topic_folder, 'metadata')
    }
    
    for subfolder in subfolders.values():
        os.makedirs(subfolder, exist_ok=True)
    
    console.print(f"[green]✓ Created folder: {topic_folder}[/green]")
    
    return {
        'root': topic_folder,
        'videos': subfolders['videos'],
        'urls': subfolders['urls'],
        'metadata': subfolders['metadata'],
        'safe_name': safe_topic
    }

def get_existing_topics(base_dir=None):
    """Get list of existing topic folders"""
    if base_dir is None:
        base_dir = DEFAULT_BARES_DIR
    
    if not os.path.exists(base_dir):
        return []
    
    topics = []
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path):
            # Check if it has our structure (videos/urls/metadata subfolders)
            if all(os.path.exists(os.path.join(item_path, sub)) for sub in ['videos', 'urls', 'metadata']):
                topics.append(item)
            else:
                # Legacy folder or other folder
                topics.append(item)
    
    return topics

def save_pin_urls_to_topic(urls, topic, topic_folders):
    """Save pin URLs to topic-specific folder"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save to urls subfolder
    urls_filename = f"pin_urls_{timestamp}.txt"
    urls_filepath = os.path.join(topic_folders['urls'], urls_filename)
    
    with open(urls_filepath, 'w') as f:
        f.write(f"# Pinterest Pin URLs for: {topic}\n")
        f.write(f"# Total: {len(urls)}\n")
        f.write(f"# Scraped: {datetime.now().isoformat()}\n\n")
        for url in urls:
            f.write(f"{url}\n")
    
    # Save JSON metadata
    json_filename = f"metadata_{timestamp}.json"
    json_filepath = os.path.join(topic_folders['metadata'], json_filename)
    
    with open(json_filepath, 'w') as f:
        json.dump({
            "topic": topic,
            "timestamp": datetime.now().isoformat(),
            "total": len(urls),
            "urls": urls
        }, f, indent=2)
    
    # Also save a combined file in root for quick access (optional)
    master_file = os.path.join(topic_folders['root'], f"{topic_folders['safe_name']}_all_urls.txt")
    with open(master_file, 'w') as f:
        for url in urls:
            f.write(f"{url}\n")
    
    # Update global PIN_URLS_FILE (for backward compatibility)
    if os.path.exists(PIN_URLS_FILE):
        with open(PIN_URLS_FILE, 'a') as f:
            f.write(f"\n# {topic} - {timestamp}\n")
            for url in urls:
                f.write(f"{url}\n")
    else:
        with open(PIN_URLS_FILE, 'w') as f:
            f.write(f"# {topic} - {timestamp}\n")
            for url in urls:
                f.write(f"{url}\n")
    
    console.print(f"[green]✓ Saved {len(urls)} pin URLs to {topic_folders['urls']}[/green]")
    console.print(f"[green]✓ Metadata saved to {topic_folders['metadata']}[/green]")
    
    return urls_filepath, json_filepath


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

def download_pin_video(pin_url, output_dir='downloads', topic_info=None):
    """Download video to specified directory with better organization"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Create a filename pattern that includes topic if available
    if topic_info and 'safe_name' in topic_info:
        filename_template = f'{output_dir}/%(title)s_[{topic_info["safe_name"]}].%(ext)s'
    else:
        filename_template = f'{output_dir}/%(title)s.%(ext)s'
    
    cmd = [
        'yt-dlp',
        '-o', filename_template,
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

def download_videos_from_urls(urls, output_dir='downloads', topic_info=None):
    """Download videos with optional topic organization"""
    if not ensure_ytdlp():
        console.print("[red]Cannot proceed without yt-dlp[/red]")
        return 0
    
    # If topic_info is provided, use the videos subfolder
    if topic_info and 'videos' in topic_info:
        output_dir = topic_info['videos']
        console.print(f"[cyan]📁 Downloading to: {output_dir}[/cyan]")
    
    downloaded = 0
    total = len(urls)
    for i, url in enumerate(urls, 1):
        console.print(f"[cyan]Checking {i}/{total}: {url}[/cyan]")
        if is_video_pin(url):
            console.print("[green]✓ Video detected, downloading...[/green]")
            if download_pin_video(url, output_dir, topic_info):
                downloaded += 1
            time.sleep(1)
        else:
            console.print("[yellow]✗ Not a video pin, skipping[/yellow]")
    return downloaded

def download_from_file(file_path, output_dir='downloads', topic_info=None):
    """Download videos from a URL file, optionally using topic organization"""
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
    downloaded = download_videos_from_urls(urls, output_dir, topic_info)
    console.print(f"[bold green]Downloaded {downloaded} videos[/bold green]")
    return downloaded


# ------------------- Chrome startup -------------------
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
    """Start VNC server on :1 and wait until the display is actually usable."""
    display = ":1"
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
    """Launch Chrome with CDP on port 2222."""
    global chrome_process
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
    # Attempt 1: VNC display
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
            for i in range(20):
                time.sleep(1)
                if is_cdp_alive():
                    console.print(f"[green]✓ Chrome ready (VNC mode, {i+1}s)[/green]")
                    return True
                if chrome_process.poll() is not None:
                    console.print("[yellow]Chrome process exited early, trying headless...[/yellow]")
                    break
            else:
                console.print("[yellow]CDP port not responding after 20s, trying headless...[/yellow]")
        except Exception as e:
            console.print(f"[yellow]VNC launch error: {e}[/yellow]")
    # Attempt 2: Headless
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


# ------------------- CDP helpers -------------------
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

def scrape_and_save(topic, scrolls=10, auto_download=True):
    """Main scraping function with organized folder structure"""
    console.print(f"[bold green]🎬 Scraping Pinterest URLs for: {topic}[/bold green]")
    
    # Create organized folder structure for this topic
    console.print(f"[cyan]📁 Setting up folder structure in {DEFAULT_BASE_DIR}...[/cyan]")
    topic_folders = create_topic_folder(topic)
    
    if not start_chrome_auto():
        console.print("[red]Could not start Chrome. Cannot proceed.[/red]")
        return
    
    time.sleep(2)
    pin_urls = scrape_pinterest_urls(topic, scrolls)
    
    if pin_urls:
        # Save URLs to topic-specific folders
        urls_file, json_file = save_pin_urls_to_topic(pin_urls, topic, topic_folders)
        
        console.print(f"\n[bold green]✓ Success! {len(pin_urls)} pin URLs saved[/bold green]")
        console.print(f"[dim]Root folder: {topic_folders['root']}[/dim]")
        console.print(f"[dim]URLs folder: {topic_folders['urls']}[/dim]")
        console.print(f"[dim]Metadata folder: {topic_folders['metadata']}[/dim]")
        
        # Show storage info
        storage_info = shutil.disk_usage(DEFAULT_BASE_DIR)
        free_gb = storage_info.free / (1024**3)
        console.print(f"[dim]Free space: {free_gb:.2f} GB[/dim]")
        
        # Ask about download if auto_download is False or confirm
        if auto_download:
            download_choice = "y"
        else:
            download_choice = Prompt.ask("\nDownload video pins now?", choices=["y", "n"], default="y")
        
        if download_choice == "y":
            if ensure_ytdlp():
                downloaded = download_videos_from_urls(pin_urls, topic_folders['videos'], topic_folders)
                console.print(f"[bold green]✓ Downloaded {downloaded} videos to {topic_folders['videos']}[/bold green]")
                
                # Show final summary
                console.print(Panel.fit(
                    f"[bold green]COMPLETED![/bold green]\n\n"
                    f"Topic: {topic}\n"
                    f"URLs scraped: {len(pin_urls)}\n"
                    f"Videos downloaded: {downloaded}\n\n"
                    f"📁 Location: {topic_folders['root']}",
                    border_style="green"
                ))
    else:
        console.print("[yellow]No pin URLs found[/yellow]")


# ------------------- Menu -------------------
def view_saved_topics():
    """Display all saved topics and their contents"""
    topics = get_existing_topics()
    
    if not topics:
        console.print("[yellow]No saved topics found[/yellow]")
        return
    
    console.print("[cyan]📁 Saved Topics:[/cyan]")
    for i, topic in enumerate(topics, 1):
        topic_path = os.path.join(DEFAULT_BASE_DIR, topic)
        
        # Get stats
        videos_dir = os.path.join(topic_path, 'videos') if os.path.exists(os.path.join(topic_path, 'videos')) else None
        urls_dir = os.path.join(topic_path, 'urls') if os.path.exists(os.path.join(topic_path, 'urls')) else None
        
        video_count = len([f for f in os.listdir(videos_dir) if f.endswith(('.mp4', '.webm', '.mov'))]) if videos_dir and os.path.exists(videos_dir) else 0
        url_files = len([f for f in os.listdir(urls_dir) if f.endswith('.txt')]) if urls_dir and os.path.exists(urls_dir) else 0
        
        console.print(f"  {i}. [cyan]{topic}[/cyan] - {video_count} videos, {url_files} URL files")
    
    choice = Prompt.ask("\nEnter topic number to view details (or 'q' to cancel)", default="q")
    if choice.lower() == 'q':
        return
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(topics):
            topic = topics[idx]
            topic_path = os.path.join(DEFAULT_BASE_DIR, topic)
            
            # Show detailed view
            console.print(Panel.fit(
                f"[bold cyan]Topic: {topic}[/bold cyan]\n"
                f"📁 Path: {topic_path}",
                border_style="cyan"
            ))
            
            # Show URL files
            urls_dir = os.path.join(topic_path, 'urls')
            if os.path.exists(urls_dir):
                url_files = [f for f in os.listdir(urls_dir) if f.endswith('.txt')]
                if url_files:
                    console.print("\n[cyan]📄 URL Files:[/cyan]")
                    for f in url_files[-5:]:  # Show last 5
                        file_path = os.path.join(urls_dir, f)
                        with open(file_path, 'r') as file:
                            lines = file.readlines()
                            url_count = len([l for l in lines if l.strip() and not l.startswith('#') and '/pin/' in l])
                        console.print(f"  • {f} ({url_count} URLs)")
            
            # Show videos
            videos_dir = os.path.join(topic_path, 'videos')
            if os.path.exists(videos_dir):
                videos = [f for f in os.listdir(videos_dir) if f.endswith(('.mp4', '.webm', '.mov'))]
                if videos:
                    console.print(f"\n[cyan]🎬 Videos ({len(videos)}):[/cyan]")
                    for v in videos[-10:]:  # Show last 10
                        file_path = os.path.join(videos_dir, v)
                        size_mb = os.path.getsize(file_path) / (1024*1024)
                        console.print(f"  • {v} ({size_mb:.1f} MB)")
                    if len(videos) > 10:
                        console.print(f"  ... and {len(videos)-10} more")
        else:
            console.print("[red]Invalid selection[/red]")
    except ValueError:
        console.print("[red]Invalid input[/red]")

def view_saved_urls():
    """Legacy view - shows global URL file"""
    if os.path.exists(PIN_URLS_FILE):
        with open(PIN_URLS_FILE, 'r') as f:
            lines = f.read().split('\n')
        recent = '\n'.join(lines[-50:])
        console.print(Panel(recent, title="Recent Pin URLs (last 50 lines)", border_style="cyan"))
    else:
        console.print("[yellow]No saved URLs yet[/yellow]")

def download_videos_menu():
    """Enhanced download menu with topic selection"""
    console.print("[cyan]📁 Select download source:[/cyan]")
    console.print("  1. Download from a saved topic folder")
    console.print("  2. Download from a specific URL file")
    
    choice = Prompt.ask("Choice", choices=["1", "2"], default="1")
    
    if choice == "1":
        topics = get_existing_topics()
        if not topics:
            console.print("[yellow]No saved topics found[/yellow]")
            return
        
        console.print("\n[cyan]Available topics:[/cyan]")
        for i, topic in enumerate(topics, 1):
            topic_path = os.path.join(DEFAULT_BASE_DIR, topic)
            videos_dir = os.path.join(topic_path, 'videos')
            video_count = len([f for f in os.listdir(videos_dir) if f.endswith(('.mp4', '.webm', '.mov'))]) if os.path.exists(videos_dir) else 0
            console.print(f"  {i}. [cyan]{topic}[/cyan] - {video_count} videos already downloaded")
        
        topic_choice = Prompt.ask("Select topic number (or 'q' to cancel)", default="q")
        if topic_choice.lower() == 'q':
            return
        
        try:
            idx = int(topic_choice) - 1
            if 0 <= idx < len(topics):
                topic = topics[idx]
                topic_path = os.path.join(DEFAULT_BASE_DIR, topic)
                
                # Find latest URL file
                urls_dir = os.path.join(topic_path, 'urls')
                if os.path.exists(urls_dir):
                    url_files = [f for f in os.listdir(urls_dir) if f.endswith('.txt')]
                    if url_files:
                        latest_file = sorted(url_files)[-1]
                        file_path = os.path.join(urls_dir, latest_file)
                        
                        console.print(f"[cyan]Using URL file: {latest_file}[/cyan]")
                        topic_info = {
                            'root': topic_path,
                            'videos': os.path.join(topic_path, 'videos'),
                            'urls': urls_dir,
                            'metadata': os.path.join(topic_path, 'metadata'),
                            'safe_name': topic
                        }
                        downloaded = download_from_file(file_path, topic_info['videos'], topic_info)
                        console.print(f"[bold green]Downloaded {downloaded} videos to {topic_info['videos']}[/bold green]")
                    else:
                        console.print("[yellow]No URL files found in this topic[/yellow]")
                else:
                    console.print("[yellow]No urls directory found[/yellow]")
            else:
                console.print("[red]Invalid selection[/red]")
        except ValueError:
            console.print("[red]Invalid input[/red]")
    
    else:  # choice == "2"
        files = [f for f in os.listdir('.') if f.startswith('pin_urls_') and f.endswith('.txt')]
        if not files:
            console.print("[yellow]No pin URL files found in current directory[/yellow]")
            return
        console.print("\n[cyan]Available URL files:[/cyan]")
        for i, f in enumerate(files, 1):
            console.print(f"  {i}. {f}")
        file_choice = Prompt.ask("Select file number (or 'q' to cancel)", default="q")
        if file_choice.lower() == 'q':
            return
        try:
            idx = int(file_choice) - 1
            if 0 <= idx < len(files):
                download_from_file(files[idx])
            else:
                console.print("[red]Invalid selection[/red]")
        except ValueError:
            console.print("[red]Invalid input[/red]")

def show_storage_info():
    """Display storage information for downloads directory"""
    try:
        usage = shutil.disk_usage(DEFAULT_BASE_DIR)
        total_gb = usage.total / (1024**3)
        used_gb = (usage.total - usage.free) / (1024**3)
        free_gb = usage.free / (1024**3)
        
        console.print(Panel(
            f"[cyan]Downloads Directory: {DEFAULT_BASE_DIR}[/cyan]\n"
            f"Total: {total_gb:.2f} GB\n"
            f"Used: {used_gb:.2f} GB\n"
            f"Free: {free_gb:.2f} GB\n"
            f"Usage: {(used_gb/total_gb)*100:.1f}%",
            title="💾 Storage Info",
            border_style="cyan"
        ))
    except Exception as e:
        console.print(f"[red]Could not get storage info: {e}[/red]")

def menu():
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold green]🎬 PINTEREST PIN URL SCRAPER v2.0[/bold green]\n"
            "Organized downloads with topic-based folders",
            border_style="green"
        ))
        
        # Show storage info in menu
        try:
            free_gb = shutil.disk_usage(DEFAULT_BASE_DIR).free / (1024**3)
            console.print(f"[dim]💾 Free space: {free_gb:.2f} GB → {DEFAULT_BASE_DIR}[/dim]")
        except:
            pass
        
        console.print("\n[cyan]1.[/cyan] 🔍 Scrape New Topic (auto-save to topic folder)")
        console.print("[cyan]2.[/cyan] 📁 View Saved Topics & Content")
        console.print("[cyan]3.[/cyan] ⬇️  Download Videos to Topic Folder")
        console.print("[cyan]4.[/cyan] 📄 View Legacy URL File")
        console.print("[cyan]5.[/cyan] 💾 Show Storage Info")
        console.print("[cyan]6.[/cyan] 🚪 Exit")
        
        choice = Prompt.ask("\nChoice", choices=["1", "2", "3", "4", "5", "6"])
        
        if choice == "1":
            topic = Prompt.ask("Search topic", default="explosion green screen")
            scrolls = int(Prompt.ask("Number of scrolls", default="15"))
            auto_dl = Prompt.ask("Auto-download videos?", choices=["y", "n"], default="y") == "y"
            scrape_and_save(topic, scrolls, auto_dl)
        
        elif choice == "2":
            view_saved_topics()
        
        elif choice == "3":
            download_videos_menu()
        
        elif choice == "4":
            view_saved_urls()
        
        elif choice == "5":
            show_storage_info()
        
        elif choice == "6":
            cleanup()
            console.print("[bold red]Goodbye![/bold red]")
            break
        
        if choice != "6":
            Prompt.ask("\nPress Enter...", default="")


if __name__ == "__main__":
    try:
        import websocket
    except ImportError:
        console.print("[yellow]Installing websocket-client...[/yellow]")
        subprocess.run([sys.executable, "-m", "pip", "install", "websocket-client"], check=True)
        import websocket  # noqa: F811
    
    # Ensure downloads base directory exists
    os.makedirs(DEFAULT_BASE_DIR, exist_ok=True)
    console.print(f"[green]✓ Base downloads directory: {DEFAULT_BASE_DIR}[/green]")
    
    menu()
