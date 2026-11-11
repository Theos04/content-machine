"""
Wikipedia Research Agent.
Extracts deep encyclopedic articles, summaries, and conceptual entities.
"""

import urllib.request
import urllib.parse
import json
import re
import logging
from typing import List, Optional

from ..base import BaseAgent
from ...core.models import TopicEvent, ResearchItem

logger = logging.getLogger("content_machine.agent.wikipedia")


class WikipediaAgent(BaseAgent):
    def __init__(self, bus=None, max_results: int = 4):
        super().__init__(name="WikipediaAgent", bus=bus, rate_limit_seconds=0.3)
        self.max_results = max_results

    def research(self, event: TopicEvent) -> List[ResearchItem]:
        query = event.topic
        encoded_query = urllib.parse.quote_plus(query)
        search_url = (
            f"https://en.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={encoded_query}&utf8=1&format=json&srlimit={self.max_results}"
        )

        headers = {"User-Agent": "ContentMachineBot/1.0 (https://github.com/theos/content-machine)"}
        req = urllib.request.Request(search_url, headers=headers)

        findings: List[ResearchItem] = []
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8"))
                search_results = data.get("query", {}).get("search", [])

                for result in search_results:
                    title = result.get("title", "")
                    page_id = result.get("pageid")
                    clean_snippet = re.sub(r"<[^>]+>", "", result.get("snippet", "")).strip()

                    # Fetch full lead section extract for deep research
                    extract, full_url = self._fetch_lead_extract(title, headers)

                    summary = extract if extract else clean_snippet
                    key_facts = self._extract_facts(summary)
                    entities = self._extract_entities(summary)

                    findings.append(ResearchItem(
                        topic=event.topic,
                        depth=event.depth,
                        parent_topic=event.parent_topic,
                        source_type="wikipedia",
                        source="Wikipedia",
                        title=title,
                        url=full_url or f"https://en.wikipedia.org/?curid={page_id}",
                        summary=summary,
                        key_facts=key_facts,
                        entities=entities,
                        relevance_score=0.95
                    ))
        except Exception as e:
            logger.error("Wikipedia search failed for '%s': %s", query, e)

        return findings

    def _fetch_lead_extract(self, title: str, headers: dict) -> (str, str):
        """Fetch lead section intro text for a Wikipedia title."""
        try:
            encoded_title = urllib.parse.quote(title)
            url = (
                f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts|info"
                f"&inprop=url&exintro=1&explaintext=1&titles={encoded_title}&format=json"
            )
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pages = data.get("query", {}).get("pages", {})
                for page in pages.values():
                    extract = page.get("extract", "").strip()
                    canonical_url = page.get("fullurl", "")
                    return extract, canonical_url
        except Exception:
            pass
        return "", ""

    def _extract_facts(self, text: str) -> List[str]:
        """Extract high-value factual statements from text."""
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 30]
        # Return first 3 informative sentences
        return sentences[:3]

    def _extract_entities(self, text: str) -> List[str]:
        """Extract capitalized multi-word technical concepts and entities."""
        candidates = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]+(?:\s+[A-Z][a-zA-Z0-9_\-]+)*\b", text)
        filtered = [
            c for c in candidates
            if len(c) > 3 and c.lower() not in {"the", "this", "that", "there", "these", "wikipedia", "further"}
        ]
        # Return unique top entities
        return list(dict.fromkeys(filtered))[:6]
