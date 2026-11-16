"""联系人仓储层：数据库读写、检索、星标与批量导入。

对外返回的「联系人字典」结构（前后端共用同一套字段）::

    {
      "id": 1,
      "name": "林晓",
      "group": "工作",
      "company": "福州大学",
      "department": "计算机学院",
      "title": "讲师",
      "note": "周三下午有空",
      "starred": true,
      "methods": [
        {"id": 3, "type": "phone", "label": "工作", "value": "13800000001", "primary": true}
      ],
      "created_at": "2026-11-16 10:00:00",
      "updated_at": "2026-11-16 10:00:00"
    }
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Iterable

from .db import Database
from .validation import ValidationError, normalize_contact

CONTACT_COLUMNS = """
    c.id, c.name, c.group_name, c.company, c.department, c.title,
    c.note, c.starred, c.created_at, c.updated_at
"""

SORTS = {
    "default": "c.starred DESC, c.name COLLATE NOCASE ASC, c.id ASC",
    "name": "c.name COLLATE NOCASE ASC, c.id ASC",
    "updated": "c.updated_at DESC, c.id DESC",
    "created": "c.created_at DESC, c.id DESC",
}


class NotFoundError(Exception):
    """联系人不存在。"""


def now_text() -> str:
    """本地时间字符串，便于直接展示与导出（本项目面向单机/单区域部署）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _escape_like(keyword: str) -> str:
    return keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def pinyin_key(text: str) -> bytes:
    """按 GBK（GB2312 一级汉字按拼音排序）编码得到近似拼音序的排序键。

    中文通讯录通常按拼音排列联系人，而 SQLite 的默认排序基于 Unicode 码位，
    与拼音顺序无关。借助 GB2312 的编码规律可以在不引入拼音词库的情况下
    得到符合中文用户习惯的顺序。
    """
    try:
        return text.encode("gbk")
    except UnicodeEncodeError:
        return text.encode("utf-8")


def contact_key(name: str, methods: Iterable[dict[str, Any]]) -> str:
    """导入去重键：姓名 + 全部联系方式（忽略大小写与格式差异）。"""
    values = sorted(
        f"{m['type']}:{m['value'].strip().lower()}" for m in methods if m.get("value")
    )
    return f"{name.strip().lower()}|" + "|".join(values)


class ContactStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ 查询
    def list_contacts(
        self,
        *,
        q: str | None = None,
        starred: bool | None = None,
        group: str | None = None,
        sort: str = "default",
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if starred is not None:
            where.append("c.starred = ?")
            params.append(1 if starred else 0)
        if group:
            where.append("c.group_name = ?")
            params.append(group)
        if q:
            like = f"%{_escape_like(q.strip())}%"
            where.append(
                "(c.name LIKE ? ESCAPE '\\' OR c.company LIKE ? ESCAPE '\\'"
                " OR c.department LIKE ? ESCAPE '\\' OR c.title LIKE ? ESCAPE '\\'"
                " OR c.note LIKE ? ESCAPE '\\' OR c.group_name LIKE ? ESCAPE '\\'"
                " OR EXISTS (SELECT 1 FROM contact_methods m"
                "            WHERE m.contact_id = c.id AND m.value LIKE ? ESCAPE '\\'))"
            )
            params.extend([like] * 7)

        sql = f"SELECT {CONTACT_COLUMNS} FROM contacts c"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY " + SORTS.get(sort, SORTS["default"])

        with self.db.cursor() as conn:
            rows = conn.execute(sql, params).fetchall()
            methods = self._methods_for(conn, [row["id"] for row in rows])
        items = [self._serialize(row, methods.get(row["id"], [])) for row in rows]
        if sort == "default":
            items.sort(key=lambda item: (0 if item["starred"] else 1, pinyin_key(item["name"]), item["id"]))
        elif sort == "name":
            items.sort(key=lambda item: (pinyin_key(item["name"]), item["id"]))
        return items

    def get(self, contact_id: int) -> dict[str, Any]:
        with self.db.cursor() as conn:
            row = conn.execute(
                f"SELECT {CONTACT_COLUMNS} FROM contacts c WHERE c.id = ?", (contact_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"联系人 {contact_id} 不存在")
            methods = self._methods_for(conn, [contact_id])
        return self._serialize(row, methods.get(contact_id, []))

    def exists(self, contact_id: int) -> bool:
        with self.db.cursor() as conn:
            row = conn.execute("SELECT 1 FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        return row is not None

    def list_groups(self) -> list[dict[str, Any]]:
        with self.db.cursor() as conn:
            rows = conn.execute(
                "SELECT group_name AS name, COUNT(*) AS count FROM contacts"
                " WHERE group_name <> '' GROUP BY group_name"
                " ORDER BY count DESC, name COLLATE NOCASE ASC"
            ).fetchall()
        return [{"name": row["name"], "count": row["count"]} for row in rows]

    def stats(self) -> dict[str, int]:
        with self.db.cursor() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM contacts").fetchone()["n"]
            starred = conn.execute(
                "SELECT COUNT(*) AS n FROM contacts WHERE starred = 1"
            ).fetchone()["n"]
            methods = conn.execute("SELECT COUNT(*) AS n FROM contact_methods").fetchone()["n"]
            groups = conn.execute(
                "SELECT COUNT(DISTINCT group_name) AS n FROM contacts WHERE group_name <> ''"
            ).fetchone()["n"]
        return {"total": total, "starred": starred, "methods": methods, "groups": groups}

    # ------------------------------------------------------------------ 写入
    def create(self, payload: Any) -> dict[str, Any]:
        clean = normalize_contact(payload)
        with self.db.cursor() as conn:
            contact_id = self._insert(conn, clean)
        return self.get(contact_id)

    def update(self, contact_id: int, payload: Any) -> dict[str, Any]:
        clean = normalize_contact(payload)
        with self.db.cursor() as conn:
            self._update(conn, contact_id, clean)
        return self.get(contact_id)

    def set_starred(self, contact_id: int, starred: bool) -> dict[str, Any]:
        with self.db.cursor() as conn:
            cursor = conn.execute(
                "UPDATE contacts SET starred = ?, updated_at = ? WHERE id = ?",
                (1 if starred else 0, now_text(), contact_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError(f"联系人 {contact_id} 不存在")
        return self.get(contact_id)

    def delete(self, contact_id: int) -> None:
        with self.db.cursor() as conn:
            cursor = conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            if cursor.rowcount == 0:
                raise NotFoundError(f"联系人 {contact_id} 不存在")

    # ------------------------------------------------------------- Excel 导入
    def bulk_import(self, records: list[dict[str, Any]], *, mode: str = "merge") -> dict[str, Any]:
        """把 Excel 解析后的记录写入数据库。

        mode = "merge"  同名且联系方式完全相同的记录视为同一人，做字段补全与去重合并；
        mode = "insert" 无条件新增（由数据库自增分配新 id）。
        """
        imported = updated = 0
        with self.db.cursor() as conn:
            index = self._import_index(conn)
            for record in records:
                if mode == "merge":
                    key = contact_key(record["name"], record["methods"])
                    existing_id = index.get(key)
                    if existing_id:
                        self._merge(conn, existing_id, record)
                        updated += 1
                        continue
                new_id = self._insert(conn, record)
                index[contact_key(record["name"], record["methods"])] = new_id
                imported += 1
        return {"imported": imported, "updated": updated}

    # ---------------------------------------------------------------- 内部实现
    def _import_index(self, conn: sqlite3.Connection) -> dict[str, int]:
        rows = conn.execute(f"SELECT {CONTACT_COLUMNS} FROM contacts c").fetchall()
        methods = self._methods_for(conn, [row["id"] for row in rows])
        index: dict[str, int] = {}
        for row in rows:
            index[contact_key(row["name"], methods.get(row["id"], []))] = row["id"]
        return index

    def _merge(self, conn: sqlite3.Connection, contact_id: int, record: dict[str, Any]) -> None:
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        current = self._serialize(row, self._methods_for(conn, [contact_id]).get(contact_id, []))
        merged = {
            "name": record["name"],
            "group": record["group"] or current["group"],
            "company": record["company"] or current["company"],
            "department": record["department"] or current["department"],
            "title": record["title"] or current["title"],
            "note": record["note"] or current["note"],
            "starred": record["starred"] or current["starred"],
            "methods": self._union_methods(current["methods"], record["methods"]),
        }
        self._update(conn, contact_id, merged)

    @staticmethod
    def _union_methods(
        existing: list[dict[str, Any]], incoming: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for method in list(existing) + list(incoming):
            key = (method["type"], method["value"].strip().lower())
            if key in seen:
                continue
            seen.add(key)
            merged.append(
                {
                    "type": method["type"],
                    "label": method.get("label", ""),
                    "value": method["value"],
                    "primary": bool(method.get("primary")),
                }
            )
        if merged and not any(m["primary"] for m in merged):
            merged[0]["primary"] = True
        primary_seen = False
        for method in merged:
            if method["primary"] and primary_seen:
                method["primary"] = False
            primary_seen = primary_seen or method["primary"]
        return merged[:20]

    def _insert(self, conn: sqlite3.Connection, clean: dict[str, Any]) -> int:
        stamp = now_text()
        cursor = conn.execute(
            "INSERT INTO contacts (name, group_name, company, department, title, note,"
            " starred, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                clean["name"],
                clean["group"],
                clean["company"],
                clean["department"],
                clean["title"],
                clean["note"],
                1 if clean["starred"] else 0,
                stamp,
                stamp,
            ),
        )
        contact_id = int(cursor.lastrowid)
        self._replace_methods(conn, contact_id, clean["methods"])
        return contact_id

    def _update(self, conn: sqlite3.Connection, contact_id: int, clean: dict[str, Any]) -> None:
        cursor = conn.execute(
            "UPDATE contacts SET name = ?, group_name = ?, company = ?, department = ?,"
            " title = ?, note = ?, starred = ?, updated_at = ? WHERE id = ?",
            (
                clean["name"],
                clean["group"],
                clean["company"],
                clean["department"],
                clean["title"],
                clean["note"],
                1 if clean["starred"] else 0,
                now_text(),
                contact_id,
            ),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(f"联系人 {contact_id} 不存在")
        self._replace_methods(conn, contact_id, clean["methods"])

    def _replace_methods(
        self, conn: sqlite3.Connection, contact_id: int, methods: list[dict[str, Any]]
    ) -> None:
        conn.execute("DELETE FROM contact_methods WHERE contact_id = ?", (contact_id,))
        conn.executemany(
            "INSERT INTO contact_methods (contact_id, type, label, value, is_primary, sort_order)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    contact_id,
                    method["type"],
                    method.get("label", ""),
                    method["value"],
                    1 if method.get("primary") else 0,
                    index,
                )
                for index, method in enumerate(methods)
            ],
        )

    def _methods_for(
        self, conn: sqlite3.Connection, contact_ids: list[int]
    ) -> dict[int, list[dict[str, Any]]]:
        if not contact_ids:
            return {}
        placeholders = ",".join("?" * len(contact_ids))
        rows = conn.execute(
            "SELECT * FROM contact_methods WHERE contact_id IN ("
            f"{placeholders}) ORDER BY sort_order ASC, id ASC",
            contact_ids,
        ).fetchall()
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["contact_id"], []).append(
                {
                    "id": row["id"],
                    "type": row["type"],
                    "label": row["label"],
                    "value": row["value"],
                    "primary": bool(row["is_primary"]),
                }
            )
        return grouped

    @staticmethod
    def _serialize(row: sqlite3.Row, methods: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "group": row["group_name"],
            "company": row["company"],
            "department": row["department"],
            "title": row["title"],
            "note": row["note"],
            "starred": bool(row["starred"]),
            "methods": methods,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


__all__ = ["ContactStore", "NotFoundError", "ValidationError", "contact_key", "now_text"]
