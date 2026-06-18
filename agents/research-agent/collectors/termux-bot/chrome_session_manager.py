#!/usr/bin/env python3
"""
Rich Chrome Session Manager with Database Backend
"""

import os
import time
import subprocess
import shutil
import signal
import sys
from typing import Optional
import json
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.layout import Layout
from rich.columns import Columns
from rich.text import Text
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown

from session_db import SessionDB

# Configuration
BASE_PROFILE_DIR = os.path.expanduser("~/chrome-sessions")
DEBUG_PORT_START = 9222
DEBUG_PORT_END = 9299

console = Console()

class ChromeSessionManager:
    def __init__(self):
        self.db = SessionDB()
        os.makedirs(BASE_PROFILE_DIR, exist_ok=True)
        self.chrome_path = self._find_chrome()
    
    def _find_chrome(self):
        """Find Chrome/Chromium executable"""
        paths = [
            "chromium-browser",
            "chromium",
            "google-chrome",
            "google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/data/data/com.termux/files/usr/bin/chromium-browser",
        ]
        
        for path in paths:
            if shutil.which(path):
                return path
        raise RuntimeError("Chrome not found. Install chromium-browser")
    
    def _get_profile_dir(self, name: str) -> str:
        """Get profile directory for a session"""
        # Sanitize name for filesystem
        safe_name = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        return os.path.join(BASE_PROFILE_DIR, safe_name)
    
    def _get_next_port(self) -> int:
        """Get next available port"""
        available = self.db.get_available_ports()
        if not available:
            raise RuntimeError("No available ports in range 9222-9299")
        return available[0]
    
    def create_session(self):
        """Interactive session creation"""
        console.print()
        console.print(Panel("🆕 Create New Chrome Session", style="bold green"))
        
        # Get session name
        while True:
            name = Prompt.ask("📝 Session name (e.g., semanticscholar)")
            if not name:
                console.print("[red]Name cannot be empty[/red]")
                continue
            if self.db.get_session_by_name(name):
                console.print(f"[red]Session '{name}' already exists[/red]")
                continue
            break
        
        # Get URL
        url = Prompt.ask("🌐 Website URL", default="https://www.semanticscholar.org")
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        # Get port (auto or manual)
        if Confirm.ask("🔌 Auto-assign port?"):
            port = self._get_next_port()
        else:
            while True:
                port = IntPrompt.ask("🔌 Port number", default=9222)
                if port < 1024 or port > 65535:
                    console.print("[red]Port must be between 1024 and 65535[/red]")
                    continue
                if self.db.get_session_by_port(port):
                    console.print(f"[red]Port {port} is already in use[/red]")
                    continue
                break
        
        # Create profile directory
        profile_dir = self._get_profile_dir(name)
        os.makedirs(profile_dir, exist_ok=True)
        
        # Save to database
        session_id = self.db.create_session(name, url, port, profile_dir)
        
        console.print()
        console.print(f"[green]✅ Session created! ID: {session_id}[/green]")
        console.print(f"   Name: {name}")
        console.print(f"   URL: {url}")
        console.print(f"   Port: {port}")
        console.print(f"   Profile: {profile_dir}")
        
        # Ask if user wants to start it
        if Confirm.ask("🚀 Start this session now?"):
            self.start_session(session_id)
    
    def start_session(self, session_id: int):
        """Start a Chrome session"""
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session {session_id} not found[/red]")
            return
        
        if session['status'] == 'running':
            console.print(f"[yellow]Session '{session['name']}' is already running (PID: {session['pid']})[/yellow]")
            return
        
        console.print(f"[blue]🚀 Starting session '{session['name']}'...[/blue]")
        
        # Build command
        cmd = [
            self.chrome_path,
            f"--remote-debugging-port={session['port']}",
            f"--user-data-dir={session['profile_dir']}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
            "--window-size=1366,768",
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            time.sleep(1)  # Give it a moment to start
            
            if process.poll() is None:
                self.db.start_session(session_id, process.pid)
                console.print(f"[green]✅ Session '{session['name']}' started (PID: {process.pid})[/green]")
                console.print(f"   Debug URL: http://127.0.0.1:{session['port']}")
                console.print(f"   Website: {session['url']}")
            else:
                console.print("[red]❌ Failed to start Chrome[/red]")
        
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")
    
    def stop_session(self, session_id: int):
        """Stop a Chrome session"""
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session {session_id} not found[/red]")
            return
        
        if session['status'] != 'running':
            console.print(f"[yellow]Session '{session['name']}' is not running[/yellow]")
            return
        
        try:
            # Kill the process
            os.kill(session['pid'], signal.SIGTERM)
            time.sleep(1)
            
            # Check if it's dead
            try:
                os.kill(session['pid'], 0)
                # Still alive, force kill
                os.kill(session['pid'], signal.SIGKILL)
            except OSError:
                pass
            
            self.db.stop_session(session_id)
            self.db.release_port(session['port'])
            console.print(f"[green]✅ Session '{session['name']}' stopped[/green]")
        
        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")
    
    def list_sessions(self):
        """List all sessions"""
        sessions = self.db.list_sessions()
        
        if not sessions:
            console.print("[yellow]No sessions found. Create one with option 1.[/yellow]")
            return
        
        table = Table(title="📋 Chrome Sessions", box=box.ROUNDED)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("URL", style="blue")
        table.add_column("Port", style="yellow")
        table.add_column("Status", style="magenta")
        table.add_column("PID", style="red")
        table.add_column("Last Used", style="dim")
        
        for session in sessions:
            status_color = "green" if session['status'] == 'running' else "dim"
            table.add_row(
                str(session['id']),
                session['name'],
                session['url'][:30] + "..." if len(session['url']) > 30 else session['url'],
                str(session['port']),
                f"[{status_color}]{session['status']}[/{status_color}]",
                str(session['pid']) if session['pid'] else "-",
                session['last_used'][:16] if session['last_used'] else "-"
            )
        
        console.print(table)
    
    def show_session_details(self, session_id: int):
        """Show detailed information about a session"""
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session {session_id} not found[/red]")
            return
        
        # Get history
        history = self.db.get_history(session_id, limit=10)
        
        panel_content = f"""
[bold cyan]Session Details[/bold cyan]

[bold]ID:[/bold] {session['id']}
[bold]Name:[/bold] {session['name']}
[bold]URL:[/bold] {session['url']}
[bold]Port:[/bold] {session['port']}
[bold]Status:[/bold] {session['status']}
[bold]PID:[/bold] {session['pid'] if session['pid'] else 'N/A'}
[bold]Profile:[/bold] {session['profile_dir']}
[bold]Created:[/bold] {session['created_at']}
[bold]Updated:[/bold] {session['updated_at']}
[bold]Last Used:[/bold] {session['last_used'] if session['last_used'] else 'Never'}
[bold]Notes:[/bold] {session['notes'] if session['notes'] else 'None'}

[bold cyan]Recent History:[/bold cyan]
"""
        
        if history:
            for entry in history[:5]:
                panel_content += f"  • {entry['timestamp']}: {entry['action']}"
                if entry['details']:
                    panel_content += f" ({entry['details']})"
                panel_content += "\n"
        else:
            panel_content += "  No history available\n"
        
        console.print(Panel(panel_content, title="📊 Session Details", border_style="blue"))
    
    def delete_session(self, session_id: int):
        """Delete a session"""
        session = self.db.get_session(session_id)
        if not session:
            console.print(f"[red]Session {session_id} not found[/red]")
            return
        
        if session['status'] == 'running':
            console.print(f"[yellow]Session '{session['name']}' is running. Stop it first.[/yellow]")
            if Confirm.ask("Stop and delete it?"):
                self.stop_session(session_id)
                time.sleep(1)
            else:
                return
        
        if Confirm.ask(f"Delete session '{session['name']}'?"):
            # Delete profile directory
            if os.path.exists(session['profile_dir']):
                try:
                    import shutil
                    shutil.rmtree(session['profile_dir'])
                except Exception as e:
                    console.print(f"[red]Warning: Could not delete profile directory: {e}[/red]")
            
            self.db.delete_session(session_id)
            console.print(f"[green]✅ Session '{session['name']}' deleted[/green]")
    
    def show_dashboard(self):
        """Show comprehensive dashboard"""
        sessions = self.db.list_sessions()
        running = [s for s in sessions if s['status'] == 'running']
        stopped = [s for s in sessions if s['status'] == 'stopped']
        
        # Summary panel
        summary = f"""
[bold green]📊 Session Summary[/bold green]

Total Sessions: {len(sessions)}
🟢 Running: {len(running)}
⚪ Stopped: {len(stopped)}
🔌 Available Ports: {len(self.db.get_available_ports())}
📁 Profile Directory: {BASE_PROFILE_DIR}
🔧 Chrome: {self.chrome_path}
        """
        
        console.print(Panel(summary, title="Dashboard", border_style="cyan"))
        
        # Show running sessions if any
        if running:
            running_table = Table(title="🟢 Running Sessions", box=box.SIMPLE)
            running_table.add_column("Name", style="green")
            running_table.add_column("Port", style="yellow")
            running_table.add_column("PID", style="red")
            running_table.add_column("Debug URL", style="blue")
            
            for session in running:
                running_table.add_row(
                    session['name'],
                    str(session['port']),
                    str(session['pid']),
                    f"http://127.0.0.1:{session['port']}"
                )
            
            console.print(running_table)
        else:
            console.print("[dim]No running sessions[/dim]")
        
        console.print()
    
    def interactive_menu(self):
        """Main interactive menu"""
        while True:
            console.clear()
            console.print()
            
            header = """
╔══════════════════════════════════════════════════════════════╗
║           🌐 Chrome Session Manager                        ║
║           Persistent Chrome Sessions with Database        ║
╚══════════════════════════════════════════════════════════════╝
            """
            console.print(Panel(header, border_style="cyan"))
            
            # Dashboard summary at top
            sessions = self.db.list_sessions()
            running = len([s for s in sessions if s['status'] == 'running'])
            total = len(sessions)
            available = len(self.db.get_available_ports())
            
            status_line = f"📊 {total} sessions | 🟢 {running} running | 🔌 {available} ports available"
            console.print(Panel(status_line, style="dim"))
            console.print()
            
            # Menu options
            menu = Table(show_header=False, box=box.MINIMAL_HEAVY_HEAD)
            menu.add_column("Option", style="cyan", width=8)
            menu.add_column("Action", style="white")
            menu.add_column("Description", style="dim")
            
            menu.add_row("1", "[green]Create Session[/green]", "Create a new Chrome session")
            menu.add_row("2", "[blue]Start Session[/blue]", "Start an existing session")
            menu.add_row("3", "[yellow]Stop Session[/yellow]", "Stop a running session")
            menu.add_row("4", "[magenta]List Sessions[/magenta]", "Show all sessions")
            menu.add_row("5", "[cyan]Session Details[/cyan]", "Show detailed session info")
            menu.add_row("6", "[red]Delete Session[/red]", "Delete a session")
            menu.add_row("7", "[white]Dashboard[/white]", "Show comprehensive dashboard")
            menu.add_row("8", "[bold]View History[/bold]", "View session history")
            menu.add_row("0", "[red]Exit[/red]", "Exit the manager")
            
            console.print(menu)
            console.print()
            
            choice = Prompt.ask("Select option", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8"])
            
            if choice == "0":
                console.print("[green]Goodbye! 👋[/green]")
                break
            
            elif choice == "1":
                self.create_session()
            
            elif choice == "2":
                self.list_sessions()
                session_id = IntPrompt.ask("Enter session ID to start")
                self.start_session(session_id)
            
            elif choice == "3":
                self.list_sessions()
                session_id = IntPrompt.ask("Enter session ID to stop")
                self.stop_session(session_id)
            
            elif choice == "4":
                self.list_sessions()
            
            elif choice == "5":
                self.list_sessions()
                session_id = IntPrompt.ask("Enter session ID")
                self.show_session_details(session_id)
            
            elif choice == "6":
                self.list_sessions()
                session_id = IntPrompt.ask("Enter session ID to delete")
                self.delete_session(session_id)
            
            elif choice == "7":
                self.show_dashboard()
            
            elif choice == "8":
                history = self.db.get_history(limit=20)
                if history:
                    table = Table(title="📜 Recent History", box=box.ROUNDED)
                    table.add_column("Time", style="dim")
                    table.add_column("Session", style="green")
                    table.add_column("Action", style="cyan")
                    table.add_column("Details", style="white")
                    
                    for entry in history:
                        session = self.db.get_session(entry['session_id'])
                        session_name = session['name'] if session else f"ID:{entry['session_id']}"
                        table.add_row(
                            entry['timestamp'][:16],
                            session_name,
                            entry['action'],
                            entry['details'] or ""
                        )
                    
                    console.print(table)
                else:
                    console.print("[dim]No history available[/dim]")
            
            if choice != "0":
                console.print()
                Prompt.ask("Press Enter to continue...")

def main():
    try:
        manager = ChromeSessionManager()
        manager.interactive_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
