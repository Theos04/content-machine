"""
Content Machine package.
"""

from .core.bus import TopicBus
from .core.models import TopicEvent, ResearchItem, BranchNode, ResearchDossier
from .storage.db import ResearchDB


def run_pipeline(*args, **kwargs):
    from .pipeline import run_pipeline as _run_pipeline
    return _run_pipeline(*args, **kwargs)


def parse_pipeline_command(*args, **kwargs):
    from .pipeline import parse_pipeline_command as _parse_pipeline_command
    return _parse_pipeline_command(*args, **kwargs)


__all__ = [
    "run_pipeline",
    "parse_pipeline_command",
    "TopicBus",
    "TopicEvent",
    "ResearchItem",
    "BranchNode",
    "ResearchDossier",
    "ResearchDB"
]
