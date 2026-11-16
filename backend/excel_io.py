"""Excel 导入 / 导出。

导出规则（与作业要求一致）：
- 一个联系人占一行；
- 每一类信息占一列（姓名、分组、公司、部门、职位……）；
- 同一类型的多个联系方式依次占用「电话1、电话2、电话3……」等列，
  保证「导出 → 修改 → 再导入」可以无损往返；
- 导出文件带表头样式、冻结窗格、筛选器、列宽自适应和「填写说明」工作表。

导入规则：
- 只要求表头包含「姓名」列，其余列按别名识别（如 手机/电话、邮件/邮箱、微信、QQ、地址、备注、星标）；
- 支持单元格内用「；」「、」「,」分隔多个同类型联系方式；
- 逐行校验，错误行会被跳过并在报告中给出行号与原因。
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from io import BytesIO
from typing import Any, BinaryIO, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .validation import (
    METHOD_LABELS,
    METHOD_TYPES,
    ValidationError,
    normalize_contact,
    to_bool,
)

SHEET_TITLE = "通讯录"
GUIDE_TITLE = "填写说明"

FRONT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("name", "姓名"),
    ("group", "分组"),
    ("company", "公司"),
    ("department", "部门"),
    ("title", "职位"),
)
TAIL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("note", "备注"),
    ("starred", "星标"),
    ("created_at", "创建时间"),
)

HEAD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("姓名", "名字", "联系人", "联系人姓名", "名称", "name", "contact", "contactname"),
    "group": ("分组", "分类", "标签", "组别", "group", "category", "tag"),
    "company": ("公司", "单位", "工作单位", "公司名称", "company"),
    "department": ("部门", "所属部门", "department", "dept"),
    "title": ("职位", "职务", "岗位", "title", "position"),
    "note": ("备注", "说明", "描述", "note", "remark", "comment"),
    "starred": ("星标", "收藏", "星标联系人", "是否星标", "starred", "star"),
}

TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "phone": ("电话", "手机", "手机号", "手机号码", "电话号码", "联系电话", "联系方式", "phone", "mobile", "tel"),
    "email": ("邮箱", "电子邮箱", "邮件", "邮件地址", "email", "mail", "e-mail"),
    "wechat": ("微信", "微信号", "wechat", "weixin"),
    "qq": ("qq", "qq号", "qq号码"),
    "address": ("地址", "住址", "通讯地址", "联系地址", "address", "addr"),
    "other": ("其他", "其它", "其他联系方式", "other", "misc"),
}

HEADER_FILL = PatternFill("solid", fgColor="4F6EF7")
HEADER_FONT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
BODY_FONT = Font(name="微软雅黑", size=10, color="1F2937")
STRIPE_FILL = PatternFill("solid", fgColor="F4F7FF")
STAR_FONT = Font(name="微软雅黑", size=10, bold=True, color="B45309")
STAR_OFF_FONT = Font(name="微软雅黑", size=10, color="94A3B8")
THIN_SIDE = Side(style="thin", color="DCE3F0")
CELL_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")
WRAP = Alignment(horizontal="left", vertical="center", wrap_text=True)

GUIDE_LINES: tuple[str, ...] = (
    "通讯录导入说明",
    "1. 请勿修改第一行表头，导入程序依靠表头识别每一列的含义。",
    "2. 每个联系人占一行；姓名（第一列）必填，其余列可以留空。",
    "3. 同一类型的多个联系方式，请填写在「电话1、电话2、电话3……」等不同列中。",
    "4. 一个单元格内也可以写多个号码，用「；」「、」或「,」分隔，导入时会自动拆分。",
    "5. 「星标」列填写「是」或「否」，用于标记常用联系人。",
    "6. 「创建时间」列仅供导出时查看，导入时会被忽略。",
    "7. 导入时若姓名与联系方式都与已有联系人一致，将按「合并」或「新增」策略处理。",
    "8. 支持的表头别名：姓名/名字、电话/手机/手机号、邮箱/邮件、微信、QQ、地址/住址、备注、星标。",
)


class WorkbookError(ValueError):
    """Excel 文件无法解析。"""


# ---------------------------------------------------------------- 导出辅助函数
def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _column_plan(contacts: list[dict[str, Any]]) -> tuple[dict[str, int], list[str]]:
    """按实际数据计算每类联系方式需要几列，并生成表头。"""
    slots: dict[str, int] = {}
    for mtype in METHOD_TYPES:
        longest = 0
        for contact in contacts:
            longest = max(longest, sum(1 for m in contact["methods"] if m["type"] == mtype))
        slots[mtype] = max(1, longest)

    headers = [label for _, label in FRONT_COLUMNS]
    for mtype in METHOD_TYPES:
        label = METHOD_LABELS[mtype]
        headers += [label] if slots[mtype] == 1 else [f"{label}{i}" for i in range(1, slots[mtype] + 1)]
    headers += [label for _, label in TAIL_COLUMNS]
    return slots, headers


def _row_values(contact: dict[str, Any], slots: dict[str, int]) -> list[str]:
    values = [str(contact.get(key) or "") for key, _ in FRONT_COLUMNS]
    for mtype in METHOD_TYPES:
        picked = [m["value"] for m in contact["methods"] if m["type"] == mtype]
        picked += [""] * (slots[mtype] - len(picked))
        values += picked[: slots[mtype]]
    values.append(str(contact.get("note") or ""))
    values.append("是" if contact.get("starred") else "否")
    values.append(str(contact.get("created_at") or ""))
    return values


def _style_sheet(ws, headers: list[str], rows: list[list[str]], *, star_col: int, wrap_cols: set[int]) -> None:
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 26

    for index, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=index, value=title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = CELL_BORDER

    for row_index, values in enumerate(rows, start=2):
        striped = row_index % 2 == 0
        for col_index, value in enumerate(values, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            if col_index == star_col:
                cell.font = STAR_FONT if value == "是" else STAR_OFF_FONT
            else:
                cell.font = BODY_FONT
            cell.alignment = WRAP if col_index in wrap_cols else (CENTER if col_index == star_col else LEFT)
            cell.border = CELL_BORDER
            if striped:
                cell.fill = STRIPE_FILL

    for col_index, title in enumerate(headers, start=1):
        width = max([_display_width(title)] + [_display_width(str(r[col_index - 1])) for r in rows] or [10])
        ws.column_dimensions[get_column_letter(col_index)].width = min(max(10, width + 4), 42)

    if headers:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(1, len(rows) + 1)}"

    validation = DataValidation(type="list", formula1='"是,否"', allow_blank=True, showDropDown=False)
    validation.error = "请填写「是」或「否」"
    validation.errorTitle = "星标取值不合法"
    ws.add_data_validation(validation)
    column = get_column_letter(star_col)
    validation.add(f"{column}2:{column}{max(2, len(rows) + 1)}")


def _add_guide_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet(GUIDE_TITLE)
    ws.column_dimensions["A"].width = 110
    for index, line in enumerate(GUIDE_LINES, start=1):
        cell = ws.cell(row=index, column=1, value=line)
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        cell.font = Font(name="微软雅黑", size=12 if index == 1 else 10, bold=index == 1)
        ws.row_dimensions[index].height = 24 if index == 1 else 20


def build_workbook(contacts: list[dict[str, Any]]) -> bytes:
    """把联系人列表导出为 xlsx 字节流。"""
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_TITLE
    slots, headers = _column_plan(contacts)
    rows = [_row_values(contact, slots) for contact in contacts]
    _style_sheet(
        ws,
        headers,
        rows,
        star_col=headers.index("星标") + 1,
        wrap_cols={headers.index("备注") + 1} | {i + 1 for i, h in enumerate(headers) if h.startswith("地址")},
    )
    _add_guide_sheet(wb)
    wb.properties.creator = "Address Book"
    wb.properties.title = "通讯录导出"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_template() -> bytes:
    """生成空白导入模板（含两行示例）。"""
    samples = [
        {
            "name": "张三",
            "group": "工作",
            "company": "福州大学",
            "department": "计算机与大数据学院",
            "title": "辅导员",
            "note": "示例行，导入前可删除",
            "starred": True,
            "created_at": "",
            "methods": [
                {"type": "phone", "label": "工作", "value": "13800001111", "primary": True},
                {"type": "phone", "label": "个人", "value": "0591-22866000", "primary": False},
                {"type": "email", "label": "工作", "value": "zhangsan@fzu.edu.cn", "primary": False},
                {"type": "wechat", "label": "", "value": "zhangsan_fzu", "primary": False},
            ],
        },
        {
            "name": "李四",
            "group": "家人",
            "company": "福建师范大学",
            "department": "",
            "title": "",
            "note": "",
            "starred": False,
            "created_at": "",
            "methods": [
                {"type": "phone", "label": "个人", "value": "13900002222", "primary": True},
                {"type": "address", "label": "家庭", "value": "福建省福州市仓山区上三路 8 号", "primary": False},
            ],
        },
    ]
    return build_workbook(samples)


# ---------------------------------------------------------------- 导入解析函数
def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value).strip()


def _canonical(value: Any) -> str:
    text = _cell_text(value).lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[（(].*?[)）]", "", text)
    return re.sub(r"\d+$", "", text)


def _match_header(value: Any) -> tuple[str, str] | None:
    key = _canonical(value)
    if not key:
        return None
    for field, aliases in HEAD_ALIASES.items():
        if key in aliases:
            return ("field", field)
    for mtype, aliases in TYPE_ALIASES.items():
        if key in aliases:
            return ("method", mtype)
    return None


def _build_mapping(header_row: Iterable[Any]) -> tuple[dict[int, tuple[str, str]], dict[str, list[int]]]:
    mapping: dict[int, tuple[str, str]] = {}
    method_cols: dict[str, list[int]] = {mtype: [] for mtype in METHOD_TYPES}
    for index, value in enumerate(header_row):
        matched = _match_header(value)
        if not matched:
            continue
        mapping[index] = matched
        if matched[0] == "method":
            method_cols[matched[1]].append(index)
    return mapping, method_cols


def _split_values(text: str, *, mtype: str) -> list[str]:
    if not text:
        return []
    if mtype == "address":
        return [part.strip() for part in text.splitlines() if part.strip()]
    parts = re.split(r"[；;、,，\n]+", text)
    return [part.strip() for part in parts if part.strip()]


def parse_workbook(stream: BinaryIO) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """解析 Excel，返回 (合法记录, 错误列表)。记录中带 ``row`` 行号。"""
    try:
        workbook = load_workbook(stream, read_only=True, data_only=True)
    except Exception as exc:  # 非 xlsx / 文件损坏
        raise WorkbookError("无法读取该文件，请上传 .xlsx 格式的 Excel 文件") from exc

    sheet = workbook[SHEET_TITLE] if SHEET_TITLE in workbook.sheetnames else workbook.active

    header_row_index = 0
    header_row: tuple[Any, ...] | None = None
    mapping: dict[int, tuple[str, str]] = {}
    method_cols: dict[str, list[int]] = {mtype: [] for mtype in METHOD_TYPES}

    for index, row in enumerate(sheet.iter_rows(max_row=10, values_only=True), start=1):
        if row is None or all(_cell_text(cell) == "" for cell in row):
            continue
        candidate, candidate_cols = _build_mapping(row)
        if any(kind == "field" and key == "name" for kind, key in candidate.values()):
            header_row_index, header_row, mapping, method_cols = index, row, candidate, candidate_cols
            break

    if header_row is None:
        raise WorkbookError("未找到表头：第一行需要包含「姓名」列，请使用模板填写")

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for row_number, row in enumerate(
        sheet.iter_rows(min_row=header_row_index + 1, values_only=True), start=header_row_index + 1
    ):
        cells = list(row)
        if all(_cell_text(cell) == "" for cell in cells):
            continue

        def value_of(field: str) -> str:
            for index, (kind, key) in mapping.items():
                if kind == "field" and key == field and index < len(cells):
                    return _cell_text(cells[index])
            return ""

        payload: dict[str, Any] = {
            "name": value_of("name"),
            "group": value_of("group"),
            "company": value_of("company"),
            "department": value_of("department"),
            "title": value_of("title"),
            "note": value_of("note"),
            "starred": to_bool(value_of("starred")),
            "methods": [],
        }
        for mtype in METHOD_TYPES:
            for index in method_cols[mtype]:
                if index >= len(cells):
                    continue
                for part in _split_values(_cell_text(cells[index]), mtype=mtype):
                    payload["methods"].append({"type": mtype, "label": "", "value": part, "primary": False})

        try:
            clean = normalize_contact(payload)
        except ValidationError as exc:
            errors.append({"row": row_number, "message": exc.message})
            continue
        clean["row"] = row_number
        records.append(clean)

    return records, errors
