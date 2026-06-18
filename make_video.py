#!/usr/bin/env python3
# make_video.py - One command to rule them all

import sys
import subprocess
from pathlib import Path
import argparse

def main():
    parser = argparse.ArgumentParser(description="Complete Video Content Machine")
    parser.add_argument("topic", help="Video topic")
    parser.add_argument("--mode", choices=["quick", "full", "research-only", "edit-only"], 
                       default="full")
    parser.add_argument("--output", default="./output")
    args = parser.parse_args()
    
    if args.mode == "full":
        # Complete pipeline
        subprocess.run([
            "python", "-c", f"""
from editor import complete_video_pipeline
complete_video_pipeline("{args.topic}", "{args.output}")
"""
        ])
        
    elif args.mode == "research-only":
        subprocess.run([
            "python", "agents/research-agent/agent.py",
            args.topic
        ])
        
    elif args.mode == "edit-only":
        subprocess.run([
            "python", "editor.py"
        ])  # Opens TUI for manual editing
        
    elif args.mode == "quick":
        # Fast mode: use existing assets
        subprocess.run([
            "python", "editor.py", "--quick", args.topic
        ])

if __name__ == "__main__":
    main()
