"""
Research Stitcher & Synthesizer.
Takes the nested rabbit-hole research tree and stitches everything into:
1. Master Research Dossier (JSON)
2. Comprehensive Markdown Dossier & Report
3. Video Script Blueprint & Production Outline
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..core.models import BranchNode, ResearchDossier, ResearchItem


class ResearchStitcher:
    """
    Synthesizes and stitches multi-branch research findings into
    structured knowledge dossiers, comprehensive reports, and video outlines.
    """

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def stitch(self, root_node: BranchNode, all_findings: List[ResearchItem]) -> ResearchDossier:
        """Stitch all tree nodes and findings into a unified ResearchDossier."""
        root_topic = root_node.topic
        safe_topic = root_topic.replace(" ", "_").lower()
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Generate Executive Summary
        exec_summary = self._synthesize_executive_summary(root_node, all_findings)

        # 2. Extract Key Takeaways
        key_takeaways = self._extract_key_takeaways(root_node, all_findings)

        # 3. Generate Video Script Outline
        script_outline = self._generate_script_outline(root_node, all_findings)

        # 4. Build Dossier object
        dossier = ResearchDossier(
            root_topic=root_topic,
            created_at=timestamp,
            total_sources=len(all_findings),
            tree=root_node,
            all_findings=all_findings,
            executive_summary=exec_summary,
            key_takeaways=key_takeaways,
            script_outline=script_outline
        )

        # 5. Export JSON Dossier
        json_file = self.output_dir / f"{safe_topic}_dossier.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(dossier.to_dict(), f, indent=2, ensure_ascii=False)
        dossier.json_dossier_path = str(json_file)

        # 6. Export Markdown Report
        md_file = self.output_dir / f"{safe_topic}_research_report.md"
        markdown_content = self._generate_markdown_report(dossier)
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        dossier.markdown_report_path = str(md_file)

        # Also write a copy to agents/research-agent/reports/ for backwards compatibility
        compat_reports_dir = Path("agents/research-agent/reports")
        if compat_reports_dir.exists():
            compat_file = compat_reports_dir / f"{safe_topic}_report.txt"
            with open(compat_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)

        # 7. Export Script Outline Markdown
        script_file = self.output_dir / f"{safe_topic}_script_outline.md"
        script_md = self._generate_script_markdown(dossier)
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(script_md)
        dossier.script_outline_path = str(script_file)

        # 8. Export Modern Bento Grid & Kanban HTML Dashboard
        from ..ui.dashboard import generate_html_dashboard
        html_file = self.output_dir / f"{safe_topic}_dashboard.html"
        generate_html_dashboard(dossier, str(html_file))
        dossier.html_dashboard_path = str(html_file)

        return dossier

    def _synthesize_executive_summary(self, root_node: BranchNode, all_findings: List[ResearchItem]) -> str:
        """Create a holistic summary connecting the root topic to its branches."""
        branches_str = ", ".join([b.topic for b in root_node.sub_branches]) if root_node.sub_branches else "core domains"

        # Prioritize encyclopedic, instant answer, or academic summaries
        authoritative = [
            f for f in root_node.findings
            if f.source_type in {"wikipedia", "duckduckgo", "arxiv", "crossref"} and f.summary
        ]
        other_summaries = [f for f in root_node.findings if f.summary and f not in authoritative]

        candidates = authoritative + other_summaries
        top_summaries = []
        for f in candidates[:3]:
            first_sent = f.summary.split(". ")[0].strip()
            if first_sent and len(first_sent) > 20:
                top_summaries.append(first_sent + ".")

        core_overview = " ".join(top_summaries) if top_summaries else f"Comprehensive investigation into {root_node.topic}."

        return (
            f"This dossier synthesizes structured multi-source research into '{root_node.topic}'. "
            f"{core_overview} "
            f"Investigation expanded across key rabbit-hole sub-domains including {branches_str}, "
            f"consolidating findings from encyclopedic knowledge, academic literature, open-source repositories, "
            f"and community engineering discussions."
        )

    def _extract_key_takeaways(self, root_node: BranchNode, all_findings: List[ResearchItem]) -> List[str]:
        """Aggregate unique facts and high-impact technical takeaways."""
        facts = []
        seen = set()

        # Prioritize academic, wikipedia, and github facts over forum comment counts
        sorted_findings = sorted(
            all_findings,
            key=lambda x: 0 if x.source_type in {"arxiv", "crossref", "wikipedia", "github"} else 1
        )

        for item in sorted_findings:
            for fact in item.key_facts:
                clean = fact.strip()
                # Skip trivial stats like comment counts for top facts
                if any(kw in clean.lower() for kw in ["discussion link", "comments on"]):
                    continue
                if clean and clean not in seen and len(clean) > 10:
                    seen.add(clean)
                    facts.append(f"**[{item.source}]** {clean}")
                if len(facts) >= 8:
                    break
            if len(facts) >= 8:
                break

        if not facts:
            facts = [
                f"Multi-layered exploration across {len(root_node.sub_branches)} distinct sub-topic branches.",
                f"Aggregated {len(all_findings)} structured references from academic and developer ecosystems.",
                f"Established foundational concepts and concrete implementation tooling."
            ]

        return facts

    def _generate_script_outline(self, root_node: BranchNode, all_findings: List[ResearchItem]) -> List[Dict[str, Any]]:
        """Generate structured video scenes with timing, cues, and narration points."""
        scenes = []

        # Scene 1: The Hook
        scenes.append({
            "scene_number": 1,
            "section": "The Hook & Problem Statement",
            "est_duration": "00:00 - 00:30",
            "visual_cue": "Fast-paced dynamic title montage, high-impact keyword zoom-ins",
            "talking_points": [
                f"Grab attention with the core premise of {root_node.topic}.",
                "State why this topic is essential and commonly misunderstood in the ecosystem."
            ],
            "keywords": [root_node.topic.split()[0], "architecture", "ecosystem"]
        })

        # Scene 2: Foundational Overview
        scenes.append({
            "scene_number": 2,
            "section": "Foundations & High-Level Architecture",
            "est_duration": "00:30 - 01:30",
            "visual_cue": "Architectural diagram or knowledge graph overview overlay",
            "talking_points": [
                f"Define {root_node.topic} based on primary encyclopedic and standard definitions.",
                "Outline the components that power the system from the ground up."
            ],
            "keywords": root_node.keywords[:4] if root_node.keywords else ["foundation", "core"]
        })

        # Scenes for each Rabbit-Hole Branch
        for idx, branch in enumerate(root_node.sub_branches, start=3):
            branch_findings = branch.findings
            top_finding = branch_findings[0] if branch_findings else None

            points = [f"Dive into {branch.topic}."]
            if top_finding:
                points.append(f"Key insight from {top_finding.source}: {top_finding.summary[:150]}...")
            if len(branch_findings) > 1:
                points.append(f"Practical tooling & references: {branch_findings[1].title}.")

            scenes.append({
                "scene_number": idx,
                "section": f"Deep Dive: {branch.topic}",
                "est_duration": f"0{idx-2}:30 - 0{idx-1}:30",
                "visual_cue": f"Code walkthrough or repository demonstration for {branch.topic}",
                "talking_points": points,
                "keywords": branch.keywords[:4] if branch.keywords else [branch.topic.split()[0]]
            })

        # Final Scene: Synthesis & Next Steps
        scenes.append({
            "scene_number": len(scenes) + 1,
            "section": "Synthesis, Real-World Impact & Call to Action",
            "est_duration": "Final 60 seconds",
            "visual_cue": "Summary bullet points overlay + final verdict",
            "talking_points": [
                "Summarize how the pieces interconnect.",
                "Provide actionable next steps / recommended open-source repositories to explore.",
                "Call to action: Like, subscribe, and check resources in description."
            ],
            "keywords": ["summary", "future", "ecosystem", "resources"]
        })

        return scenes

    def _generate_markdown_report(self, dossier: ResearchDossier) -> str:
        """Produce a comprehensive, publication-grade Markdown dossier."""
        lines = []
        lines.append(f"# 📚 Comprehensive Research Dossier: {dossier.root_topic}\n")
        lines.append(f"> **Generated:** {dossier.created_at}  ")
        lines.append(f"> **Total Sources Analyzed:** {dossier.total_sources} across multiple specialized agents  ")
        lines.append(f"> **Exploration Branches:** {len(dossier.tree.sub_branches)} nested branches\n")
        lines.append("---\n")

        # Executive Summary
        lines.append("## 🌟 Executive Summary\n")
        lines.append(dossier.executive_summary + "\n\n")

        # Key Takeaways
        lines.append("## 💡 Key Technical Takeaways\n")
        for takeaway in dossier.key_takeaways:
            lines.append(f"- {takeaway}")
        lines.append("\n---\n")

        # Hierarchical Research Tree
        lines.append("## 🌳 Nested Rabbit-Hole Research Tree\n")
        lines.append("```text")
        lines.append(f"📁 {dossier.root_topic} (Root)")
        for branch in dossier.tree.sub_branches:
            lines.append(f" └── 📂 {branch.topic} ({len(branch.findings)} findings)")
            for sub in branch.sub_branches:
                lines.append(f"      └── 📄 {sub.topic} ({len(sub.findings)} findings)")
        lines.append("```\n")

        # Deep Dives per Branch
        lines.append("## 🔬 Deep-Dive Branch Analyses\n")

        # Root findings first
        if dossier.tree.findings:
            lines.append(f"### 📍 Core Topic Findings: {dossier.root_topic}\n")
            for item in dossier.tree.findings:
                lines.append(f"#### 🔗 [{item.source}] {item.title}")
                lines.append(f"- **URL:** {item.url}")
                if item.author:
                    lines.append(f"- **Author/Creator:** {item.author}")
                lines.append(f"- **Summary:** {item.summary}")
                if item.key_facts:
                    lines.append("- **Facts:**")
                    for f in item.key_facts:
                        lines.append(f"  * {f}")
                lines.append("")

        # Branch findings
        for branch in dossier.tree.sub_branches:
            lines.append(f"### 🚀 Branch: {branch.topic}\n")
            if branch.summary:
                lines.append(f"*{branch.summary}*\n")
            if branch.keywords:
                lines.append(f"**Associated Concepts:** `{', '.join(branch.keywords)}`\n")

            for item in branch.findings:
                lines.append(f"#### 🔗 [{item.source}] {item.title}")
                lines.append(f"- **URL:** {item.url}")
                if item.author:
                    lines.append(f"- **Author/Creator:** {item.author}")
                lines.append(f"- **Summary:** {item.summary}")
                if item.key_facts:
                    lines.append("- **Key Findings:**")
                    for f in item.key_facts:
                        lines.append(f"  * {f}")
                lines.append("")

        lines.append("---\n")

        # Source Index
        lines.append("## 📖 Comprehensive Bibliography of Sources\n")
        lines.append("| Source Type | Title | Link |")
        lines.append("| :--- | :--- | :--- |")
        for item in dossier.all_findings:
            safe_title = item.title.replace("|", "-")
            lines.append(f"| `{item.source_type.upper()}` | {safe_title} | [View Source]({item.url}) |")

        lines.append("\n---\n*Report compiled by Content Machine Multi-Agent Synthesizer.*")
        return "\n".join(lines)

    def _generate_script_markdown(self, dossier: ResearchDossier) -> str:
        """Produce a video production script outline from the outline data."""
        lines = []
        lines.append(f"# 🎬 Video Production Script Outline: {dossier.root_topic}\n")
        lines.append(f"> **Target Duration:** 6 - 8 Minutes  ")
        lines.append(f"> **Core Narrative Arc:** Problem → Foundations → Branch Deep Dives → Synthesis\n")
        lines.append("---\n")

        for scene in dossier.script_outline:
            lines.append(f"## Scene {scene['scene_number']}: {scene['section']}")
            lines.append(f"- **Estimated Timecode:** `{scene['est_duration']}`")
            lines.append(f"- **Visual & Camera Cue:** *{scene['visual_cue']}*")
            lines.append(f"- **Trigger Keywords (for Auto-VFX Zoom):** `{', '.join(scene['keywords'])}`")
            lines.append("- **Narration Bullet Points:**")
            for pt in scene["talking_points"]:
                lines.append(f"  * {pt}")
            lines.append("")

        return "\n".join(lines)
