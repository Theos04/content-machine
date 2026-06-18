#!/usr/bin/env python3
"""
Fastest Tutorial Editor
- Screen recording + voiceover
- Auto subtitles (Whisper)
- Auto VFX (zoom on keywords)
- Auto SFX (clicks, whooshes on silences)
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import typer
import whisper
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

console = Console()

# ----------------------------------------------------------------------
# Audio & video processing helpers
# ----------------------------------------------------------------------

def get_duration(file_path: Path) -> float:
    """Return duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def add_audio_to_video(video: Path, audio: Path, output: Path):
    """Replace or add audio track to video."""
    cmd = [
        "ffmpeg", "-i", str(video), "-i", str(audio),
        "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
        "-shortest", "-y", str(output)
    ]
    subprocess.run(cmd, check=True, capture_output=True)

def get_video_resolution(video: Path) -> Tuple[int, int]:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(video)
    ]
    res = json.loads(subprocess.run(cmd, capture_output=True, text=True).stdout)
    w = res["streams"][0]["width"]
    h = res["streams"][0]["height"]
    return w, h

# ----------------------------------------------------------------------
# Whisper transcription
# ----------------------------------------------------------------------

def transcribe_audio(audio_path: Path) -> Dict[str, Any]:
    """Return Whisper result with segments."""
    model = whisper.load_model("base")
    result = model.transcribe(str(audio_path), word_timestamps=True)
    return result

def generate_srt(segments: List[Dict], output_srt: Path):
    """Create SRT subtitle file from Whisper segments."""
    def fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(output_srt, "w") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{fmt_time(seg['start'])} --> {fmt_time(seg['end'])}\n")
            f.write(f"{seg['text'].strip()}\n\n")
    rprint(f"[green]Subtitles saved to {output_srt}[/green]")

# ----------------------------------------------------------------------
# Auto VFX: zoom on keywords
# ----------------------------------------------------------------------

KEYWORD_EFFECTS = {
    "important": "zoom", "note": "zoom", "click": "zoom",
    "here": "zoom", "watch": "zoom", "see": "zoom"
}

def add_zoom_effects(video_path: Path, segments: List[Dict], output_path: Path):
    """
    Overlay zoom-in effects at timestamps where keywords appear.
    This creates a new video with zoom-in sections (simplified: single zoom per keyword).
    For production, you'd split video, apply zoom, then concatenate.
    Here we generate a filter complex that zooms at those times.
    """
    w, h = get_video_resolution(video_path)
    # We'll build a list of time intervals to zoom
    zoom_intervals = []
    for seg in segments:
        text = seg["text"].lower()
        if any(kw in text for kw in KEYWORD_EFFECTS):
            # Zoom for 1 second centered at the middle of the segment
            center = (seg["start"] + seg["end"]) / 2
            zoom_intervals.append((center - 0.5, center + 0.5))

    if not zoom_intervals:
        # No zoom, just copy
        subprocess.run(["cp", str(video_path), str(output_path)], check=True)
        return

    # Build a complex filter: at specific times, apply zoom (scale from 1 to 1.5 and back)
    # This is a simplified example: for each interval we create a separate output and concat.
    # Actually easier: use the 'zoompan' filter, but it's tricky with audio sync.
    # For demonstration, we'll use a ready-made script approach:
    # Split video into pieces, apply zoom to middle piece, concat.
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        last_end = 0.0
        for i, (z_start, z_end) in enumerate(zoom_intervals):
            # before part
            if z_start > last_end:
                before = Path(tmp) / f"before_{i}.mp4"
                subprocess.run([
                    "ffmpeg", "-i", str(video_path), "-ss", str(last_end), "-to", str(z_start),
                    "-c", "copy", "-y", str(before)
                ], check=True, capture_output=True)
                parts.append(before)
            # zoom part
            zoom_part = Path(tmp) / f"zoom_{i}.mp4"
            # Apply zoom using crop + scale (center zoom factor 1.5)
            crop_w = int(w / 1.5)
            crop_h = int(h / 1.5)
            cmd = [
                "ffmpeg", "-i", str(video_path), "-ss", str(z_start), "-to", str(z_end),
                "-filter_complex",
                f"crop={crop_w}:{crop_h}:(iw-{crop_w})/2:(ih-{crop_h})/2,scale={w}:{h}",
                "-c:a", "copy", "-y", str(zoom_part)
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            parts.append(zoom_part)
            last_end = z_end
        # after last zoom
        duration = get_duration(video_path)
        if last_end < duration:
            after = Path(tmp) / "after.mp4"
            subprocess.run([
                "ffmpeg", "-i", str(video_path), "-ss", str(last_end), "-to", str(duration),
                "-c", "copy", "-y", str(after)
            ], check=True, capture_output=True)
            parts.append(after)
        # concat all parts
        concat_list = Path(tmp) / "list.txt"
        with open(concat_list, "w") as f:
            for p in parts:
                f.write(f"file '{p}'\n")
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", "-y", str(output_path)
        ], check=True, capture_output=True)

    rprint(f"[cyan]Added {len(zoom_intervals)} zoom effects[/cyan]")

# ----------------------------------------------------------------------
# Auto SFX: insert clicks/whooshes at silences
# ----------------------------------------------------------------------

def detect_silences(audio_path: Path, threshold_db: float = -30, min_dur: float = 0.3) -> List[Tuple[float, float]]:
    """Return list of (start, end) silence segments in seconds."""
    cmd = [
        "ffmpeg", "-i", str(audio_path), "-af",
        f"silencedetect=noise={threshold_db}dB:d={min_dur}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    pattern = r"silence_start: ([\d\.]+)\nsilence_end: ([\d\.]+)"
    matches = re.findall(pattern, result.stderr)
    return [(float(s), float(e)) for s, e in matches]

def overlay_sfx(video_path: Path, audio_path: Path, silences: List[Tuple[float, float]], sfx_folder: Path, output_path: Path):
    """
    Overlay random SFX at the middle of each silence.
    Uses ffmpeg's amix filter.
    """
    if not sfx_folder.exists():
        rprint("[yellow]SFX folder not found, skipping SFX[/yellow]")
        subprocess.run(["cp", str(video_path), str(output_path)], check=True)
        return

    sfx_files = list(sfx_folder.glob("*.mp3")) + list(sfx_folder.glob("*.wav"))
    if not sfx_files:
        rprint("[yellow]No SFX files found, skipping[/yellow]")
        subprocess.run(["cp", str(video_path), str(output_path)], check=True)
        return

    # Build filter_complex to mix SFX at given timestamps
    # We'll create a temporary audio with mixed SFX, then combine with video.
    with tempfile.TemporaryDirectory() as tmp:
        mixed_audio = Path(tmp) / "mixed_audio.wav"
        # Start with original audio
        subprocess.run([
            "ffmpeg", "-i", str(audio_path), "-c", "copy", str(mixed_audio)
        ], check=True, capture_output=True)

        for idx, (s_start, s_end) in enumerate(silences):
            sfx = sfx_files[idx % len(sfx_files)]
            mid = (s_start + s_end) / 2
            # Create a temporary audio with just the SFX at the right time
            sfx_duration = get_duration(sfx)
            sfx_at_time = Path(tmp) / f"sfx_{idx}.wav"
            subprocess.run([
                "ffmpeg", "-i", str(sfx), "-af", f"adelay={int(mid*1000)}|{int(mid*1000)}",
                "-y", str(sfx_at_time)
            ], check=True, capture_output=True)
            # Mix with current mixed_audio
            new_mixed = Path(tmp) / f"mixed_{idx}.wav"
            subprocess.run([
                "ffmpeg", "-i", str(mixed_audio), "-i", str(sfx_at_time),
                "-filter_complex", "amix=inputs=2:duration=longest",
                "-y", str(new_mixed)
            ], check=True, capture_output=True)
            mixed_audio = new_mixed

        # Combine final audio with video
        subprocess.run([
            "ffmpeg", "-i", str(video_path), "-i", str(mixed_audio),
            "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", "-y", str(output_path)
        ], check=True, capture_output=True)

    rprint(f"[cyan]Added {len(silences)} SFX effects[/cyan]")

# ----------------------------------------------------------------------
# Main tutorial pipeline
# ----------------------------------------------------------------------

def render_tutorial(video_path: Path, audio_path: Path, output_path: Path, sfx_folder: Optional[Path] = None):
    """
    Full automatic pipeline:
    1. Combine screen recording with voiceover.
    2. Transcribe voiceover → subtitles.
    3. Add zoom effects based on keywords.
    4. Add SFX based on silences.
    5. Burn subtitles into video.
    """
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        # Step 1: combine video + audio
        progress.add_task(description="Combining video and audio...", total=None)
        combined_video = Path(tempfile.gettempdir()) / "combined.mp4"
        add_audio_to_video(video_path, audio_path, combined_video)

        # Step 2: transcribe
        progress.add_task(description="Transcribing voiceover (Whisper)...", total=None)
        transcript = transcribe_audio(audio_path)
        srt_path = output_path.with_suffix(".srt")
        generate_srt(transcript["segments"], srt_path)

        # Step 3: zoom effects
        progress.add_task(description="Adding zoom effects on keywords...", total=None)
        zoomed_video = Path(tempfile.gettempdir()) / "zoomed.mp4"
        add_zoom_effects(combined_video, transcript["segments"], zoomed_video)

        # Step 4: SFX overlay
        if sfx_folder and sfx_folder.exists():
            progress.add_task(description="Detecting silences and adding SFX...", total=None)
            silences = detect_silences(audio_path)
            if silences:
                sfx_video = Path(tempfile.gettempdir()) / "with_sfx.mp4"
                overlay_sfx(zoomed_video, audio_path, silences, sfx_folder, sfx_video)
                final_video = sfx_video
            else:
                final_video = zoomed_video
        else:
            final_video = zoomed_video

        # Step 5: burn subtitles
        progress.add_task(description="Burning subtitles...", total=None)
        subprocess.run([
            "ffmpeg", "-i", str(final_video), "-vf", f"subtitles={srt_path}",
            "-c:a", "copy", "-y", str(output_path)
        ], check=True, capture_output=True)

    rprint(f"[bold green]✅ Tutorial ready: {output_path}[/bold green]")

# ----------------------------------------------------------------------
# TUI (simplified)
# ----------------------------------------------------------------------

def tui():
    console.clear()
    console.print(Panel.fit("🎬 FASTEST TUTORIAL EDITOR", style="bold green"))

    while True:
        console.print("\n[bold cyan]1.[/] Import screen recording")
        console.print("[bold cyan]2.[/] Import voiceover (audio)")
        console.print("[bold cyan]3.[/] Set SFX folder (optional)")
        console.print("[bold cyan]4.[/] RUN FULL AUTOMATION → Export tutorial")
        console.print("[bold cyan]5.[/] Quit")

        choice = Prompt.ask("Choose", choices=["1","2","3","4","5"])

        if choice == "1":
            video_path = Prompt.ask("Path to screen recording (MP4)")
            if Path(video_path).exists():
                state["video"] = Path(video_path)
                console.print(f"[green]Video loaded: {video_path}[/green]")
            else:
                console.print("[red]File not found[/red]")

        elif choice == "2":
            audio_path = Prompt.ask("Path to voiceover (MP3/WAV)")
            if Path(audio_path).exists():
                state["audio"] = Path(audio_path)
                console.print(f"[green]Voiceover loaded: {audio_path}[/green]")
            else:
                console.print("[red]File not found[/red]")

        elif choice == "3":
            sfx_path = Prompt.ask("Path to folder with SFX (.mp3/.wav)", default="./sfx")
            if Path(sfx_path).exists():
                state["sfx"] = Path(sfx_path)
                console.print(f"[green]SFX folder set: {sfx_path}[/green]")
            else:
                console.print("[red]Folder not found, SFX will be skipped[/red]")
                state["sfx"] = None

        elif choice == "4":
            if "video" not in state or "audio" not in state:
                console.print("[red]Please import both video and voiceover first![/red]")
                continue
            out = Prompt.ask("Output filename", default="tutorial_final.mp4")
            render_tutorial(state["video"], state["audio"], Path(out), state.get("sfx"))
            if Confirm.ask("Process another tutorial?", default=False):
                continue
            else:
                break

        elif choice == "5":
            break

        console.input("\nPress Enter to continue...")
        console.clear()

# ----------------------------------------------------------------------
# CLI entry
# ----------------------------------------------------------------------

if __name__ == "__main__":
    state = {"video": None, "audio": None, "sfx": None}
    tui()
