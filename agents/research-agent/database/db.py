import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResearchDB:
    def __init__(self, db_path: str = "research.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database with proper schema"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create sources table (matches agent.py call)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sources (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        collector TEXT,
                        title TEXT,
                        content TEXT,
                        url TEXT,
                        source TEXT,
                        published TEXT,
                        query TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create keywords table for graph
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS keywords (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT,
                        source_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (source_id) REFERENCES sources (id)
                    )
                """)
                
                conn.commit()
                logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def add_source(self, collector: str, title: str, content: str, 
                   url: str, source: str, published: str, query: str) -> Optional[int]:
        """Add a source to the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO sources (collector, title, content, url, source, published, query)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (collector, title, content, url, source, published, query))
                
                source_id = cursor.lastrowid
                conn.commit()
                logger.debug(f"Added source: {title[:50]}...")
                return source_id
        except Exception as e:
            logger.error(f"Error adding source: {e}")
            return None
    
    def get_sources(self, query: str = None, collector: str = None) -> List[Dict[str, Any]]:
        """Retrieve sources from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if query and collector:
                    cursor.execute("""
                        SELECT * FROM sources 
                        WHERE query = ? AND collector = ?
                        ORDER BY created_at DESC
                    """, (query, collector))
                elif query:
                    cursor.execute("""
                        SELECT * FROM sources 
                        WHERE query = ?
                        ORDER BY created_at DESC
                    """, (query,))
                elif collector:
                    cursor.execute("""
                        SELECT * FROM sources 
                        WHERE collector = ?
                        ORDER BY created_at DESC
                    """, (collector,))
                else:
                    cursor.execute("SELECT * FROM sources ORDER BY created_at DESC")
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting sources: {e}")
            return []
    
    def add_keyword(self, keyword: str, source_id: int):
        """Add a keyword linked to a source"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO keywords (keyword, source_id)
                    VALUES (?, ?)
                """, (keyword.lower(), source_id))
                conn.commit()
                logger.debug(f"Added keyword: {keyword}")
        except Exception as e:
            logger.error(f"Error adding keyword: {e}")
    
    def get_keywords(self, source_id: int = None) -> List[str]:
        """Get keywords for a source or all keywords"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if source_id:
                    cursor.execute("""
                        SELECT DISTINCT keyword FROM keywords WHERE source_id = ?
                        ORDER BY keyword
                    """, (source_id,))
                else:
                    cursor.execute("SELECT DISTINCT keyword FROM keywords ORDER BY keyword")
                
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting keywords: {e}")
            return []
    
    def clear_all(self):
        """Clear all data (for testing)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM keywords")
                cursor.execute("DELETE FROM sources")
                conn.commit()
                logger.info("Database cleared")
        except Exception as e:
            logger.error(f"Error clearing database: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM sources")
                total_sources = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM keywords")
                total_keywords = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT collector, COUNT(*) as count 
                    FROM sources 
                    GROUP BY collector 
                    ORDER BY count DESC
                """)
                by_collector = dict(cursor.fetchall())
                
                return {
                    'total_sources': total_sources,
                    'total_keywords': total_keywords,
                    'by_collector': by_collector
                }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}

if __name__ == "__main__":
    # Test the database
    db = ResearchDB("test.db")
    print("Database created successfully")
    
    # Test adding a source
    source_id = db.add_source(
        collector="test",
        title="Test Article",
        content="This is test content",
        url="http://example.com",
        source="Test Source",
        published="2024-01-01",
        query="test"
    )
    print(f"Added source with ID: {source_id}")
    
    # Test adding a keyword
    db.add_keyword("test", source_id)
    
    # Test retrieving
    sources = db.get_sources()
    print(f"Found {len(sources)} sources")
    
    # Clean up
    db.clear_all()
    print("Test completed")
