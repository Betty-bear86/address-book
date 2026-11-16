"""SQLite 连接管理与建表脚本。

设计说明：
- 每个请求/操作使用独立连接（sqlite3 连接不是线程安全的），由 ``Database.cursor``
  这个上下文管理器负责 commit / rollback / close；
- 打开 ``foreign_keys``，删除联系人时由外键级联删除其联系方式；
- 打开 WAL，提升并发读性能，避免开发服务器的多线程读写冲突。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    group_name  TEXT    NOT NULL DEFAULT '',
    company     TEXT    NOT NULL DEFAULT '',
    department  TEXT    NOT NULL DEFAULT '',
    title       TEXT    NOT NULL DEFAULT '',
    note        TEXT    NOT NULL DEFAULT '',
    starred     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS contact_methods (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    type       TEXT    NOT NULL,
    label      TEXT    NOT NULL DEFAULT '',
    value      TEXT    NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_methods_contact ON contact_methods(contact_id);
CREATE INDEX IF NOT EXISTS idx_contacts_starred ON contacts(starred DESC, name);
CREATE INDEX IF NOT EXISTS idx_contacts_group ON contacts(group_name);
"""


class Database:
    """轻量 SQLite 封装，只为本项目提供连接与建表能力。"""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """创建数据库文件（如不存在）与全部表结构，可重复执行。"""
        Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        with self.cursor() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)

    def is_empty(self) -> bool:
        with self.cursor() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM contacts").fetchone()
        return int(row["n"]) == 0
