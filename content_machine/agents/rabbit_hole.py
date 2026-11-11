"""
Rabbit Hole Coordinator.
Manages the recursive multi-agent branching research down topic rabbit holes,
extracts conceptual branches, avoids cycles, and coordinates final stitching.
"""

import logging
import re
from collections import Counter
from typing import List, Dict, Set, Optional

from ..core.bus import TopicBus
from ..core.models import TopicEvent, ResearchItem, BranchNode, ResearchDossier
from ..storage.db import ResearchDB
from .base import BaseAgent
from .stitcher import ResearchStitcher
from .specialized import (
    WikipediaAgent,
    AcademicAgent,
    GitHubAgent,
    DiscussionAgent,
    WebAgent,
    YouTubeAgent
)

logger = logging.getLogger("content_machine.rabbit_hole")


class RabbitHoleCoordinator:
    """
    Coordinates multi-agent pub-sub research, branching down nested rabbit holes.
    """

    def __init__(
        self,
        max_depth: int = 1,
        max_branches_per_node: int = 3,
        db_path: str = "research.db",
        output_dir: str = "output"
    ):
        self.max_depth = max_depth
        self.max_branches_per_node = max_branches_per_node
        self.bus = TopicBus(max_workers=8)
        self.db = ResearchDB(db_path=db_path)
        self.stitcher = ResearchStitcher(output_dir=output_dir)

        self.visited_topics: Set[str] = set()
        self.registered_agents: List[BaseAgent] = []

        self._setup_agents()

    def _setup_agents(self):
        """Instantiate and attach all specialized agents to the bus."""
        agents = [
            WikipediaAgent(bus=self.bus),
            AcademicAgent(bus=self.bus),
            GitHubAgent(bus=self.bus),
            DiscussionAgent(bus=self.bus),
            WebAgent(bus=self.bus),
            YouTubeAgent(bus=self.bus),
        ]
        self.registered_agents = agents

        # Also register database persistence on findings
        self.bus.subscribe("finding", self._persist_finding)

    def _persist_finding(self, item: ResearchItem):
        """Save finding directly to SQLite storage."""
        self.db.save_item(item)

    def explore_topic(self, root_topic: str) -> ResearchDossier:
        """
        Main entrypoint:
        1. Explores root topic via multi-agent pub-sub.
        2. Discovers subtopics and branches down the rabbit hole.
        3. Stitches all branches into a master dossier and script outline.
        """
        clean_topic = root_topic.strip()
        logger.info("🎬 Starting Rabbit Hole Exploration for root topic: '%s'", clean_topic)
        print(f"\n🚀 [PUB-SUB BUS] Publishing Root Topic: '{clean_topic}'")
        print("=" * 80)

        # Track visited
        self.visited_topics.add(clean_topic.lower())

        # Step 1: Root Exploration
        root_event = TopicEvent(topic=clean_topic, depth=0, parent_topic=None)
        self.db.record_topic(root_event)
        root_findings: List[ResearchItem] = self.bus.publish_topic(root_event)

        print(f"✅ Root research complete: {len(root_findings)} structured items collected.")

        # Step 2: Extract Subtopic Branches for Rabbit Hole
        subtopics = self._extract_subtopics(clean_topic, root_findings)
        print(f"\n🐇 Identified {len(subtopics)} Rabbit-Hole Branches:")
        for idx, sub in enumerate(subtopics, 1):
            print(f"   {idx}. ↳ {sub}")

        root_node = BranchNode(
            topic=clean_topic,
            depth=0,
            parent_topic=None,
            findings=root_findings,
            keywords=[s for s in subtopics]
        )

        all_findings: List[ResearchItem] = list(root_findings)

        # Step 3: Branch Exploration (Depth 1)
        if self.max_depth >= 1 and subtopics:
            print("\n" + "=" * 80)
            print("🔍 Diving down the Rabbit Hole (Depth 1 branches)...")
            print("=" * 80)

            for sub in subtopics[:self.max_branches_per_node]:
                if sub.lower() in self.visited_topics:
                    continue
                self.visited_topics.add(sub.lower())

                branch_event = TopicEvent(
                    topic=sub,
                    depth=1,
                    parent_topic=clean_topic,
                    branch_path=[clean_topic, sub]
                )
                self.db.record_topic(branch_event)
                print(f"\n📡 Branching into: '{sub}'...")

                branch_findings: List[ResearchItem] = self.bus.publish_topic(branch_event)
                all_findings.extend(branch_findings)

                branch_keywords = self._extract_subtopics(sub, branch_findings)
                branch_node = BranchNode(
                    topic=sub,
                    depth=1,
                    parent_topic=clean_topic,
                    findings=branch_findings,
                    keywords=branch_keywords[:4]
                )
                root_node.sub_branches.append(branch_node)
                print(f"   ↳ Collected {len(branch_findings)} items for '{sub}'")

        # Step 4: Stitch and Synthesize
        print("\n" + "=" * 80)
        print("🧵 Stitching structured research into Master Dossier & Video Script...")
        print("=" * 80)

        # Deduplicate all findings by ID
        unique_findings = []
        seen_ids = set()
        for f in all_findings:
            if f.id not in seen_ids:
                seen_ids.add(f.id)
                unique_findings.append(f)

        dossier = self.stitcher.stitch(root_node, unique_findings)

        print("\n🎉 Research Synthesis Complete!")
        print(f"📊 Total Sources Stitched: {dossier.total_sources}")
        print(f"🖼️ Bento HTML Dashboard: {dossier.html_dashboard_path}")
        print(f"📄 Master Markdown Report: {dossier.markdown_report_path}")
        print(f"💾 JSON Research Dossier: {dossier.json_dossier_path}")
        print(f"🎬 Video Script Outline:  {dossier.script_outline_path}")

        db_stats = self.db.get_stats()
        print(f"🗄️ Database Stats: {db_stats.get('total_sources', 0)} sources stored across {len(db_stats.get('by_collector', {}))} collectors.")

        return dossier

    def _extract_subtopics(self, current_topic: str, findings: List[ResearchItem]) -> List[str]:
        """
        Analyze findings to extract salient technical subtopics for branching.
        Combines entities, titles, and high-frequency keywords.
        """
        stop_words = {
            "the", "and", "for", "with", "this", "that", "from", "are", "overview", "introduction",
            "guide", "system", "systems", "using", "used", "into", "between", "under", "about", "what", "which",
            "wikipedia", "github", "points", "comments", "discussion", "video", "tutorial",
            "files", "users", "user", "file", "code", "work", "time", "year", "years", "name",
            "list", "part", "various", "stars", "star", "true", "false", "none", "null", "more",
            "free", "band", "know", "need", "things", "want", "like", "tell", "show", "look", "looking",
            "ask", "post", "posts", "where", "when", "some", "good", "best", "help", "here", "item",
            "join", "startup", "developer", "mentor", "thoughts", "versus"
        }

        current_words = set(current_topic.lower().split())
        candidates = Counter()

        for item in findings:
            # 1. Use extracted entities
            for ent in item.entities:
                if ent and isinstance(ent, str):
                    ent_clean = ent.strip()
                    if (
                        len(ent_clean) > 3
                        and ent_clean.lower() not in stop_words
                        and ent_clean.lower() not in current_words
                    ):
                        # Give bonus to multi-word concepts
                        weight = 4 if " " in ent_clean else 2
                        candidates[ent_clean] += weight

            # 2. Extract noun phrases / capitalized words from titles
            title_clean = re.sub(r"\[.*?\]|\(.*?\)", "", item.title)
            # Find multi-word capitalized phrases first
            multi_caps = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]+(?:\s+[A-Z][a-zA-Z0-9_\-]+)+\b", title_clean)
            for mc in multi_caps:
                if mc.lower() not in current_words and not any(w.lower() in stop_words for w in mc.split()):
                    candidates[mc] += 4

            single_caps = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]{3,}\b", title_clean)
            for sc in single_caps:
                if sc.lower() not in stop_words and sc.lower() not in current_words:
                    candidates[sc] += 1

            # 3. Extract key phrases from facts
            for fact in item.key_facts:
                if fact and isinstance(fact, str):
                    fact_entities = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]{3,}\b", fact)
                    for fe in fact_entities:
                        if fe.lower() not in stop_words and fe.lower() not in current_words:
                            candidates[fe] += 1

        # Pick top distinct candidates
        selected = []
        for phrase, _ in candidates.most_common(20):
            # Avoid substrings or duplicates
            phrase_lower = phrase.lower()
            if not any(phrase_lower in s.lower() or s.lower() in phrase_lower for s in selected):
                selected.append(phrase)
            if len(selected) >= self.max_branches_per_node:
                break

        # Fallback if findings had few entities
        if not selected:
            selected = [
                f"{current_topic} Architecture",
                f"{current_topic} Components",
                f"{current_topic} Tools"
            ]

        return selected
