"""
YouTube Research Agent.
Extracts video metadata, video tutorials, and technical explanations using yt-dlp.
"""

import logging
from typing import List

from ..base import BaseAgent
from ...core.models import TopicEvent, ResearchItem

logger = logging.getLogger("content_machine.agent.youtube")


class YouTubeAgent(BaseAgent):
    def __init__(self, bus=None, max_results: int = 3):
        super().__init__(name="YouTubeAgent", bus=bus, rate_limit_seconds=0.5)
        self.max_results = max_results
        self._has_ytdlp = False
        try:
            import yt_dlp
            self._has_ytdlp = True
        except ImportError:
            self._has_ytdlp = False

    def research(self, event: TopicEvent) -> List[ResearchItem]:
        if not self._has_ytdlp:
            logger.debug("yt-dlp not available, skipping YouTube search")
            return []

        import yt_dlp
        findings: List[ResearchItem] = []
        search_query = f"ytsearch{self.max_results}:{event.topic}"

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
            "ignoreerrors": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
                entries = info.get("entries", []) if info else []

                for entry in entries:
                    if not entry:
                        continue
                    title = entry.get("title", "")
                    video_url = entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                    channel = entry.get("uploader") or entry.get("channel", "YouTube Creator")
                    duration = entry.get("duration", 0)

                    findings.append(ResearchItem(
                        topic=event.topic,
                        depth=event.depth,
                        parent_topic=event.parent_topic,
                        source_type="youtube",
                        source=f"YouTube ({channel})",
                        title=f"{title} [Video]",
                        url=video_url,
                        author=channel,
                        summary=f"Video tutorial on '{event.topic}' by {channel}. Duration: {int(duration)//60}m {int(duration)%60}s.",
                        key_facts=[f"Channel: {channel}", f"Duration: {duration}s"],
                        entities=[channel],
                        relevance_score=0.82
                    ))
        except Exception as e:
            logger.warning("YouTube search failed for '%s': %s", event.topic, e)

        return findings
