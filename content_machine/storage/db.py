"""
SQLite database storage for multi-agent topics, branches, and structured research items.
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..core.models import ResearchItem, TopicEvent

logger = logging.getLogger("content_machine.storage")


class ResearchDB:
    def __init__(self, db_path: str = "research.db"):
        self.db_path = str(Path(db_path).resolve())
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Create normalized schema if not already present."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Topics & Branches
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS topics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL,
                        parent_topic TEXT,
                        depth INTEGER DEFAULT 0,
                        branch_path TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(topic, depth, parent_topic)
                    )
                """)

                # Sources & Findings
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sources (
                        id TEXT PRIMARY KEY,
                        topic TEXT NOT NULL,
                        parent_topic TEXT,
                        depth INTEGER DEFAULT 0,
                        collector TEXT NOT NULL,
                        title TEXT NOT NULL,
                        url TEXT,
                        summary TEXT,
                        published TEXT,
                        relevance_score REAL DEFAULT 1.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Entities & Keywords linked to findings
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS entities (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        entity TEXT NOT NULL,
                        source_id TEXT,
                        topic TEXT,
                        FOREIGN KEY (source_id) REFERENCES sources (id)
                    )
                """)

                # Key facts
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS facts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fact TEXT NOT NULL,
                        source_id TEXT,
                        topic TEXT,
                        FOREIGN KEY (source_id) REFERENCES sources (id)
                    )
                """)

                conn.commit()
                logger.debug("Database initialized at %s", self.db_path)
        except Exception as e:
            logger.error("Database initialization failed: %s", e)
            raise

    def record_topic(self, event: TopicEvent):
        """Save a topic event to the topics table."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO topics (topic, parent_topic, depth, branch_path)
                    VALUES (?, ?, ?, ?)
                """, (event.topic, event.parent_topic, event.depth, " -> ".join(event.branch_path)))
                conn.commit()
        except Exception as e:
            logger.error("Failed recording topic: %s", e)

    def save_item(self, item: ResearchItem) -> bool:
        """Save a structured research item and its entities/facts."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO sources (
                        id, topic, parent_topic, depth, collector, title, url, summary, published, relevance_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.id, item.topic, item.parent_topic, item.depth, item.source_type,
                    item.title, item.url, item.summary, item.published, item.relevance_score
                ))

                for ent in item.entities:
                    if ent:
                        cursor.execute("""
                            INSERT INTO entities (entity, source_id, topic)
                            VALUES (?, ?, ?)
                        """, (str(ent).lower().strip(), item.id, item.topic))

                for fact in item.key_facts:
                    if fact:
                        cursor.execute("""
                            INSERT INTO facts (fact, source_id, topic)
                            VALUES (?, ?, ?)
                        """, (str(fact).strip(), item.id, item.topic))

                conn.commit()
                return True
        except Exception as e:
            logger.error("Failed saving research item %s: %s", item.title, e)
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics of collected research."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM topics")
                total_topics = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM sources")
                total_sources = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM entities")
                total_entities = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT collector, COUNT(*) as count
                    FROM sources
                    GROUP BY collector
                    ORDER BY count DESC
                """)
                by_collector = dict(cursor.fetchall())

                return {
                    "total_topics": total_topics,
                    "total_sources": total_sources,
                    "total_entities": total_entities,
                    "by_collector": by_collector
                }
        except Exception as e:
            logger.error("Failed getting stats: %s", e)
            return {}
