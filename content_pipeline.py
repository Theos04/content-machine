#!/usr/bin/env python3
# content_pipeline.py - Complete Video Content Machine

from pathlib import Path
import subprocess
import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ContentPackage:
    """Complete content package for video generation"""
    topic: str
    script: str
    voiceover_path: Path
    visuals: List[Path]  # screen recordings, b-roll
    sfx_folder: Path
    output_video: Path

class ContentMachine:
    def __init__(self):
        self.research_dir = Path("./agents/research-agent")
        self.raw_dir = Path("./raw")
        self.segregated_dir = Path("./segregated")
        self.output_dir = Path("./output")
        
    def run_complete_pipeline(self, topic: str):
        """Full pipeline: research → script → assets → edit → publish"""
        
        # Step 1: Research & Content Gathering
        print("📚 STEP 1: Researching topic...")
        research_data = self.research_topic(topic)
        
        # Step 2: Generate Script
        print("✍️ STEP 2: Generating script from research...")
        script = self.generate_script(research_data, topic)
        
        # Step 3: Create Voiceover
        print("🎙️ STEP 3: Creating voiceover...")
        voiceover = self.create_voiceover(script)
        
        # Step 4: Gather/Record Screen Content
        print("🎬 STEP 4: Recording screen content...")
        screen_recording = self.record_screen_content(topic)
        
        # Step 5: Auto-edit with effects
        print("✂️ STEP 5: Auto-editing video...")
        final_video = self.auto_edit_video(
            screen_recording=screen_recording,
            voiceover=voiceover,
            script=script,
            topic=topic
        )
        
        # Step 6: Export & Publish
        print("📤 STEP 6: Exporting final video...")
        self.export_video(final_video, topic)
        
        return final_video
