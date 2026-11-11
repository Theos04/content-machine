"""
Specialized research agents for Content Machine.
"""

from .wikipedia_agent import WikipediaAgent
from .academic_agent import AcademicAgent
from .github_agent import GitHubAgent
from .discussion_agent import DiscussionAgent
from .web_agent import WebAgent
from .youtube_agent import YouTubeAgent

__all__ = [
    "WikipediaAgent",
    "AcademicAgent",
    "GitHubAgent",
    "DiscussionAgent",
    "WebAgent",
    "YouTubeAgent"
]
