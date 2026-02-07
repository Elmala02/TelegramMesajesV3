import sqlite3
import os
from datetime import datetime
import pytz

class TradingDB:
    def __init__(self, db_name="trading_signals.db"):
        self.db_name = db_name
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_name)

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Table for signals
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT,
                    msg_id INTEGER,
                    asset TEXT,
                    direction TEXT,
                    entry_min REAL,
                    entry_max REAL,
                    tp1 REAL,
                    tp2 REAL,
                    tp3 REAL,
                    tp4 REAL,
                    tp5 REAL,
                    sl REAL,
                    status TEXT DEFAULT 'ACTIVE', -- ACTIVE, IN_PROGRESS, TP_HIT, SL_HIT, EXPIRED
                    pips_result REAL DEFAULT 0,
                    raw_text TEXT,
                    formatted_text TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_update DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Table for performance logs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE UNIQUE,
                    total_signals INTEGER,
                    win_rate REAL,
                    total_pips REAL
                )
            ''')
            conn.commit()

    def save_signal(self, data):
        """
        data: dict with keys matching column names
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        sql = f'INSERT INTO signals ({columns}) VALUES ({placeholders})'
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, list(data.values()))
            conn.commit()
            return cursor.lastrowid

    def update_signal_status(self, signal_id, status, pips=0):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE signals 
                SET status = ?, pips_result = ?, last_update = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (status, pips, signal_id))
            conn.commit()

    def get_active_signals(self):
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals WHERE status IN ('ACTIVE', 'IN_PROGRESS')")
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), SUM(pips_result) FROM signals WHERE status IN ('TP_HIT', 'SL_HIT')")
            total, pips = cursor.fetchone()
            
            cursor.execute("SELECT COUNT(*) FROM signals WHERE status = 'TP_HIT'")
            wins = cursor.fetchone()[0]
            
            win_rate = (wins / total * 100) if total and total > 0 else 0
            return {
                "total": total or 0,
                "wins": wins or 0,
                "win_rate": round(win_rate, 2),
                "total_pips": round(pips or 0, 2)
            }
