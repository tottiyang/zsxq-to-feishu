"""persistence.py — SQLite 断点续传"""
import sqlite3
from datetime import datetime

class SyncState:
    def __init__(self, db_path: str = "zsxq_sync_state.db"):
        self.db = sqlite3.connect(db_path)
        self.db.execute("CREATE TABLE IF NOT EXISTS synced_topics (topic_id TEXT PRIMARY KEY, synced_at TEXT, phase TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS sync_checkpoint (phase TEXT PRIMARY KEY, last_end_time TEXT, last_topic_id TEXT, total_synced INTEGER DEFAULT 0, updated_at TEXT)")
        self.db.commit()

    def is_synced(self, topic_id: str) -> bool:
        cur = self.db.execute("SELECT 1 FROM synced_topics WHERE topic_id=?", (topic_id,))
        return cur.fetchone() is not None

    def mark_synced(self, topic_id: str, phase: str):
        self.db.execute("INSERT OR IGNORE INTO synced_topics (topic_id, synced_at, phase) VALUES (?, ?, ?)",
            (topic_id, datetime.now().isoformat(), phase))
        self.db.commit()

    def save_checkpoint(self, phase: str, last_end_time: str, last_topic_id: str, total_synced: int):
        self.db.execute("INSERT OR REPLACE INTO sync_checkpoint (phase, last_end_time, last_topic_id, total_synced, updated_at) VALUES (?, ?, ?, ?, ?)",
            (phase, last_end_time, last_topic_id, total_synced, datetime.now().isoformat()))
        self.db.commit()
        print(f"  ✓ 断点已保存: phase={phase}, total={total_synced}, last_time={last_end_time[:19]}")

    def load_checkpoint(self, phase: str) -> dict | None:
        cur = self.db.execute("SELECT last_end_time, last_topic_id, total_synced FROM sync_checkpoint WHERE phase=?", (phase,))
        row = cur.fetchone()
        if row:
            return {"last_end_time": row[0], "last_topic_id": row[1], "total_synced": row[2]}
        return None

    def get_all_synced_ids(self) -> set:
        cur = self.db.execute("SELECT topic_id FROM synced_topics")
        return set(row[0] for row in cur.fetchall())
