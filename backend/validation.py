"""联系人数据的校验与归一化。

所有写接口（新建、编辑、Excel 导入）都会先经过 ``normalize_contact``，
保证入库数据字段完整、类型正确、联系方式合法，并且「只有一个主联系方式」。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# 联系方式类型（顺序即界面与 Excel 列的展示顺序）
METHOD_TYPES: tuple[str, ...] = ("phone", "email", "wechat", "qq", "address", "other")
METHOD_LABELS: dict[str, str] = {
    "phone": "电话",
    "email": "邮箱",
    "wechat": "微信",
    "qq": "QQ",
    "address": "地址",
    "other": "其他",
}
METHOD_LABEL_CHOICES: tuple[str, ...] = ("工作", "个人", "家庭", "学校", "其他")

MAX_NAME = 40
MAX_SHORT_TEXT = 60
MAX_NOTE = 500
MAX_METHOD_VALUE = 120
MAX_METHODS = 20
MAX_GROUP = 20

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_ALLOWED_RE = re.compile(r"^[0-9+\-() \u00a0]+$")
TRUTHY = {"1", "true", "yes", "y", "是", "星标", "⭐", "on"}


class ValidationError(ValueError):
    """字段级校验异常，携带出错的字段名便于前端定位。"""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field

    def to_dict(self) -> dict[str, Any]:
        return {"message": self.message, "field": self.field}


def _text(value: Any, *, field: str, limit: int, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        if isinstance(value, (int, float)):
            value = str(value)
        else:
            raise ValidationError(f"{field}格式不正确", field)
    value = re.sub(r"[\r\n\t]+", " ", value).strip()
    if required and not value:
        raise ValidationError(f"{field}不能为空", field)
    if len(value) > limit:
        raise ValidationError(f"{field}不能超过 {limit} 个字符", field)
    return value


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY
    return False


def _normalize_phone(value: str) -> str:
    compact = value.replace(" ", "").replace("-", "")
    if not PHONE_ALLOWED_RE.match(value):
        raise ValidationError("电话号码包含非法字符", "methods")
    if compact.startswith("+"):
        digits = re.sub(r"\D", "", compact[1:])
    else:
        digits = re.sub(r"\D", "", compact)
    if not 5 <= len(digits) <= 20:
        raise ValidationError("电话号码位数不正确（应为 5~20 位数字）", "methods")
    return value


def _normalize_method(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValidationError("联系方式格式不正确", "methods")
    mtype = str(item.get("type") or "").strip().lower()
    if mtype not in METHOD_TYPES:
        raise ValidationError(f"不支持的联系方式类型：{mtype or '(空)'}", "methods")
    value = _text(item.get("value"), field="联系方式内容", limit=MAX_METHOD_VALUE, required=True)
    label = _text(item.get("label"), field="联系方式备注", limit=MAX_GROUP)
    if label and label not in METHOD_LABEL_CHOICES:
        label = label[:MAX_GROUP]

    if mtype == "phone":
        value = _normalize_phone(value)
    elif mtype == "email":
        if not EMAIL_RE.match(value):
            raise ValidationError(f"邮箱格式不正确：{value}", "methods")
    elif mtype == "qq":
        if not value.isdigit():
            raise ValidationError(f"QQ 号应为纯数字：{value}", "methods")

    return {"type": mtype, "label": label, "value": value, "primary": to_bool(item.get("primary"))}


def normalize_methods(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes, dict)):
        raise ValidationError("联系方式应为数组", "methods")
    methods: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        method = _normalize_method(item)
        key = (method["type"], method["value"].lower())
        if key in seen:  # 同一类型下完全相同的值只保留一条
            continue
        seen.add(key)
        methods.append(method)
    if len(methods) > MAX_METHODS:
        raise ValidationError(f"一个联系人最多 {MAX_METHODS} 条联系方式", "methods")
    # 保证有且仅有一个主联系方式（默认第一条）
    primary_index = next((i for i, m in enumerate(methods) if m["primary"]), 0 if methods else -1)
    for i, method in enumerate(methods):
        method["primary"] = i == primary_index
    return methods


def normalize_contact(payload: Any) -> dict[str, Any]:
    """把任意来源的数据整理成可直接入库的字典。"""
    if not isinstance(payload, dict):
        raise ValidationError("请求体应为 JSON 对象")
    return {
        "name": _text(payload.get("name"), field="姓名", limit=MAX_NAME, required=True),
        "group": _text(payload.get("group"), field="分组", limit=MAX_GROUP),
        "company": _text(payload.get("company"), field="公司", limit=MAX_SHORT_TEXT),
        "department": _text(payload.get("department"), field="部门", limit=MAX_SHORT_TEXT),
        "title": _text(payload.get("title"), field="职位", limit=MAX_SHORT_TEXT),
        "note": _text(payload.get("note"), field="备注", limit=MAX_NOTE),
        "starred": to_bool(payload.get("starred")),
        "methods": normalize_methods(payload.get("methods")),
    }
