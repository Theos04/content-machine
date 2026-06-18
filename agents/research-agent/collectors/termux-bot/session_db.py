#!/usr/bin/env python3
"""
Session Database Manager using SQLite
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Any

DB_PATH = os.path.expanduser("~/chrome-sessions.db")

class SessionDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    port INTEGER UNIQUE NOT NULL,
                    profile_dir TEXT NOT NULL,
                    pid INTEGER,
                    status TEXT DEFAULT 'stopped',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP,
                    notes TEXT
                )
            ''')
            
            # Usage history
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    action TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    details TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (id)
                )
            ''')
            
            # Port assignments
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS port_assignments (
                    port INTEGER PRIMARY KEY,
                    session_id INTEGER,
                    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    released_at TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (id)
                )
            ''')
            
            conn.commit()
    
    def create_session(self, name: str, url: str, port: int, profile_dir: str) -> int:
        """Create a new session"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if port is available
            cursor.execute("SELECT port FROM port_assignments WHERE port = ? AND released_at IS NULL", (port,))
            if cursor.fetchone():
                raise ValueError(f"Port {port} is currently in use")
            
            cursor.execute('''
                INSERT INTO sessions (name, url, port, profile_dir, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'stopped', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (name, url, port, profile_dir))
            
            session_id = cursor.lastrowid
            
            # Assign port
            cursor.execute('''
                INSERT INTO port_assignments (port, session_id)
                VALUES (?, ?)
            ''', (port, session_id))
            
            conn.commit()
            return session_id
    
    def update_session(self, session_id: int, **kwargs):
        """Update session fields"""
        valid_fields = ['name', 'url', 'port', 'profile_dir', 'pid', 'status', 'notes']
        updates = []
        values = []
        
        for key, value in kwargs.items():
            if key in valid_fields:
                updates.append(f"{key} = ?")
                values.append(value)
        
        if not updates:
            return
        
        values.append(session_id)
        updates.append("updated_at = CURRENT_TIMESTAMP")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                UPDATE sessions 
                SET {', '.join(updates)}
                WHERE id = ?
            ''', values)
            
            # Log history
            if kwargs.get('status'):
                cursor.execute('''
                    INSERT INTO session_history (session_id, action, details)
                    VALUES (?, ?, ?)
                ''', (session_id, 'status_change', f"Status changed to {kwargs['status']}"))
            
            conn.commit()
    
    def start_session(self, session_id: int, pid: int):
        """Mark session as running"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE sessions 
                SET status = 'running', pid = ?, updated_at = CURRENT_TIMESTAMP, last_used = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (pid, session_id))
            
            cursor.execute('''
                INSERT INTO session_history (session_id, action, details)
                VALUES (?, ?, ?)
            ''', (session_id, 'started', f"PID: {pid}"))
            
            conn.commit()
    
    def stop_session(self, session_id: int):
        """Mark session as stopped"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE sessions 
                SET status = 'stopped', pid = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (session_id,))
            
            cursor.execute('''
                INSERT INTO session_history (session_id, action)
                VALUES (?, ?)
            ''', (session_id, 'stopped'))
            
            conn.commit()
    
    def release_port(self, port: int):
        """Release a port assignment"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE port_assignments 
                SET released_at = CURRENT_TIMESTAMP
                WHERE port = ? AND released_at IS NULL
            ''', (port,))
            conn.commit()
    
    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_session_by_port(self, port: int) -> Optional[Dict[str, Any]]:
        """Get session by port"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions WHERE port = ?', (port,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_session_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get session by name"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions WHERE name = ?', (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def list_sessions(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all sessions, optionally filtered by status"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if status:
                cursor.execute('SELECT * FROM sessions WHERE status = ? ORDER BY name', (status,))
            else:
                cursor.execute('SELECT * FROM sessions ORDER BY name')
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_available_ports(self) -> List[int]:
        """Get list of available ports"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT port FROM port_assignments 
                WHERE released_at IS NULL
            ''')
            used_ports = [row[0] for row in cursor.fetchall()]
            
            # Return ports from 9222-9299 that aren't used
            all_ports = set(range(9222, 9300))
            available = all_ports - set(used_ports)
            return sorted(available)
    
    def delete_session(self, session_id: int):
        """Delete a session and release its port"""
        session = self.get_session(session_id)
        if not session:
            return
        
        # Release port
        self.release_port(session['port'])
        
        # Delete session
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
            conn.commit()
    
    def get_history(self, session_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get session history"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if session_id:
                cursor.execute('''
                    SELECT * FROM session_history 
                    WHERE session_id = ? 
                    ORDER BY timestamp DESC LIMIT ?
                ''', (session_id, limit))
            else:
                cursor.execute('''
                    SELECT * FROM session_history 
                    ORDER BY timestamp DESC LIMIT ?
                ''', (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
