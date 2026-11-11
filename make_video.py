#!/usr/bin/env python3
# make_video.py - Unified Content Machine CLI

import sys
import argparse
from pathlib import Path
from content_pipeline import ContentMachine
from content_machine.pipeline import run_pipeline, parse_pipeline_command


def main():
    parser = argparse.ArgumentParser(description="Complete Video Content Machine")
    parser.add_argument("topic", help="Video topic or '/pipeline: topic: <name>'")
    parser.add_argument(
        "--mode",
        choices=["quick", "full", "research-only", "edit-only"],
        default="full",
        help="Pipeline execution mode (default: full)"
    )
    parser.add_argument("--output", default="./output", help="Output directory")
    parser.add_argument("--depth", type=int, default=1, help="Rabbit hole recursion depth (default: 1)")
    parser.add_argument("--branches", type=int, default=3, help="Max branches per node (default: 3)")
    args = parser.parse_args()

    clean_topic = parse_pipeline_command(args.topic)

    if args.mode == "full":
        machine = ContentMachine(output_dir=args.output)
        machine.run_complete_pipeline(clean_topic)

    elif args.mode == "research-only":
        run_pipeline(
            topic_command=clean_topic,
            max_depth=args.depth,
            max_branches=args.branches,
            output_dir=args.output
        )

    elif args.mode == "edit-only":
        from editor import tui
        tui()

    elif args.mode == "quick":
        # Fast mode: Run research depth 0 and outline
        run_pipeline(
            topic_command=clean_topic,
            max_depth=0,
            max_branches=0,
            output_dir=args.output
        )


if __name__ == "__main__":
    main()
