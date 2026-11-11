"""
Pipeline orchestrator and command parser for Content Machine.
Supports /pipeline: topic: <query> commands, CLI flags, and programmatic calls.
"""

import sys
import re
import argparse
import logging
from typing import Optional

from .agents.rabbit_hole import RabbitHoleCoordinator
from .core.models import ResearchDossier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("content_machine.pipeline")


def parse_pipeline_command(raw_input: str) -> str:
    """
    Parse topic from commands such as:
    - /pipeline: topic: understanding linux ecosystem
    - topic: understanding linux ecosystem
    - /pipeline understanding linux ecosystem
    - understanding linux ecosystem
    """
    text = raw_input.strip()

    # Pattern: /pipeline: topic: <topic> or /pipeline: <topic>
    m1 = re.match(r"^/pipeline:\s*(?:topic:\s*)?(.+)$", text, re.IGNORECASE)
    if m1:
        return m1.group(1).strip()

    # Pattern: topic: <topic>
    m2 = re.match(r"^topic:\s*(.+)$", text, re.IGNORECASE)
    if m2:
        return m2.group(1).strip()

    # Pattern: /pipeline <topic>
    m3 = re.match(r"^/pipeline\s+(.+)$", text, re.IGNORECASE)
    if m3:
        return m3.group(1).strip()

    return text


def run_pipeline(
    topic_command: str,
    max_depth: int = 1,
    max_branches: int = 3,
    output_dir: str = "output",
    db_path: str = "research.db"
) -> ResearchDossier:
    """
    Execute the multi-agent rabbit-hole research pipeline for a topic command.
    """
    topic = parse_pipeline_command(topic_command)
    if not topic:
        topic = "understanding linux ecosystem"

    coordinator = RabbitHoleCoordinator(
        max_depth=max_depth,
        max_branches_per_node=max_branches,
        db_path=db_path,
        output_dir=output_dir
    )
    dossier = coordinator.explore_topic(topic)
    return dossier


def main():
    """CLI entrypoint for content_machine.pipeline"""
    parser = argparse.ArgumentParser(description="Content Machine Multi-Agent Rabbit Hole Pipeline")
    parser.add_argument("command", nargs="*", help="Topic or command like '/pipeline: topic: understanding linux ecosystem'")
    parser.add_argument("--topic", "-t", default=None, help="Explicit topic string")
    parser.add_argument("--depth", "-d", type=int, default=1, help="Max recursion depth for rabbit hole branches (default: 1)")
    parser.add_argument("--branches", "-b", type=int, default=3, help="Max branches per node (default: 3)")
    parser.add_argument("--output", "-o", default="output", help="Output directory for reports and dossiers")
    parser.add_argument("--db", default="research.db", help="SQLite database path")

    args = parser.parse_args()

    raw_command = args.topic
    if not raw_command and args.command:
        raw_command = " ".join(args.command)

    if not raw_command:
        raw_command = "/pipeline: topic: understanding linux ecosystem"

    run_pipeline(
        topic_command=raw_command,
        max_depth=args.depth,
        max_branches=args.branches,
        output_dir=args.output,
        db_path=args.db
    )


if __name__ == "__main__":
    main()
