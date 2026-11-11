"""
Academic Research Agent.
Harvests peer-reviewed papers, arXiv preprints, CrossRef publications, and DOIs.
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import re
import logging
from typing import List

from ..base import BaseAgent
from ...core.models import TopicEvent, ResearchItem

logger = logging.getLogger("content_machine.agent.academic")


class AcademicAgent(BaseAgent):
    def __init__(self, bus=None, max_results: int = 3):
        super().__init__(name="AcademicAgent", bus=bus, rate_limit_seconds=0.4)
        self.max_results = max_results

    def research(self, event: TopicEvent) -> List[ResearchItem]:
        findings: List[ResearchItem] = []

        # 1. arXiv Query
        findings.extend(self._query_arxiv(event))

        # 2. CrossRef Query
        findings.extend(self._query_crossref(event))

        return findings

    def _query_arxiv(self, event: TopicEvent) -> List[ResearchItem]:
        query = urllib.parse.quote_plus(event.topic)
        url = f"http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={self.max_results}"
        req = urllib.request.Request(url, headers={"User-Agent": "ContentMachineBot/1.0"})

        results = []
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                xml_data = resp.read().decode("utf-8")
                root = ET.fromstring(xml_data)
                ns = {"atom": "http://www.w3.org/2005/Atom"}

                for entry in root.findall("atom:entry", ns):
                    title_el = entry.find("atom:title", ns)
                    summary_el = entry.find("atom:summary", ns)
                    link_el = entry.find("atom:id", ns)
                    published_el = entry.find("atom:published", ns)

                    title = title_el.text.strip().replace("\n", " ") if title_el is not None else "Untitled"
                    summary = summary_el.text.strip().replace("\n", " ") if summary_el is not None else ""
                    paper_url = link_el.text.strip() if link_el is not None else ""
                    published = published_el.text.strip()[:10] if published_el is not None else ""

                    authors = [
                        a.find("atom:name", ns).text.strip()
                        for a in entry.findall("atom:author", ns)
                        if a.find("atom:name", ns) is not None
                    ]

                    key_facts = [s.strip() for s in summary.split(". ") if len(s.strip()) > 30][:2]
                    entities = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]{2,}\b", title)

                    results.append(ResearchItem(
                        topic=event.topic,
                        depth=event.depth,
                        parent_topic=event.parent_topic,
                        source_type="arxiv",
                        source="arXiv",
                        title=title,
                        url=paper_url,
                        author=", ".join(authors[:3]),
                        published=published,
                        summary=summary[:600] + "..." if len(summary) > 600 else summary,
                        key_facts=key_facts,
                        entities=list(set(entities))[:5],
                        relevance_score=0.9
                    ))
        except Exception as e:
            logger.warning("arXiv query failed for '%s': %s", event.topic, e)

        return results

    def _query_crossref(self, event: TopicEvent) -> List[ResearchItem]:
        query = urllib.parse.quote_plus(event.topic)
        url = f"https://api.crossref.org/works?query={query}&rows={self.max_results}&sort=relevance"
        req = urllib.request.Request(url, headers={"User-Agent": "ContentMachineBot/1.0 (mailto:research@contentmachine.local)"})

        results = []
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("message", {}).get("items", [])
                for item in items:
                    title_list = item.get("title", [])
                    title = title_list[0] if title_list else "Unknown Title"
                    doi_url = item.get("URL", f"https://doi.org/{item.get('DOI', '')}")
                    publisher = item.get("publisher", "Academic Publisher")

                    abstract = item.get("abstract", "")
                    clean_abstract = re.sub(r"<[^>]+>", "", abstract).strip() if abstract else f"Published by {publisher}."

                    results.append(ResearchItem(
                        topic=event.topic,
                        depth=event.depth,
                        parent_topic=event.parent_topic,
                        source_type="crossref",
                        source=f"CrossRef ({publisher})",
                        title=title,
                        url=doi_url,
                        summary=clean_abstract[:400],
                        key_facts=[f"Publisher: {publisher}"],
                        entities=re.findall(r"\b[A-Z][a-zA-Z0-9_\-]{2,}\b", title)[:4],
                        relevance_score=0.85
                    ))
        except Exception as e:
            logger.warning("CrossRef query failed for '%s': %s", event.topic, e)

        return results
