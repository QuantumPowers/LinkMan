"""
SQLite persistence layer for LinkMan VPN.

Provides async database operations for session, traffic, and device persistence.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import aiosqlite

DB_PATH = "data/linkman.db"


class Database:
    def __init__(self, path: str = DB_PATH):
        self._path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        import os
        os.makedirs(os.path.dirname(self._path) if os.path.dirname(self._path) else ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._create_tables()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _create_tables(self) -> None:
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                client_address TEXT NOT NULL,
                device_id TEXT,
                user_id TEXT,
                start_time REAL NOT NULL,
                end_time REAL,
                bytes_sent INTEGER DEFAULT 0,
                bytes_received INTEGER DEFAULT 0,
                connection_count INTEGER DEFAULT 0,
                metadata TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_client ON sessions(client_address);
            CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time);

            CREATE TABLE IF NOT EXISTS traffic (
                client_id TEXT NOT NULL,
                bytes_sent INTEGER DEFAULT 0,
                bytes_received INTEGER DEFAULT 0,
                recorded_at REAL NOT NULL,
                PRIMARY KEY (client_id, recorded_at)
            );

            CREATE INDEX IF NOT EXISTS idx_traffic_client ON traffic(client_id);
            CREATE INDEX IF NOT EXISTS idx_traffic_time ON traffic(recorded_at);

            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT,
                user_id TEXT,
                created_at REAL NOT NULL,
                last_seen REAL NOT NULL,
                status TEXT DEFAULT 'offline',
                total_bytes INTEGER DEFAULT 0
            );
        """)
        await self._conn.commit()

    async def save_session(self, session_data: dict) -> None:
        await self._conn.execute(
            """INSERT OR REPLACE INTO sessions
               (session_id, client_address, device_id, user_id,
                start_time, end_time, bytes_sent, bytes_received,
                connection_count, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_data.get("session_id"),
                session_data.get("client_address", ""),
                session_data.get("device_id"),
                session_data.get("user_id"),
                session_data.get("start_time", time.time()),
                session_data.get("end_time"),
                session_data.get("bytes_sent", 0),
                session_data.get("bytes_received", 0),
                session_data.get("connection_count", 0),
                str(session_data.get("metadata", {})),
            ),
        )
        await self._conn.commit()

    async def get_sessions(self, client_address: str | None = None) -> list[dict]:
        if client_address:
            cursor = await self._conn.execute(
                "SELECT * FROM sessions WHERE client_address = ? ORDER BY start_time DESC",
                (client_address,),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM sessions WHERE end_time IS NULL ORDER BY start_time DESC"
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def end_session(self, session_id: str) -> None:
        await self._conn.execute(
            "UPDATE sessions SET end_time = ? WHERE session_id = ?",
            (time.time(), session_id),
        )
        await self._conn.commit()

    async def cleanup_old_sessions(self, older_than: float) -> int:
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE end_time IS NOT NULL AND end_time < ?",
            (older_than,),
        )
        row = await cursor.fetchone()
        count = row[0] if row else 0
        await self._conn.execute(
            "DELETE FROM sessions WHERE end_time IS NOT NULL AND end_time < ?",
            (older_than,),
        )
        await self._conn.commit()
        return count

    async def record_traffic(self, client_id: str, sent: int, received: int) -> None:
        recorded_at = int(time.time() / 60) * 60
        await self._conn.execute(
            """INSERT INTO traffic (client_id, bytes_sent, bytes_received, recorded_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(client_id, recorded_at) DO UPDATE SET
               bytes_sent = bytes_sent + ?,
               bytes_received = bytes_received + ?""",
            (client_id, sent, received, recorded_at, sent, received),
        )
        await self._conn.commit()

    async def get_traffic_stats(self, client_id: str | None = None, hours: int = 24) -> list[dict]:
        since = time.time() - hours * 3600
        if client_id:
            cursor = await self._conn.execute(
                """SELECT client_id, SUM(bytes_sent) as sent, SUM(bytes_received) as received
                   FROM traffic WHERE client_id = ? AND recorded_at >= ?
                   GROUP BY client_id""",
                (client_id, since),
            )
        else:
            cursor = await self._conn.execute(
                """SELECT client_id, SUM(bytes_sent) as sent, SUM(bytes_received) as received
                   FROM traffic WHERE recorded_at >= ?
                   GROUP BY client_id ORDER BY sent + received DESC""",
                (since,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def save_device(self, device_data: dict) -> None:
        await self._conn.execute(
            """INSERT OR REPLACE INTO devices
               (device_id, name, user_id, created_at, last_seen, status, total_bytes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                device_data.get("device_id"),
                device_data.get("name", ""),
                device_data.get("user_id"),
                device_data.get("created_at", time.time()),
                device_data.get("last_seen", time.time()),
                device_data.get("status", "offline"),
                device_data.get("total_bytes", 0),
            ),
        )
        await self._conn.commit()

    async def get_devices(self) -> list[dict]:
        cursor = await self._conn.execute("SELECT * FROM devices ORDER BY last_seen DESC")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def delete_device(self, device_id: str) -> bool:
        cursor = await self._conn.execute(
            "DELETE FROM devices WHERE device_id = ?", (device_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0


_db_instance: Optional[Database] = None


async def get_db(path: str = DB_PATH) -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(path)
        await _db_instance.connect()
    return _db_instance


async def close_db() -> None:
    global _db_instance
    if _db_instance:
        await _db_instance.close()
        _db_instance = None
