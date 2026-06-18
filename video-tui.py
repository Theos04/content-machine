#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, ListView, ListItem, Label, Button, Input, Static
from textual import events

# ----- Emoji removal (fallback if emoji library not installed) -----
try:
    import emoji
    def remove_emoji(text: str) -> str:
        return emoji.replace_emoji(text, replace='')
except ImportError:
    def remove_emoji(text: str) -> str:
        # Regex for common emoji ranges
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F700-\U0001F77F"  # alchemical symbols
            u"\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
            u"\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
            u"\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
            u"\U0001FA00-\U0001FA6F"  # Chess Symbols
            u"\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
            u"\U00002702-\U000027B0"  # Dingbats
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        return emoji_pattern.sub(r'', text)

def sanitize_filename(name: str) -> str:
    """Clean up filename: remove emojis, hashtags, special chars."""
    # Remove extension for processing
    stem, ext = name.rsplit('.', 1) if '.' in name else (name, '')
    # Remove emojis
    stem = remove_emoji(stem)
    # Remove hashtags (e.g., #viral)
    stem = re.sub(r'#\S+', '', stem)
    # Remove special characters except letters, numbers, underscore, dash, dot
    stem = re.sub(r'[^a-zA-Z0-9_.\-]+', ' ', stem)
    # Replace spaces with underscores
    stem = re.sub(r'\s+', '_', stem).strip('_')
    # Collapse multiple underscores
    stem = re.sub(r'_{2,}', '_', stem)
    # Lowercase
    stem = stem.lower()
    # Limit length
    if len(stem) > 80:
        stem = stem[:80]
    # Add extension
    return f"{stem}.{ext}" if ext else stem

def get_video_list(folder="raw"):
    """Return sorted list of video files in folder."""
    path = Path(folder)
    if not path.exists():
        return []
    # Include common video extensions
    extensions = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
    return sorted([f for f in path.glob("*") if f.suffix.lower() in extensions])

def play_video_external(video_path: Path):
    """Open video with system default player (mpv or termux-open)."""
    try:
        # Try mpv first
        subprocess.Popen(["mpv", str(video_path)])
    except FileNotFoundError:
        # Fallback for Termux
        try:
            subprocess.Popen(["termux-open", str(video_path)])
        except FileNotFoundError:
            print(f"Cannot play video: no mpv or termux-open found. File: {video_path}")

class VideoBrowser(App):
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 1fr 2fr;
        grid-rows: 1fr auto;
    }
    #file-list {
        border: solid green;
        height: 100%;
    }
    #info-panel {
        border: solid blue;
        padding: 1;
    }
    #action-bar {
        column-span: 2;
        height: 3;
        background: $panel;
        padding: 0 1;
    }
    Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(id="file-list"):
            yield ListView()
        with Vertical(id="info-panel"):
            yield Label("Select a video", id="info-label")
            yield Input(placeholder="Add tag...", id="tag-input")
            yield Label("Sanitized name: ", id="sanitized-preview")
        with Horizontal(id="action-bar"):
            yield Button("Play", variant="primary", id="play")
            yield Button("Sanitize & Rename", id="sanitize")
            yield Button("Add Tag", id="add-tag")
            yield Button("Move to...", id="move")
            yield Button("Quit", id="quit")
        yield Footer()

    def on_mount(self):
        self.videos = get_video_list()
        if not self.videos:
            self.query_one("#info-label").update("No videos found in 'raw/' folder")
            return
        list_view = self.query_one(ListView)
        for v in self.videos:
            list_view.append(ListItem(Label(v.name)))
        self.current_index = 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """FIXED: use list_view.index instead of item.index"""
        self.current_index = event.list_view.index
        self.update_info_panel()

    def update_info_panel(self):
        if not self.videos:
            return
        video = self.videos[self.current_index]
        sanitized = sanitize_filename(video.name)
        self.query_one("#info-label").update(f"File: {video.name}\nPath: {video}")
        self.query_one("#sanitized-preview").update(f"Sanitized name: {sanitized}")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "play":
            self.play_video()
        elif event.button.id == "sanitize":
            self.sanitize_and_rename()
        elif event.button.id == "add-tag":
            self.add_tag()
        elif event.button.id == "move":
            self.move_to_folder()
        elif event.button.id == "quit":
            self.exit()

    def play_video(self):
        if not self.videos:
            return
        video_path = self.videos[self.current_index]
        play_video_external(video_path)

    def sanitize_and_rename(self):
        if not self.videos:
            return
        old_path = self.videos[self.current_index]
        new_name = sanitize_filename(old_path.name)
        new_path = old_path.parent / new_name
        if new_path.exists() and new_path != old_path:
            self.query_one("#info-label").update("ERROR: target file already exists, not renaming")
            return
        old_path.rename(new_path)
        self.videos[self.current_index] = new_path
        # Update list view item text
        list_view = self.query_one(ListView)
        list_view.children[self.current_index].children[0].update(new_path.name)
        self.update_info_panel()

    def add_tag(self):
        tag_input = self.query_one("#tag-input")
        tag = tag_input.value.strip()
        if tag:
            # For now, just display; you can extend with SQLite later
            self.query_one("#info-label").update(f"Tag '{tag}' added (DB not yet implemented)")
            tag_input.value = ""

    def move_to_folder(self):
        """Prompt user for destination folder (existing or new)."""
        if not self.videos:
            return
        from textual.screen import ModalScreen
        from textual.widgets import Input as ModalInput, Label as ModalLabel

        class MoveScreen(ModalScreen):
            def compose(self):
                yield ModalLabel("Enter destination folder (relative path):")
                yield ModalInput(placeholder="e.g., greenscreen or memes", id="dest-input")
                with Horizontal():
                    yield Button("Move", variant="primary", id="move-confirm")
                    yield Button("Cancel", id="cancel")

            def on_button_pressed(self, event):
                if event.button.id == "move-confirm":
                    dest_name = self.query_one("#dest-input").value.strip()
                    if dest_name:
                        self.dismiss(dest_name)
                else:
                    self.dismiss(None)

        def move_callback(dest_name):
            if dest_name:
                dest = Path(dest_name)
                dest.mkdir(exist_ok=True)
                old_path = self.videos[self.current_index]
                new_path = dest / old_path.name
                # Avoid overwriting
                if new_path.exists():
                    self.query_one("#info-label").update(f"ERROR: {new_path} already exists")
                    return
                old_path.rename(new_path)
                # Remove from list
                self.videos.pop(self.current_index)
                list_view = self.query_one(ListView)
                list_view.children[self.current_index].remove()
                if self.videos:
                    self.current_index = min(self.current_index, len(self.videos)-1)
                    self.update_info_panel()
                else:
                    self.query_one("#info-label").update("No videos left in raw/")
                    self.query_one("#sanitized-preview").update("")

        self.push_screen(MoveScreen(), move_callback)

if __name__ == "__main__":
    app = VideoBrowser()
    app.run()
