#!/usr/bin/env python3
"""
Pinterest Media Scraper - Textual TUI Application
Fixed version with proper error handling
"""

import asyncio
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
from typing import List, Optional

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Button, Input, Static, ListView, ListItem, Label, LoadingIndicator
from textual.screen import Screen
from textual import work
from rich.text import Text

# Constants
PIN_URLS_FILE = "pin_urls.txt"
DOWNLOAD_DIR = "pinterest_downloads"

chrome_process = None

# ------------------- Chrome Setup -------------------

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
    """Find Chrome/Chromium binary"""
    candidates = [
        "chromium", "chromium-browser", "google-chrome",
        os.path.expanduser("~/../usr/bin/chromium"),
        "/data/data/com.termux/files/usr/bin/chromium"
    ]
    for name in candidates:
        path = shutil.which(name) if isinstance(name, str) and '/' not in name else name
        if path and os.path.exists(path):
            return path
    return None

def is_cdp_alive():
    try:
        response = requests.get("http://127.0.0.1:2222/json/version", timeout=2)
        return response.status_code == 200
    except Exception:
        return False

def start_chrome_headless_sync():
    global chrome_process
    subprocess.run(["pkill", "-f", "remote-debugging-port=2222"], capture_output=True)
    time.sleep(1)
    
    chrome_cmd = find_chrome()
    if not chrome_cmd:
        return False
    
    user_data_dir = os.path.expanduser('~/chrome-cdp')
    os.makedirs(user_data_dir, exist_ok=True)
    
    cmd = [
        chrome_cmd,
        "--remote-debugging-port=2222",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080"
    ]
    
    try:
        chrome_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for i in range(20):
            time.sleep(1)
            if is_cdp_alive():
                return True
    except Exception:
        pass
    return False

def get_ws_url():
    try:
        tabs = requests.get("http://127.0.0.1:2222/json/list", timeout=5).json()
        if tabs:
            return tabs[0].get("webSocketDebuggerUrl")
    except Exception:
        pass
    return None

def is_video_pin_sync(pin_url):
    try:
        result = subprocess.run(['yt-dlp', '-j', '--skip-download', pin_url], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False
        info = json.loads(result.stdout)
        if info.get('duration', 0) > 0:
            return True
        return False
    except Exception:
        return False

def is_image_pin_sync(pin_url):
    try:
        result = subprocess.run(['yt-dlp', '-j', '--skip-download', pin_url], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False
        info = json.loads(result.stdout)
        if info.get('thumbnail'):
            return True
        return False
    except Exception:
        return False

def scrape_pinterest_urls_sync(topic, scrolls=10, media_type="both", progress_callback=None):
    """Synchronous scraper - will be run in thread"""
    ws = None
    try:
        ws_url = get_ws_url()
        if not ws_url:
            return []
        
        ws = websocket.create_connection(ws_url, timeout=30)
        
        # Enable domains
        for method in ["Page.enable", "Runtime.enable", "Network.enable"]:
            ws.send(json.dumps({"id": 1, "method": method}))
            time.sleep(0.5)
            try:
                ws.recv()
            except:
                pass
        
        # Navigate to search
        search_url = f"https://www.pinterest.com/search/pins/?q={quote(topic)}"
        ws.send(json.dumps({"id": 1000, "method": "Page.navigate", "params": {"url": search_url}}))
        time.sleep(5)
        
        # Wait for page load
        for _ in range(30):
            ws.send(json.dumps({"id": 100, "method": "Runtime.evaluate", "params": {"expression": "document.readyState", "returnByValue": True}}))
            try:
                res = json.loads(ws.recv())
                if res.get("result", {}).get("result", {}).get("value") == "complete":
                    break
            except:
                pass
            time.sleep(1)
        
        # Collect pin URLs
        pin_urls = set()
        
        for i in range(scrolls):
            if progress_callback:
                progress_callback(i + 1, scrolls)
            
            # Get current pin URLs
            ws.send(json.dumps({
                "id": 200,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """
                        Array.from(document.querySelectorAll('a[href*="/pin/"]'))
                            .map(a => a.href.split('?')[0])
                            .filter(href => href && href.includes('/pin/') && !href.includes('/pin/create/'))
                    """,
                    "returnByValue": True
                }
            }))
            
            try:
                res = json.loads(ws.recv())
                urls = res.get("result", {}).get("result", {}).get("value", [])
                pin_urls.update(urls)
            except:
                pass
            
            # Scroll down
            ws.send(json.dumps({
                "id": 201,
                "method": "Runtime.evaluate",
                "params": {"expression": "window.scrollTo(0, document.body.scrollHeight)"}
            }))
            time.sleep(2)
        
        all_urls = list(pin_urls)
        
        # Filter based on media type
        if media_type == "video":
            filtered = [url for url in all_urls if is_video_pin_sync(url)]
        elif media_type == "image":
            filtered = [url for url in all_urls if is_image_pin_sync(url)]
        else:
            filtered = all_urls
        
        return filtered
        
    except Exception as e:
        print(f"Scrape error: {e}")
        return []
    finally:
        if ws:
            try:
                ws.close()
            except:
                pass


# ------------------- Main Screen -------------------

class MainScreen(Screen):
    """Main application screen"""
    
    CSS = """
    MainScreen {
        background: $surface;
    }
    
    .title {
        text-align: center;
        text-style: bold;
        color: $success;
        padding: 1;
        height: 3;
    }
    
    .subtitle {
        text-align: center;
        color: $text-muted;
        padding-bottom: 1;
        height: 2;
    }
    
    .button-row {
        layout: horizontal;
        align: center middle;
        padding: 1;
        margin: 1;
    }
    
    Button {
        margin: 0 1;
        min-width: 20;
    }
    
    .input-group {
        padding: 1;
        margin: 1 2;
        border: solid $primary;
        background: $surface;
    }
    
    .input-label {
        padding: 0 1;
        color: $primary;
        text-style: bold;
    }
    
    Input {
        margin: 0 1;
        width: 100%;
    }
    
    .media-row {
        layout: horizontal;
        align: center middle;
        padding: 1;
        margin: 0 2;
    }
    
    .media-selected {
        text-align: center;
        padding: 0 1;
        color: $success;
        text-style: bold;
    }
    
    .activity-container {
        border: solid $primary;
        margin: 1;
        padding: 1;
        height: 40%;
        background: $surface;
    }
    
    .activity-log {
        background: $panel;
        padding: 1;
        height: 100%;
        overflow-y: auto;
    }
    
    .section-title {
        padding: 0 1;
        color: $primary;
        text-style: bold;
    }
    
    .hidden {
        display: none;
    }
    
    .progress-text {
        padding: 1;
        color: $warning;
        text-align: center;
    }
    
    .results {
        padding: 1;
        margin: 1;
        border: solid $success;
        overflow-y: auto;
        height: auto;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        yield Container(
            Static("🎬 Pinterest Media Scraper", classes="title"),
            Static("Extract and download videos/images from Pinterest", classes="subtitle"),
            
            # Search topic input
            Vertical(
                Static("🔍 SEARCH TOPIC:", classes="input-label"),
                Input(
                    placeholder="Enter what you want to search (e.g., 3d green screen, nature, art)",
                    id="topic-input",
                    value=""
                ),
                classes="input-group"
            ),
            
            # Scroll count input
            Vertical(
                Static("📜 SCROLL COUNT:", classes="input-label"),
                Input(
                    placeholder="Number of scrolls (10-50, more scrolls = more results)",
                    id="scrolls-input",
                    value="15"
                ),
                classes="input-group"
            ),
            
            # Media type selection
            Static("📺 MEDIA TYPE:", classes="input-label"),
            Horizontal(
                Button("🎬 Videos Only", variant="default", id="media-video", classes="media-btn"),
                Button("🖼️ Images Only", variant="default", id="media-image", classes="media-btn"),
                Button("📦 Both", variant="primary", id="media-both", classes="media-btn"),
                classes="media-row"
            ),
            Static("Selected: 📦 Both (Videos & Images)", id="media-selected", classes="media-selected"),
            
            # Action buttons
            Horizontal(
                Button("▶ START SCRAPING", variant="primary", id="start-btn"),
                Button("📥 DOWNLOAD", variant="success", id="download-btn"),
                Button("📄 HISTORY", variant="default", id="history-btn"),
                Button("🎨 THEME", variant="default", id="theme-btn"),
                Button("❌ EXIT", variant="error", id="exit-btn"),
                classes="button-row"
            ),
            
            LoadingIndicator(id="loading-indicator", classes="hidden"),
            Static("", id="progress-text", classes="progress-text"),
            
            ScrollableContainer(
                Static("Recent Activity:", classes="section-title"),
                Static("✨ Ready to scrape! Enter a search topic above.", id="activity-log", classes="activity-log"),
                classes="activity-container"
            ),
            
            ScrollableContainer(
                Static("", id="results-area", classes="results"),
                id="results-scroll"
            ),
            
            id="main-container"
        )
        
        yield Footer()
    
    def __init__(self):
        super().__init__()
        self.selected_media = "both"
        self.theme_index = 0
        self.themes = [
            ("Default", "$surface"),
            ("Primary", "$primary"),
            ("Success", "$success"),
            ("Warning", "$warning"),
            ("Error", "$error"),
            ("Panel", "$panel"),
        ]
    
    def on_mount(self) -> None:
        """Called when screen mounts"""
        self.update_activity("✅ Application ready! Enter a search topic to begin.")
    
    def update_activity(self, message: str) -> None:
        """Update activity log"""
        try:
            log = self.query_one("#activity-log", Static)
            timestamp = datetime.now().strftime("%H:%M:%S")
            current = log.renderable if hasattr(log, 'renderable') else ""
            new_content = f"[{timestamp}] {message}\n" + str(current)
            log.update(new_content[:3000])
        except Exception:
            pass
    
    def update_results(self, text: str) -> None:
        """Update results area"""
        try:
            results = self.query_one("#results-area", Static)
            results.update(text)
        except Exception:
            pass
    
    # Media selection handlers
    @on(Button.Pressed, "#media-video")
    def select_video(self):
        self.selected_media = "video"
        self.query_one("#media-selected", Static).update("Selected: 🎬 Videos Only")
        self.query_one("#media-video", Button).variant = "primary"
        self.query_one("#media-image", Button).variant = "default"
        self.query_one("#media-both", Button).variant = "default"
        self.update_activity("Media filter changed to: Videos Only")
    
    @on(Button.Pressed, "#media-image")
    def select_image(self):
        self.selected_media = "image"
        self.query_one("#media-selected", Static).update("Selected: 🖼️ Images Only")
        self.query_one("#media-video", Button).variant = "default"
        self.query_one("#media-image", Button).variant = "primary"
        self.query_one("#media-both", Button).variant = "default"
        self.update_activity("Media filter changed to: Images Only")
    
    @on(Button.Pressed, "#media-both")
    def select_both(self):
        self.selected_media = "both"
        self.query_one("#media-selected", Static).update("Selected: 📦 Both (Videos & Images)")
        self.query_one("#media-video", Button).variant = "default"
        self.query_one("#media-image", Button).variant = "default"
        self.query_one("#media-both", Button).variant = "primary"
        self.update_activity("Media filter changed to: Both")
    
    # Theme change handler
    @on(Button.Pressed, "#theme-btn")
    def change_theme(self):
        """Cycle through different background themes"""
        self.theme_index = (self.theme_index + 1) % len(self.themes)
        theme_name, theme_color = self.themes[self.theme_index]
        
        # Apply new background
        container = self.query_one("#main-container", Container)
        container.styles.background = theme_color
        
        self.update_activity(f"Theme changed to: {theme_name}")
    
    # Start scraping handler
    @on(Button.Pressed, "#start-btn")
    def start_scraping(self):
        """Get user input and start scraping"""
        # GET USER INPUT
        topic_input = self.query_one("#topic-input", Input)
        topic = topic_input.value.strip()
        
        # Validate user input
        if not topic:
            self.update_results("[red]❌ ERROR: Please enter a search topic![/red]")
            self.update_activity("❌ No topic entered")
            topic_input.focus()
            return
        
        # Get scroll count
        scrolls_input = self.query_one("#scrolls-input", Input)
        try:
            scrolls = int(scrolls_input.value) if scrolls_input.value else 15
            scrolls = max(1, min(50, scrolls))
        except ValueError:
            scrolls = 15
        
        # Disable button and show loading
        self.query_one("#start-btn", Button).disabled = True
        loading = self.query_one("#loading-indicator", LoadingIndicator)
        loading.remove_class("hidden")
        
        self.update_activity(f"🎯 Starting scrape for: {topic} ({scrolls} scrolls, {self.selected_media})")
        self.update_results(f"[cyan]🔄 Scraping '{topic}'... Please wait[/cyan]\n")
        
        # Run scraper in background thread
        self.run_scraper_worker(topic, scrolls, self.selected_media)
    
    @work(exclusive=True)
    async def run_scraper_worker(self, topic: str, scrolls: int, media_type: str):
        """Run scraper in worker thread"""
        
        def update_progress(current, total):
            self.call_from_thread(self.update_progress_text, f"Scrolling {current}/{total}...")
        
        def update_progress_text(text):
            try:
                self.query_one("#progress-text", Static).update(text)
            except Exception:
                pass
        
        try:
            # Start Chrome
            self.call_from_thread(update_progress_text, "Starting Chrome browser...")
            self.call_from_thread(self.update_activity, "Starting Chrome browser...")
            
            chrome_started = await self.run_in_thread(start_chrome_headless_sync)
            if not chrome_started:
                self.call_from_thread(self.show_error, "Failed to start Chrome. Please install chromium: pkg install chromium")
                return
            
            self.call_from_thread(update_progress_text, "Chrome ready! Scraping pins...")
            
            # Scrape
            pin_urls = await self.run_in_thread(
                scrape_pinterest_urls_sync, topic, scrolls, media_type, update_progress
            )
            
            # Show results
            self.call_from_thread(self.show_scrape_results, topic, pin_urls, media_type)
            
        except Exception as e:
            self.call_from_thread(self.show_error, f"Scraping error: {str(e)}")
    
    def update_progress_text(self, text: str):
        """Update progress display"""
        try:
            self.query_one("#progress-text", Static).update(text)
        except Exception:
            pass
    
    def show_scrape_results(self, topic: str, pin_urls: List[str], media_type: str):
        """Display scraping results"""
        try:
            loading = self.query_one("#loading-indicator", LoadingIndicator)
            loading.add_class("hidden")
            self.query_one("#start-btn", Button).disabled = False
            self.query_one("#progress-text", Static).update("")
        except Exception:
            pass
        
        media_names = {"video": "Videos", "image": "Images", "both": "Videos & Images"}
        
        if pin_urls:
            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pin_urls_{topic.replace(' ', '_')}_{media_type}_{timestamp}.txt"
            
            with open(filename, 'w') as f:
                f.write(f"# Pinterest {media_names[media_type]} URLs for: {topic}\n")
                f.write(f"# Media Type: {media_names[media_type]}\n")
                f.write(f"# Total: {len(pin_urls)}\n")
                f.write(f"# Scraped: {datetime.now().isoformat()}\n\n")
                for url in pin_urls:
                    f.write(f"{url}\n")
            
            # Append to master file
            with open(PIN_URLS_FILE, 'a') as f:
                f.write(f"\n# {topic} - {media_names[media_type]} - {timestamp}\n")
                for url in pin_urls:
                    f.write(f"{url}\n")
            
            results_text = f"[green]✅ SUCCESS! Found {len(pin_urls)} {media_names[media_type].lower()}[/green]\n\n"
            results_text += f"📁 Saved to: {filename}\n\n"
            results_text += f"[bold]First 10 URLs:[/bold]\n"
            for i, url in enumerate(pin_urls[:10], 1):
                results_text += f"  {i}. {url[:80]}...\n"
            
            if len(pin_urls) > 10:
                results_text += f"\n  ... and {len(pin_urls) - 10} more\n"
            
            results_text += f"\n[yellow]💡 Tip: Use the DOWNLOAD button to download these files![/yellow]"
            
            self.update_results(results_text)
            self.update_activity(f"✅ Scraped {len(pin_urls)} {media_names[media_type].lower()} for '{topic}'")
        else:
            results_text = f"[red]❌ No {media_names[media_type].lower()} found for '{topic}'[/red]\n\n"
            results_text += f"[yellow]Suggestions:[/yellow]\n"
            results_text += f"  • Try a different search term\n"
            results_text += f"  • Increase scroll count\n"
            results_text += f"  • Change media type filter\n"
            self.update_results(results_text)
            self.update_activity(f"❌ No results for '{topic}'")
    
    def show_error(self, error: str):
        """Display error message"""
        try:
            loading = self.query_one("#loading-indicator", LoadingIndicator)
            loading.add_class("hidden")
            self.query_one("#start-btn", Button).disabled = False
            self.query_one("#progress-text", Static).update("")
        except Exception:
            pass
        self.update_results(f"[red]❌ ERROR: {error}[/red]")
        self.update_activity(f"❌ Error: {error}")
    
    @on(Button.Pressed, "#download-btn")
    def go_to_download(self):
        """Navigate to download screen"""
        self.app.push_screen(DownloadScreen())
    
    @on(Button.Pressed, "#history-btn")
    def go_to_history(self):
        """Navigate to history screen"""
        self.app.push_screen(HistoryScreen())
    
    @on(Button.Pressed, "#exit-btn")
    def exit_app(self):
        """Exit the application"""
        cleanup()
        self.app.exit()


class DownloadScreen(Screen):
    """Download screen"""
    
    CSS = """
    DownloadScreen {
        background: $surface;
    }
    
    .screen-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 1;
        height: 3;
    }
    
    .button-row {
        layout: horizontal;
        align: center middle;
        padding: 1;
        margin: 1;
    }
    
    Button {
        margin: 0 1;
        min-width: 20;
    }
    
    .file-list {
        margin: 1 2;
        height: 12;
        border: solid $primary;
    }
    
    .results {
        padding: 1;
        margin: 1;
        border: solid $success;
        overflow-y: auto;
        height: 20;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("📥 Download Media", classes="screen-title"),
            Static("Select a file to download:", classes="input-label"),
            ListView(id="file-list", classes="file-list"),
            Horizontal(
                Button("▶ START DOWNLOAD", variant="primary", id="download-btn"),
                Button("◀ BACK", variant="default", id="back-btn"),
                classes="button-row"
            ),
            LoadingIndicator(id="loading", classes="hidden"),
            Static("", id="progress", classes="progress-text"),
            ScrollableContainer(
                Static("", id="results", classes="results"),
                id="results-scroll"
            ),
            id="download-container"
        )
        yield Footer()
    
    def on_mount(self):
        self.load_files()
    
    def load_files(self):
        files = [f for f in os.listdir('.') if f.startswith('pin_urls_') and f.endswith('.txt')]
        files.sort(reverse=True)
        
        list_view = self.query_one("#file-list", ListView)
        list_view.clear()
        
        for f in files:
            size = os.path.getsize(f) / 1024
            item = ListItem(Label(f"📄 {f} ({size:.1f} KB)"))
            list_view.append(item)
        
        if not files:
            self.query_one("#results", Static).update("[yellow]No files found. Scrape some pins first![/yellow]")
    
    @on(Button.Pressed, "#download-btn")
    def start_download(self):
        list_view = self.query_one("#file-list", ListView)
        if not list_view.children or list_view.index is None or list_view.index < 0:
            self.query_one("#results", Static).update("[red]Please select a file first[/red]")
            return
        
        selected = list_view.children[list_view.index]
        filename = selected.query_one(Label).renderable.split(" ")[1].split(" (")[0]
        
        self.query_one("#download-btn", Button).disabled = True
        self.query_one("#loading", LoadingIndicator).remove_class("hidden")
        
        self.run_download(filename)
    
    @work(exclusive=True)
    async def run_download(self, filename: str):
        def update_progress(text):
            self.call_from_thread(self.update_progress_text, text)
        
        update_progress(f"Reading {filename}...")
        
        with open(filename, 'r') as f:
            lines = f.readlines()
        
        urls = [l.strip() for l in lines if l.strip() and not l.startswith('#') and '/pin/' in l]
        
        if not urls:
            self.call_from_thread(self.show_error, "No valid URLs found")
            return
        
        update_progress(f"Found {len(urls)} URLs, checking for videos...")
        
        downloaded = 0
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        
        for i, url in enumerate(urls[:10], 1):  # Limit to 10 for demo
            update_progress(f"Checking {i}/{min(10, len(urls))}...")
            if await self.run_in_thread(is_video_pin_sync, url):
                downloaded += 1
            await asyncio.sleep(0.5)
        
        self.call_from_thread(self.show_results, downloaded, min(10, len(urls)))
    
    def update_progress_text(self, text: str):
        try:
            self.query_one("#progress", Static).update(text)
        except Exception:
            pass
    
    def show_results(self, downloaded: int, total: int):
        try:
            self.query_one("#loading", LoadingIndicator).add_class("hidden")
            self.query_one("#download-btn", Button).disabled = False
        except Exception:
            pass
        self.query_one("#results", Static).update(f"[green]✅ Downloaded {downloaded}/{total} videos to {DOWNLOAD_DIR}/[/green]")
    
    def show_error(self, error: str):
        try:
            self.query_one("#loading", LoadingIndicator).add_class("hidden")
            self.query_one("#download-btn", Button).disabled = False
        except Exception:
            pass
        self.query_one("#results", Static).update(f"[red]❌ {error}[/red]")
    
    @on(Button.Pressed, "#back-btn")
    def go_back(self):
        self.app.pop_screen()


class HistoryScreen(Screen):
    """History screen"""
    
    CSS = """
    HistoryScreen {
        background: $surface;
    }
    
    .screen-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 1;
        height: 3;
    }
    
    .button-row {
        layout: horizontal;
        align: center middle;
        padding: 1;
        margin: 1;
    }
    
    .history-content {
        padding: 1;
        margin: 1;
        border: solid $primary;
        overflow-y: auto;
        height: 80%;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("📄 Scraping History", classes="screen-title"),
            Horizontal(
                Button("🔄 REFRESH", variant="default", id="refresh-btn"),
                Button("◀ BACK", variant="default", id="back-btn"),
                classes="button-row"
            ),
            ScrollableContainer(
                Static("", id="history-content", classes="history-content"),
                id="history-scroll"
            ),
            id="history-container"
        )
        yield Footer()
    
    def on_mount(self):
        self.load_history()
    
    @on(Button.Pressed, "#refresh-btn")
    def load_history(self):
        history_text = ""
        
        if os.path.exists(PIN_URLS_FILE):
            with open(PIN_URLS_FILE, 'r') as f:
                lines = f.readlines()
            
            history_text += f"[cyan]📊 Total entries: {len([l for l in lines if '/pin/' in l])}[/cyan]\n\n"
            history_text += "[bold]Recent scrapes:[/bold]\n\n"
            
            for line in lines[-50:]:
                if line.startswith('# ') and 'URLs for:' in line:
                    history_text += f"\n[yellow]{line.strip()}[/yellow]\n"
                elif '/pin/' in line:
                    history_text += f"  📌 {line.strip()[:80]}...\n"
        else:
            history_text = "[yellow]No history found. Start by scraping some pins![/yellow]"
        
        self.query_one("#history-content", Static).update(history_text)
    
    @on(Button.Pressed, "#back-btn")
    def go_back(self):
        self.app.pop_screen()


# ------------------- Main App -------------------

class PinterestApp(App):
    """Main Textual Application"""
    
    CSS = """
    * {
        scrollbar-color: $primary $surface;
    }
    
    Screen {
        background: $surface;
    }
    """
    
    def __init__(self):
        super().__init__()
        self.main_screen = None
    
    def on_mount(self):
        self.title = "Pinterest Media Scraper"
        self.sub_title = "Extract and download videos/images from Pinterest"
        self.main_screen = MainScreen()
        self.push_screen(self.main_screen)


# ------------------- Entry Point -------------------

def check_dependencies():
    """Check and install required packages"""
    required = ["textual", "requests", "websocket-client"]
    for package in required:
        try:
            __import__(package.replace("-", "_"))
            print(f"✓ {package} found")
        except ImportError:
            print(f"Installing {package}...")
            subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)


if __name__ == "__main__":
    check_dependencies()
    
    # Check for yt-dlp
    try:
        subprocess.run(['yt-dlp', '--version'], capture_output=True, check=True)
        print("✓ yt-dlp found")
    except:
        print("Installing yt-dlp...")
        subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)
    
    # Run app
    app = PinterestApp()
    app.run()
