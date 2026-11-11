#!/usr/bin/env python3
# content_pipeline.py - Complete Video Content Machine Orchestrator

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

from content_machine.pipeline import run_pipeline, parse_pipeline_command
from content_machine.core.models import ResearchDossier


@dataclass
class ContentPackage:
    """Complete content package for video generation"""
    topic: str
    script: str
    voiceover_path: Optional[Path] = None
    visuals: List[Path] = None
    sfx_folder: Optional[Path] = None
    output_video: Optional[Path] = None
    dossier: Optional[ResearchDossier] = None


class ContentMachine:
    def __init__(self, output_dir: str = "./output"):
        self.output_dir = Path(output_dir)
        self.raw_dir = Path("./raw")
        self.segregated_dir = Path("./segregated")
        self.sfx_dir = Path("./sfx")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.segregated_dir.mkdir(parents=True, exist_ok=True)
        self.sfx_dir.mkdir(parents=True, exist_ok=True)

    def research_topic(self, topic: str, depth: int = 1, branches: int = 3) -> ResearchDossier:
        """Step 1: Multi-agent rabbit hole research and stitching."""
        print(f"\n📚 STEP 1: Running Multi-Agent Rabbit Hole Research for: '{topic}'...")
        dossier = run_pipeline(
            topic_command=topic,
            max_depth=depth,
            max_branches=branches,
            output_dir=str(self.output_dir)
        )
        return dossier

    def generate_script(self, dossier: ResearchDossier, topic: str) -> str:
        """Step 2: Generate script from research dossier."""
        print("\n✍️ STEP 2: Generating video narration script from research...")
        lines = [
            f"# Video Script: {dossier.root_topic}",
            "",
            "## Hook (00:00 - 00:30)",
            f"{dossier.executive_summary}",
            ""
        ]

        for scene in dossier.script_outline:
            lines.append(f"## {scene['section']} ({scene['est_duration']})")
            lines.append(f"Visual Cue: [{scene['visual_cue']}]")
            for pt in scene['talking_points']:
                lines.append(f"- {pt}")
            lines.append("")

        script_text = "\n".join(lines)
        script_path = self.output_dir / f"{dossier.root_topic.replace(' ', '_').lower()}_script.txt"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_text)
        print(f"✅ Script saved to: {script_path}")
        return script_text

    def create_voiceover(self, script: str, topic: str) -> Optional[Path]:
        """Step 3: Synthesize voiceover using gTTS or Silero."""
        print("\n🎙️ STEP 3: Creating voiceover audio...")
        safe_name = topic.replace(" ", "_").lower()
        vo_path = self.output_dir / f"{safe_name}_voiceover.mp3"
        try:
            from gtts import gTTS
            # Strip markdown formatting headers for TTS
            clean_text = "\n".join([
                line for line in script.splitlines()
                if not line.startswith("#") and not line.startswith("Visual Cue:")
            ])
            tts = gTTS(text=clean_text[:4000], lang="en", slow=False)
            tts.save(str(vo_path))
            print(f"✅ Voiceover generated: {vo_path}")
            return vo_path
        except Exception as e:
            print(f"ℹ️ Voiceover synthesis skipped or gTTS error: {e}")
            return None

    def record_screen_content(self, topic: str) -> Optional[Path]:
        """Step 4: Locate or capture screen recording / visual assets."""
        print("\n🎬 STEP 4: Checking visual assets in raw/ and segregated/...")
        raw_videos = list(self.raw_dir.glob("*.mp4")) + list(self.segregated_dir.glob("*/*.mp4"))
        if raw_videos:
            chosen = raw_videos[0]
            print(f"✅ Found existing visual footage: {chosen}")
            return chosen
        print("ℹ️ No raw video clips found in raw/. Place an .mp4 in raw/ to edit.")
        return None

    def auto_edit_video(
        self,
        screen_recording: Optional[Path],
        voiceover: Optional[Path],
        script: str,
        topic: str
    ) -> Optional[Path]:
        """Step 5: Auto-edit video with Whisper subtitles, zoom VFX, and SFX."""
        print("\n✂️ STEP 5: Checking requirements for auto-editing video...")
        if not screen_recording or not voiceover:
            print("ℹ️ Both video and voiceover are required for final video rendering. Research and script completed.")
            return None
        try:
            from editor import render_tutorial
            safe_name = topic.replace(" ", "_").lower()
            out_video = self.output_dir / f"{safe_name}_final.mp4"
            render_tutorial(screen_recording, voiceover, out_video, self.sfx_dir)
            return out_video
        except Exception as e:
            print(f"⚠️ Video rendering skipped or error: {e}")
            return None

    def export_video(self, final_video: Optional[Path], topic: str):
        """Step 6: Final export confirmation."""
        print("\n📤 STEP 6: Packaging output assets...")
        if final_video and final_video.exists():
            print(f"🎉 Final Video Ready: {final_video}")
        else:
            print(f"🎉 Research and script generation successfully finished in '{self.output_dir}'!")

    def run_complete_pipeline(self, topic_command: str):
        """Full pipeline: research → script → assets → edit → publish"""
        topic = parse_pipeline_command(topic_command)

        # Step 1: Multi-Agent Rabbit Hole Research
        dossier = self.research_topic(topic)

        # Step 2: Generate Script from Research Dossier
        script = self.generate_script(dossier, topic)

        # Step 3: Create Voiceover
        voiceover = self.create_voiceover(script, topic)

        # Step 4: Gather Screen Content
        screen_recording = self.record_screen_content(topic)

        # Step 5: Auto-edit with effects
        final_video = self.auto_edit_video(
            screen_recording=screen_recording,
            voiceover=voiceover,
            script=script,
            topic=topic
        )

        # Step 6: Export & Publish
        self.export_video(final_video, topic)

        return ContentPackage(
            topic=topic,
            script=script,
            voiceover_path=voiceover,
            visuals=[screen_recording] if screen_recording else [],
            sfx_folder=self.sfx_dir,
            output_video=final_video,
            dossier=dossier
        )


def main():
    parser = argparse.ArgumentParser(description="Content Machine Complete Pipeline")
    parser.add_argument("command", nargs="*", help="Topic command like '/pipeline: topic: understanding linux ecosystem'")
    parser.add_argument("--output", default="./output", help="Output directory")
    args = parser.parse_args()

    topic_cmd = " ".join(args.command) if args.command else "/pipeline: topic: understanding linux ecosystem"
    machine = ContentMachine(output_dir=args.output)
    machine.run_complete_pipeline(topic_cmd)


if __name__ == "__main__":
    main()
