"""
Data models for the Content Machine multi-agent research and synthesis engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import hashlib


@dataclass
class TopicEvent:
    """Represents a topic published to the agent bus."""
    topic: str
    depth: int = 0
    parent_topic: Optional[str] = None
    branch_path: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.branch_path:
            self.branch_path = [self.topic]


@dataclass
class ResearchItem:
    """A structured finding harvested by an agent."""
    topic: str
    source_type: str  # wikipedia, arxiv, crossref, github, hackernews, duckduckgo, web, youtube
    title: str
    url: str
    summary: str
    depth: int = 0
    parent_topic: Optional[str] = None
    source: str = ""
    author: str = ""
    published: str = ""
    key_facts: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    relevance_score: float = 1.0
    id: str = ""

    def __post_init__(self):
        if not self.id:
            # Deterministic unique ID based on URL or title + topic
            unique_str = f"{self.source_type}:{self.url or self.title}:{self.topic}"
            self.id = hashlib.sha256(unique_str.encode('utf-8')).hexdigest()[:16]
        if not self.source:
            self.source = self.source_type


@dataclass
class BranchNode:
    """A node in the hierarchical rabbit-hole research tree."""
    topic: str
    depth: int
    parent_topic: Optional[str] = None
    findings: List[ResearchItem] = field(default_factory=list)
    sub_branches: List['BranchNode'] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "depth": self.depth,
            "parent_topic": self.parent_topic,
            "summary": self.summary,
            "keywords": self.keywords,
            "findings_count": len(self.findings),
            "findings": [
                {
                    "id": item.id,
                    "title": item.title,
                    "url": item.url,
                    "source": item.source,
                    "source_type": item.source_type,
                    "summary": item.summary,
                    "key_facts": item.key_facts,
                    "entities": item.entities
                }
                for item in self.findings
            ],
            "sub_branches": [sub.to_dict() for sub in self.sub_branches]
        }


@dataclass
class ResearchDossier:
    """Master research dossier stitching together the entire rabbit hole."""
    root_topic: str
    created_at: str
    total_sources: int
    tree: BranchNode
    all_findings: List[ResearchItem]
    executive_summary: str
    key_takeaways: List[str]
    script_outline: List[Dict[str, Any]]
    markdown_report_path: Optional[str] = None
    json_dossier_path: Optional[str] = None
    script_outline_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_topic": self.root_topic,
            "created_at": self.created_at,
            "total_sources": self.total_sources,
            "executive_summary": self.executive_summary,
            "key_takeaways": self.key_takeaways,
            "script_outline": self.script_outline,
            "tree": self.tree.to_dict(),
            "sources": [
                {
                    "title": f.title,
                    "url": f.url,
                    "source": f.source,
                    "source_type": f.source_type,
                    "topic": f.topic,
                    "depth": f.depth,
                    "summary": f.summary[:200]
                }
                for f in self.all_findings
            ]
        }
