"""
Base Agent class for the multi-agent research architecture.
All specialized research agents inherit from BaseAgent and use relative imports.
"""

import abc
import logging
import time
from typing import List, Optional

from ..core.bus import TopicBus
from ..core.models import TopicEvent, ResearchItem

logger = logging.getLogger("content_machine.agent")


class BaseAgent(abc.ABC):
    """
    Abstract Base Class for research agents.
    Handles bus subscription, safe execution boundaries, and rate limiting.
    """

    def __init__(self, name: str, bus: Optional[TopicBus] = None, rate_limit_seconds: float = 0.2):
        self.name = name
        self.bus = bus
        self.rate_limit_seconds = rate_limit_seconds
        self._last_call = 0.0

        if self.bus is not None:
            self.attach_to_bus(self.bus)

    def attach_to_bus(self, bus: TopicBus):
        """Register this agent's topic handler to the central bus."""
        self.bus = bus
        self.bus.subscribe("topic:*", self.on_topic_event)
        logger.debug("Agent '%s' attached to TopicBus", self.name)

    def _throttle(self):
        """Respectful rate limiting between network calls."""
        now = time.time()
        elapsed = now - self._last_call
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_call = time.time()

    def on_topic_event(self, event: TopicEvent) -> List[ResearchItem]:
        """
        Invoked whenever a topic is published to the bus.
        Executes the agent's research and reports findings back to the bus.
        """
        try:
            self._throttle()
            logger.info("Agent [%s] researching: '%s' (depth %d)", self.name, event.topic, event.depth)
            findings = self.research(event)

            # Ensure all findings carry the correct topic and lineage
            for f in findings:
                f.topic = event.topic
                f.depth = event.depth
                f.parent_topic = event.parent_topic
                if self.bus is not None:
                    self.bus.report_finding(f)

            logger.info("Agent [%s] produced %d items for '%s'", self.name, len(findings), event.topic)
            return findings
        except Exception as e:
            logger.error("Agent [%s] failed on topic '%s': %s", self.name, event.topic, e, exc_info=True)
            return []

    @abc.abstractmethod
    def research(self, event: TopicEvent) -> List[ResearchItem]:
        """Specialized agent implementation to fetch and structure research."""
        pass
