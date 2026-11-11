"""
Pub-Sub topic event bus for multi-agent dispatch and messaging.
Uses Python's relative imports to connect with core models.
"""

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Any, Optional

from .models import TopicEvent, ResearchItem

logger = logging.getLogger("content_machine.bus")


class TopicBus:
    """
    Central event and pub-sub bus for agent coordination.
    Allows agents to subscribe to topics, publish sub-topics,
    and report structured research findings.
    """

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self._subscribers: Dict[str, List[Callable[[Any], Any]]] = defaultdict(list)
        self._event_history: List[TopicEvent] = []
        self._findings: List[ResearchItem] = []

    def subscribe(self, channel: str, handler: Callable[[Any], Any]):
        """
        Subscribe a callable handler to a channel.
        Channels can be 'topic:*', 'topic:root', 'topic:branch', 'finding', etc.
        """
        self._subscribers[channel].append(handler)
        logger.debug("Subscribed %s to channel '%s'", getattr(handler, '__name__', str(handler)), channel)

    def publish_topic(self, event: TopicEvent) -> List[Any]:
        """
        Publish a topic event to all matching subscribers.
        Dispatches to subscribers in parallel using a ThreadPoolExecutor.
        """
        self._event_history.append(event)
        channel = "topic:root" if event.depth == 0 else "topic:branch"
        handlers = self._subscribers.get(channel, []) + self._subscribers.get("topic:*", []) + self._subscribers.get("*", [])

        # Deduplicate handlers while preserving order
        unique_handlers = []
        seen = set()
        for h in handlers:
            if h not in seen:
                seen.add(h)
                unique_handlers.append(h)

        if not unique_handlers:
            logger.warning("No subscribers registered for topic '%s' (depth %d)", event.topic, event.depth)
            return []

        results = []
        with ThreadPoolExecutor(max_workers=min(len(unique_handlers), self.max_workers)) as executor:
            future_to_handler = {executor.submit(h, event): h for h in unique_handlers}
            for future in as_completed(future_to_handler):
                h = future_to_handler[future]
                try:
                    res = future.result()
                    if res:
                        if isinstance(res, list):
                            results.extend(res)
                        else:
                            results.append(res)
                except Exception as e:
                    logger.error("Handler %s failed on topic '%s': %s", getattr(h, '__name__', str(h)), event.topic, e, exc_info=True)

        return results

    def report_finding(self, item: ResearchItem):
        """Record a structured research finding."""
        self._findings.append(item)
        handlers = self._subscribers.get("finding", [])
        for h in handlers:
            try:
                h(item)
            except Exception as e:
                logger.error("Finding subscriber failed: %s", e)

    def get_findings(self, topic: Optional[str] = None) -> List[ResearchItem]:
        """Retrieve all recorded findings, optionally filtered by topic."""
        if topic is None:
            return list(self._findings)
        return [f for f in self._findings if f.topic.lower() == topic.lower()]

    def clear(self):
        """Clear findings and history."""
        self._findings.clear()
        self._event_history.clear()
