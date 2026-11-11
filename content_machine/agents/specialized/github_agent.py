"""
GitHub Research Agent.
Extracts open-source projects, implementations, architectural blueprints, and tools.
"""

import urllib.request
import urllib.parse
import json
import logging
from typing import List

from ..base import BaseAgent
from ...core.models import TopicEvent, ResearchItem

logger = logging.getLogger("content_machine.agent.github")


class GitHubAgent(BaseAgent):
    def __init__(self, bus=None, max_results: int = 4):
        super().__init__(name="GitHubAgent", bus=bus, rate_limit_seconds=0.5)
        self.max_results = max_results

    def research(self, event: TopicEvent) -> List[ResearchItem]:
        query = urllib.parse.quote_plus(event.topic)
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page={self.max_results}"

        headers = {
            "User-Agent": "ContentMachineBot/1.0",
            "Accept": "application/vnd.github.v3+json"
        }
        req = urllib.request.Request(url, headers=headers)

        findings: List[ResearchItem] = []
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", [])

                for item in items:
                    full_name = item.get("full_name", "")
                    desc = item.get("description", "No description provided.") or "No description provided."
                    repo_url = item.get("html_url", "")
                    stars = item.get("stargazers_count", 0)
                    language = item.get("language", "Various")
                    topics = item.get("topics", [])

                    key_facts = [
                        f"Primary Language: {language}",
                        f"GitHub Stars: {stars:,}",
                        f"Topics: {', '.join(topics[:4]) if topics else 'None'}"
                    ]

                    findings.append(ResearchItem(
                        topic=event.topic,
                        depth=event.depth,
                        parent_topic=event.parent_topic,
                        source_type="github",
                        source="GitHub",
                        title=f"{full_name} ({stars:,} ★)",
                        url=repo_url,
                        summary=f"{desc} [Built with {language}, {stars:,} GitHub stars]",
                        key_facts=key_facts,
                        entities=topics[:5] if topics else [language],
                        relevance_score=0.88
                    ))
        except Exception as e:
            logger.warning("GitHub search failed for '%s': %s", event.topic, e)

        return findings
