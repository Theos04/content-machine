"""
Community & Discussion Agent.
Extracts insights, engineering debates, and real-world trade-offs from HackerNews.
"""

import urllib.request
import urllib.parse
import json
import logging
import re
from typing import List

from ..base import BaseAgent
from ...core.models import TopicEvent, ResearchItem

logger = logging.getLogger("content_machine.agent.discussion")


class DiscussionAgent(BaseAgent):
    def __init__(self, bus=None, max_results: int = 4):
        super().__init__(name="DiscussionAgent", bus=bus, rate_limit_seconds=0.3)
        self.max_results = max_results

    def research(self, event: TopicEvent) -> List[ResearchItem]:
        findings: List[ResearchItem] = []
        findings.extend(self._query_hackernews(event))
        return findings

    def _query_hackernews(self, event: TopicEvent) -> List[ResearchItem]:
        query = urllib.parse.quote_plus(event.topic)
        url = f"https://hn.algolia.com/api/v1/search?query={query}&tags=story&hitsPerPage={self.max_results}"

        req = urllib.request.Request(url, headers={"User-Agent": "ContentMachineBot/1.0"})
        results = []
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                hits = data.get("hits", [])

                for hit in hits:
                    raw_title = hit.get("title", "")
                    # Clean conversational prefixes like Ask HN:, Show HN:
                    title = re.sub(r"^(?:Ask HN|Show HN|Tell HN|HN)\s*:\s*", "", raw_title, flags=re.IGNORECASE).strip()
                    target_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                    points = hit.get("points", 0)
                    num_comments = hit.get("num_comments", 0)
                    author = hit.get("author", "anonymous")
                    created_at = hit.get("created_at", "")[:10]

                    hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"

                    key_facts = [
                        f"Discussion Score: {points} points",
                        f"Community Comments: {num_comments} comments",
                        f"HN Discussion Link: {hn_url}"
                    ]

                    results.append(ResearchItem(
                        topic=event.topic,
                        depth=event.depth,
                        parent_topic=event.parent_topic,
                        source_type="hackernews",
                        source="HackerNews Community",
                        title=f"{title} ({points} pts)",
                        url=target_url,
                        author=author,
                        published=created_at,
                        summary=f"Community discussion with {points} points and {num_comments} comments on '{title}'.",
                        key_facts=key_facts,
                        entities=[author],
                        relevance_score=0.8
                    ))
        except Exception as e:
            logger.warning("HackerNews search failed for '%s': %s", event.topic, e)

        return results
