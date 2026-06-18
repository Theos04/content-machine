from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.syntax import Syntax
import subprocess
import os
import time
import json
import yt_dlp
from datetime import datetime
from pathlib import Path
import shutil

console = Console()
SCRAPED_DATA_FILE = "pinterest_scraping_history.json"
GREEN_SCREEN_DIR = "green_screen_videos"

def ensure_green_screen_dir():
    """Create green screen directory if it doesn't exist"""
    if not os.path.exists(GREEN_SCREEN_DIR):
        os.makedirs(GREEN_SCREEN_DIR)
        console.print(f"[green]Created directory: {GREEN_SCREEN_DIR}[/green]")

def extract_metadata(url):
    """Extract metadata from video URL using yt-dlp"""
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            metadata = {
                "title": info.get('title', 'Unknown'),
                "uploader": info.get('uploader', 'Unknown'),
                "duration": info.get('duration', 0),
                "view_count": info.get('view_count', 0),
                "description": info.get('description', '')[:200],
                "upload_date": info.get('upload_date', 'Unknown'),
                "tags": info.get('tags', [])[:5],
            }
            return metadata
    except Exception as e:
        console.print(f"[red]Error extracting metadata: {e}[/red]")
        return None

def download_videos_from_urls(urls, topic):
    """Download videos using yt-dlp with metadata extraction"""
    ensure_green_screen_dir()
    
    downloaded_files = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        
        for idx, url in enumerate(urls, 1):
            task = progress.add_task(f"[cyan]Downloading {idx}/{len(urls)}: {topic} video...", total=None)
            
            # First extract metadata
            metadata = extract_metadata(url)
            
            # Create filename from metadata
            if metadata and metadata['title'] != 'Unknown':
                # Sanitize filename
                safe_title = "".join(c for c in metadata['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                filename = f"{safe_title}_{idx}.mp4"
            else:
                filename = f"{topic.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx}.mp4"
            
            # Save metadata to JSON file alongside video
            metadata_file = os.path.join(GREEN_SCREEN_DIR, filename.replace('.mp4', '_metadata.json'))
            
            ydl_opts = {
                "merge_output_format": "mp4",
                "outtmpl": os.path.join(GREEN_SCREEN_DIR, filename.replace('.mp4', '')),
                "quiet": True,
                "no_warnings": True,
            }
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                # Save metadata
                if metadata:
                    with open(metadata_file, 'w') as f:
                        json.dump(metadata, f, indent=2)
                
                downloaded_files.append({
                    "url": url,
                    "filename": filename,
                    "metadata": metadata,
                    "downloaded_at": datetime.now().isoformat()
                })
                
                progress.update(task, completed=True)
                console.print(f"[green]✅ Downloaded: {filename}[/green]")
                
            except Exception as e:
                console.print(f"[red]Error downloading {url}: {e}[/red]")
                progress.update(task, completed=True)
    
    return downloaded_files

def scrape_and_download_pinterest(topic, num_videos):
    """Scrape Pinterest for green screen videos and download them"""
    console.print(f"[bold green]🎬 Scraping Pinterest for '{topic}' green screen videos...[/bold green]")
    
    # This is where you'd implement actual Pinterest scraping
    # For demo, using your existing URL pattern
    console.print("[yellow]Searching Pinterest for green screen videos...[/yellow]")
    
    # Simulated URL discovery (replace with actual scraping)
    # In reality, you would scrape Pinterest using requests/beautifulsoup or Selenium
    base_url_pattern = "https://v1.pinimg.com/videos/iht/hls/"
    
    # For demonstration, using a sample of your existing URLs
    sample_urls = [
        "https://v1.pinimg.com/videos/iht/hls/81/74/5a/81745ac8a567aa09297017ab2c09f1df.m3u8",
        "https://v1.pinimg.com/videos/iht/hls/63/09/2c/63092c8b7e7d32ff802afa08fb317851.m3u8",
        "https://v1.pinimg.com/videos/iht/hls/b1/14/67/b1146754a2d140497c40e94ab03ca4d3.m3u8",
        "https://v1.pinimg.com/videos/iht/hls/bf/da/ce/bfdace8fcd44bb7b4ed3ccbe48fe1a5e_v2.m3u8",
    ]
    
    # Limit to requested number
    urls_to_download = sample_urls[:int(num_videos)]
    
    console.print(f"[green]Found {len(urls_to_download)} videos matching '{topic}'[/green]")
    
    # Download videos with metadata
    downloaded = download_videos_from_urls(urls_to_download, topic)
    
    # Save session
    session_data = {
        "timestamp": datetime.now().isoformat(),
        "topic": topic,
        "num_videos_requested": num_videos,
        "num_downloaded": len(downloaded),
        "downloaded_files": downloaded,
        "status": "completed"
    }
    
    save_scraping_session(session_data)
    
    console.print(f"[bold green]✅ Successfully downloaded {len(downloaded)} videos to {GREEN_SCREEN_DIR}/[/bold green]")

def view_recent_json():
    """View the most recent JSON history file"""
    if os.path.exists(SCRAPED_DATA_FILE):
        with open(SCRAPED_DATA_FILE, 'r') as f:
            data = json.load(f)
        
        if data:
            console.print(Panel("[bold cyan]📄 RECENT SCRAPING HISTORY (JSON)[/bold cyan]", border_style="cyan"))
            
            # Show last session
            last_session = data[-1]
            
            # Pretty print JSON
            json_str = json.dumps(last_session, indent=2, default=str)
            syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
            console.print(syntax)
            
            # Also show as table for readability
            console.print("\n[bold green]📊 Summary:[/bold green]")
            table = Table(title="Latest Session Details")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="yellow")
            
            table.add_row("Topic", last_session.get('topic', 'N/A'))
            table.add_row("Timestamp", last_session.get('timestamp', 'N/A')[:19])
            table.add_row("Videos Requested", str(last_session.get('num_videos_requested', 'N/A')))
            table.add_row("Videos Downloaded", str(last_session.get('num_downloaded', 'N/A')))
            table.add_row("Status", last_session.get('status', 'N/A'))
            
            console.print(table)
        else:
            console.print("[yellow]No history found[/yellow]")
    else:
        console.print("[red]No JSON history file found[/red]")

def open_and_rename_videos():
    """Open downloaded videos and rename based on metadata"""
    ensure_green_screen_dir()
    
    videos = [f for f in os.listdir(GREEN_SCREEN_DIR) if f.endswith('.mp4')]
    
    if not videos:
        console.print("[red]No videos found to rename[/red]")
        return
    
    console.print(Panel("[bold cyan]🎬 VIDEO RENAMING TOOL[/bold cyan]", border_style="cyan"))
    
    # List all videos
    table = Table(title="Videos Available for Renaming")
    table.add_column("#", style="cyan")
    table.add_column("Current Filename", style="yellow")
    table.add_column("Has Metadata", style="green")
    
    video_metadata_pairs = []
    for idx, video in enumerate(videos, 1):
        metadata_file = video.replace('.mp4', '_metadata.json')
        has_metadata = os.path.exists(os.path.join(GREEN_SCREEN_DIR, metadata_file))
        
        table.add_row(str(idx), video, "✅" if has_metadata else "❌")
        video_metadata_pairs.append((video, has_metadata))
    
    console.print(table)
    
    choice = Prompt.ask("\n[bold]Enter video number to rename[/bold] (or 'all' to rename all, 'q' to quit)")
    
    if choice.lower() == 'q':
        return
    elif choice.lower() == 'all':
        rename_all_videos(videos, video_metadata_pairs)
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(videos):
                rename_single_video(videos[idx], video_metadata_pairs[idx][1])
            else:
                console.print("[red]Invalid video number[/red]")
        except ValueError:
            console.print("[red]Invalid input[/red]")

def rename_single_video(video_filename, has_metadata):
    """Rename a single video based on its metadata"""
    video_path = os.path.join(GREEN_SCREEN_DIR, video_filename)
    
    if has_metadata:
        metadata_file = video_filename.replace('.mp4', '_metadata.json')
        metadata_path = os.path.join(GREEN_SCREEN_DIR, metadata_file)
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        # Suggest new name based on metadata
        suggested_name = f"{metadata.get('title', 'video')}_{metadata.get('upload_date', 'unknown')}.mp4"
        # Sanitize
        suggested_name = "".join(c for c in suggested_name if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
        
        console.print(f"[cyan]Current name:[/cyan] {video_filename}")
        console.print(f"[green]Suggested name:[/green] {suggested_name}")
        
        rename = Prompt.ask("[bold]Rename to suggested name?[/bold]", choices=["yes", "no", "custom"], default="yes")
        
        if rename == "yes":
            new_path = os.path.join(GREEN_SCREEN_DIR, suggested_name)
            os.rename(video_path, new_path)
            console.print(f"[green]✅ Renamed to: {suggested_name}[/green]")
        elif rename == "custom":
            custom_name = Prompt.ask("[bold]Enter custom name[/bold] (without .mp4)")
            custom_name = f"{custom_name}.mp4"
            new_path = os.path.join(GREEN_SCREEN_DIR, custom_name)
            os.rename(video_path, new_path)
            console.print(f"[green]✅ Renamed to: {custom_name}[/green]")
    else:
        console.print("[yellow]No metadata available for this video[/yellow]")
        custom_name = Prompt.ask("[bold]Enter new name[/bold] (without .mp4)")
        custom_name = f"{custom_name}.mp4"
        new_path = os.path.join(GREEN_SCREEN_DIR, custom_name)
        os.rename(video_path, new_path)
        console.print(f"[green]✅ Renamed to: {custom_name}[/green]")

def rename_all_videos(videos, video_metadata_pairs):
    """Rename all videos automatically using metadata"""
    renamed_count = 0
    for video, has_metadata in video_metadata_pairs:
        if has_metadata:
            metadata_file = video.replace('.mp4', '_metadata.json')
            metadata_path = os.path.join(GREEN_SCREEN_DIR, metadata_file)
            
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            new_name = f"{metadata.get('title', 'video')}_{metadata.get('upload_date', datetime.now().strftime('%Y%m%d'))}.mp4"
            new_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
            
            old_path = os.path.join(GREEN_SCREEN_DIR, video)
            new_path = os.path.join(GREEN_SCREEN_DIR, new_name)
            
            # Avoid duplicate names
            if os.path.exists(new_path):
                base, ext = os.path.splitext(new_name)
                new_name = f"{base}_{datetime.now().strftime('%H%M%S')}{ext}"
                new_path = os.path.join(GREEN_SCREEN_DIR, new_name)
            
            os.rename(old_path, new_path)
            renamed_count += 1
            console.print(f"[green]Renamed: {video} → {new_name}[/green]")
    
    console.print(f"[bold green]✅ Renamed {renamed_count} videos[/bold green]")

def play_video():
    """Play a downloaded video"""
    ensure_green_screen_dir()
    
    videos = [f for f in os.listdir(GREEN_SCREEN_DIR) if f.endswith('.mp4')]
    
    if not videos:
        console.print("[red]No videos found to play[/red]")
        return
    
    table = Table(title="🎥 Available Videos")
    table.add_column("#", style="cyan")
    table.add_column("Filename", style="green")
    table.add_column("Size", style="yellow")
    
    for idx, video in enumerate(videos, 1):
        size = os.path.getsize(f"{GREEN_SCREEN_DIR}/{video}")
        size_mb = size / (1024 * 1024)
        table.add_row(str(idx), video, f"{size_mb:.2f} MB")
    
    console.print(table)
    
    choice = Prompt.ask("[bold]Enter video number to play[/bold] (or 'q' to quit)")
    
    if choice.lower() != 'q':
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(videos):
                video_path = os.path.join(GREEN_SCREEN_DIR, videos[idx])
                # Use system default player
                if shutil.which('vlc'):
                    subprocess.Popen(['vlc', video_path])
                elif shutil.which('mpv'):
                    subprocess.Popen(['mpv', video_path])
                elif shutil.which('xdg-open'):
                    subprocess.Popen(['xdg-open', video_path])
                else:
                    console.print("[red]No video player found. Please install vlc, mpv, or use xdg-open[/red]")
            else:
                console.print("[red]Invalid video number[/red]")
        except ValueError:
            console.print("[red]Invalid input[/red]")

def view_video_metadata():
    """View metadata for a specific video"""
    ensure_green_screen_dir()
    
    videos = [f for f in os.listdir(GREEN_SCREEN_DIR) if f.endswith('.mp4')]
    metadata_files = [f for f in os.listdir(GREEN_SCREEN_DIR) if f.endswith('_metadata.json')]
    
    if not metadata_files:
        console.print("[yellow]No metadata files found[/yellow]")
        return
    
    table = Table(title="Videos with Metadata")
    table.add_column("#", style="cyan")
    table.add_column("Video File", style="green")
    
    for idx, video in enumerate(videos, 1):
        metadata_file = video.replace('.mp4', '_metadata.json')
        if os.path.exists(os.path.join(GREEN_SCREEN_DIR, metadata_file)):
            table.add_row(str(idx), video)
    
    console.print(table)
    
    choice = Prompt.ask("[bold]Enter video number to view metadata[/bold] (or 'q' to quit)")
    
    if choice.lower() != 'q':
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(videos):
                video = videos[idx]
                metadata_file = video.replace('.mp4', '_metadata.json')
                metadata_path = os.path.join(GREEN_SCREEN_DIR, metadata_file)
                
                if os.path.exists(metadata_path):
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                    
                    # Display metadata in a nice table
                    meta_table = Table(title=f"📋 Metadata for {video}")
                    meta_table.add_column("Field", style="cyan")
                    meta_table.add_column("Value", style="yellow")
                    
                    for key, value in metadata.items():
                        if isinstance(value, list):
                            value = ", ".join(str(v) for v in value[:3])
                        meta_table.add_row(key, str(value))
                    
                    console.print(meta_table)
                else:
                    console.print("[red]No metadata file found[/red]")
        except ValueError:
            console.print("[red]Invalid input[/red]")

def list_downloaded_videos():
    """List all downloaded green screen videos with options"""
    ensure_green_screen_dir()
    
    videos = [f for f in os.listdir(GREEN_SCREEN_DIR) if f.endswith('.mp4')]
    
    if videos:
        table = Table(title=f"📹 Green Screen Videos ({len(videos)} files)")
        table.add_column("#", style="cyan")
        table.add_column("Filename", style="green")
        table.add_column("Size", style="yellow")
        table.add_column("Metadata", style="magenta")
        
        for idx, video in enumerate(videos, 1):
            size = os.path.getsize(f"{GREEN_SCREEN_DIR}/{video}")
            size_mb = size / (1024 * 1024)
            metadata_file = video.replace('.mp4', '_metadata.json')
            has_metadata = "✅" if os.path.exists(os.path.join(GREEN_SCREEN_DIR, metadata_file)) else "❌"
            table.add_row(str(idx), video, f"{size_mb:.2f} MB", has_metadata)
        
        console.print(table)
        
        # Show submenu for video actions
        console.print("\n[yellow]Available actions:[/yellow]")
        console.print("  • Select number to play")
        console.print("  • 'rename' to rename videos")
        console.print("  • 'meta' to view metadata")
        console.print("  • 'q' to go back")
        
        action = Prompt.ask("[bold]Action[/bold]", default="q")
        
        if action.lower() == 'rename':
            open_and_rename_videos()
        elif action.lower() == 'meta':
            view_video_metadata()
        elif action.isdigit():
            idx = int(action) - 1
            if 0 <= idx < len(videos):
                video_path = os.path.join(GREEN_SCREEN_DIR, videos[idx])
                if shutil.which('vlc'):
                    subprocess.Popen(['vlc', video_path])
                elif shutil.which('mpv'):
                    subprocess.Popen(['mpv', video_path])
                else:
                    console.print("[red]No video player found[/red]")
    else:
        console.print("[yellow]No videos downloaded yet[/yellow]")

def start_vnc():
    env = os.environ.copy()
    env["DISPLAY"] = ":1"
    result = subprocess.run(["vncserver", ":1"], env=env, capture_output=True, text=True)
    if "already running" in result.stdout:
        console.print("[yellow]VNC already running on :1[/yellow]")
    else:
        console.print("[green]VNC started on :1[/green]")
    time.sleep(2)
    
    topic = Prompt.ask("[bold cyan]What topic do you want to scrape from Pinterest[/bold cyan]")
    
    if topic:
        download_videos = Prompt.ask("[bold cyan]Download videos automatically?[/bold cyan]", choices=["yes", "no"], default="yes")
        
        if download_videos == "yes":
            num_videos = Prompt.ask("[bold cyan]How many videos to download[/bold cyan]", default="10")
            scrape_and_download_pinterest(topic, num_videos)
        else:
            launch_chrome_with_topic(topic)
    else:
        console.print("[yellow]No topic entered. Launching Pinterest homepage.[/yellow]")
        launch_chrome_with_topic("")

def launch_chrome_with_topic(topic):
    """Launch Chrome with Pinterest search"""
    env = os.environ.copy()
    env["DISPLAY"] = ":1"
    
    browser = (
        shutil.which("chromium-browser")
        or "/data/data/com.termux/files/usr/bin/chromium-browser"
    )
    

    console.print(f"[cyan]Using browser:[/cyan] {browser}")  

    formatted_topic = topic.replace(" ", "%20")
    pinterest_url = f"https://www.pinterest.com/search/pins/?q={formatted_topic}%20green%20screen"
    
    chrome_cmd = [
        "google-chrome", 
        "--new-window", 
        pinterest_url,
        "--disable-gpu",
        "--no-sandbox",
        "--window-size=1920,1080"
    ]
    
    try:
        subprocess.Popen(chrome_cmd, env=env)
        console.print(f"[blue]Chrome launched with green screen videos for: {topic}[/blue]")
    except FileNotFoundError:
        console.print("[red]Chrome not found. Please install Chrome or Chromium[/red]")

def save_scraping_session(session_data):
    """Save scraping session to history"""
    existing_data = []
    if os.path.exists(SCRAPED_DATA_FILE):
        with open(SCRAPED_DATA_FILE, 'r') as f:
            existing_data = json.load(f)
    
    existing_data.append(session_data)
    
    with open(SCRAPED_DATA_FILE, 'w') as f:
        json.dump(existing_data, f, indent=2, default=str)
    
    console.print(f"[green]Session saved to {SCRAPED_DATA_FILE}[/green]")

def view_history():
    """View scraping history"""
    if os.path.exists(SCRAPED_DATA_FILE):
        with open(SCRAPED_DATA_FILE, 'r') as f:
            data = json.load(f)
        
        if data:
            table = Table(title="📊 Pinterest Scraping History")
            table.add_column("#", style="cyan")
            table.add_column("Time", style="cyan")
            table.add_column("Topic", style="green")
            table.add_column("Videos Requested", style="yellow")
            table.add_column("Videos Downloaded", style="magenta")
            table.add_column("Status", style="white")
            
            for idx, session in enumerate(reversed(data[-10:]), 1):
                table.add_row(
                    str(idx),
                    session['timestamp'][:19],
                    session['topic'],
                    str(session.get('num_videos_requested', 'N/A')),
                    str(session.get('num_downloaded', '0')),
                    session['status']
                )
            
            console.print(table)
            
            # Option to view full JSON
            if Prompt.ask("[bold]View full JSON for latest session?[/bold]", choices=["yes", "no"], default="no") == "yes":
                view_recent_json()
        else:
            console.print("[yellow]No scraping history found[/yellow]")
    else:
        console.print("[yellow]No scraping history found[/yellow]")

def stop_vnc():
    subprocess.run("vncserver -kill :1", shell=True)
    console.print("[red]VNC stopped[/red]")

def menu():
    """Main menu"""
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold green]🎬 GREEN SCREEN VIDEO SCRAPER[/bold green]\n"
            "Pinterest Green Screen Video Downloader",
            border_style="green"
        ))
        
        console.print("\n[cyan]1.[/cyan] 📥 Start VNC & Scrape Pinterest")
        console.print("[cyan]2.[/cyan] 📹 List/Play Downloaded Videos")
        console.print("[cyan]3.[/cyan] 📊 View Scraping History")
        console.print("[cyan]4.[/cyan] 📄 View Recent JSON Data")
        console.print("[cyan]5.[/cyan] ✏️ Rename Videos (from metadata)")
        console.print("[cyan]6.[/cyan] ℹ️ View Video Metadata")
        console.print("[cyan]7.[/cyan] 🛑 Stop VNC")
        console.print("[cyan]8.[/cyan] 🚪 Exit")
        
        choice = Prompt.ask("\n[bold]Enter choice[/bold]", choices=["1", "2", "3", "4", "5", "6", "7", "8"])
        
        if choice == "1":
            start_vnc()
        elif choice == "2":
            list_downloaded_videos()
        elif choice == "3":
            view_history()
        elif choice == "4":
            view_recent_json()
        elif choice == "5":
            open_and_rename_videos()
        elif choice == "6":
            view_video_metadata()
        elif choice == "7":
            stop_vnc()
        elif choice == "8":
            console.print("[bold red]Goodbye! 🎬[/bold red]")
            break
        
        if choice != "8":
            Prompt.ask("\n[dim]Press Enter to continue...[/dim]", default="")

if __name__ == "__main__":
    menu()
