"""
Web & Instant Answers Research Agent.
Extracts concise definitions, infobox summaries, and related subtopics via DuckDuckGo API.
"""

import urllib.request
import urllib.parse
import json
import logging
from typing import List

from ..base import BaseAgent
from ...core.models import TopicEvent, ResearchItem

logger = logging.getLogger("content_machine.agent.web")


class WebAgent(BaseAgent):
    def __init__(self, bus=None, max_results: int = 4):
        super().__init__(name="WebAgent", bus=bus, rate_limit_seconds=0.3)
        self.max_results = max_results

    def research(self, event: TopicEvent) -> List[ResearchItem]:
        query = urllib.parse.quote_plus(event.topic)
        url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=0"

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        findings: List[ResearchItem] = []

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

                # 1. Direct Abstract
                abstract = data.get("AbstractText", "")
                abstract_source = data.get("AbstractSource", "DuckDuckGo")
                abstract_url = data.get("AbstractURL", "")

                if abstract:
                    findings.append(ResearchItem(
                        topic=event.topic,
                        depth=event.depth,
                        parent_topic=event.parent_topic,
                        source_type="duckduckgo",
                        source=f"Instant Answer ({abstract_source})",
                        title=f"{event.topic} Overview",
                        url=abstract_url or f"https://duckduckgo.com/?q={query}",
                        summary=abstract,
                        key_facts=[f"Definition provided by {abstract_source}"],
                        entities=data.get("Entity", "").split(",") if data.get("Entity") else [],
                        relevance_score=0.92
                    ))

                # 2. Related Topics
                related_topics = data.get("RelatedTopics", [])
                count = 0
                for item in related_topics:
                    if count >= self.max_results:
                        break
                    # RelatedTopics can have sub-topics or direct dicts
                    text = item.get("Text", "")
                    first_url = item.get("FirstURL", "")
                    if text and first_url:
                        count += 1
                        title = text.split(" - ")[0] if " - " in text else text[:60]
                        findings.append(ResearchItem(
                            topic=event.topic,
                            depth=event.depth,
                            parent_topic=event.parent_topic,
                            source_type="duckduckgo",
                            source="DuckDuckGo Related Topic",
                            title=title,
                            url=first_url,
                            summary=text,
                            key_facts=[],
                            entities=[title],
                            relevance_score=0.78
                        ))

        except Exception as e:
            logger.warning("DuckDuckGo instant answer failed for '%s': %s", event.topic, e)

        return findings
