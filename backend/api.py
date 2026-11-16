"""REST API 蓝图。

所有接口统一返回 JSON；出错时返回 ``{"error": {"message": "...", "field": "..."}}``。
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from flask import Blueprint, current_app, jsonify, request, send_file

from .contacts import ContactStore, NotFoundError
from .excel_io import WorkbookError, build_template, build_workbook, parse_workbook
from .validation import (
    METHOD_LABEL_CHOICES,
    METHOD_LABELS,
    METHOD_TYPES,
    ValidationError,
)

api = Blueprint("api", __name__, url_prefix="/api")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def store() -> ContactStore:
    return current_app.extensions["store"]


def _bool_arg(name: str) -> bool | None:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on", "是"}


def _json_body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("请求体必须是合法的 JSON 对象", 400)
    return payload


# --------------------------------------------------------------------- 元信息
@api.get("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


@api.get("/meta")
def meta():
    return jsonify(
        {
            "types": [{"key": key, "label": METHOD_LABELS[key]} for key in METHOD_TYPES],
            "labels": list(METHOD_LABEL_CHOICES),
            "groups": store().list_groups(),
            "stats": store().stats(),
        }
    )


# --------------------------------------------------------------------- 联系人
@api.get("/contacts")
def list_contacts():
    contacts = store().list_contacts(
        q=request.args.get("q") or None,
        starred=_bool_arg("starred"),
        group=request.args.get("group") or None,
        sort=request.args.get("sort", "default"),
    )
    return jsonify({"items": contacts, "total": len(contacts)})


@api.get("/contacts/<int:contact_id>")
def get_contact(contact_id: int):
    return jsonify(store().get(contact_id))


@api.post("/contacts")
def create_contact():
    contact = store().create(_json_body())
    return jsonify(contact), 201


@api.put("/contacts/<int:contact_id>")
def update_contact(contact_id: int):
    return jsonify(store().update(contact_id, _json_body()))


@api.patch("/contacts/<int:contact_id>/star")
def star_contact(contact_id: int):
    payload = request.get_json(silent=True) or {}
    if "starred" in payload:
        from .validation import to_bool

        value = to_bool(payload["starred"])
    else:  # 未显式指定则取反
        value = not store().get(contact_id)["starred"]
    return jsonify(store().set_starred(contact_id, value))


@api.delete("/contacts/<int:contact_id>")
def delete_contact(contact_id: int):
    store().delete(contact_id)
    return jsonify({"deleted": contact_id})


# --------------------------------------------------------------------- 导入导出
@api.get("/export")
def export_contacts():
    contacts = store().list_contacts(
        q=request.args.get("q") or None,
        starred=_bool_arg("starred"),
        group=request.args.get("group") or None,
        sort="name",
    )
    data = build_workbook(contacts)
    filename = f"通讯录_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return send_file(BytesIO(data), mimetype=XLSX_MIME, as_attachment=True, download_name=filename)


@api.get("/template")
def download_template():
    data = build_template()
    return send_file(BytesIO(data), mimetype=XLSX_MIME, as_attachment=True, download_name="通讯录导入模板.xlsx")


@api.post("/import")
def import_contacts():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ApiError("请选择要导入的 Excel 文件")
    if not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        raise ApiError("仅支持 .xlsx 格式，请先在 Excel 中另存为 .xlsx 再导入")

    data = upload.stream.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError("文件过大，请上传 10MB 以内的 Excel 文件")
    if not data:
        raise ApiError("文件内容为空")

    mode = request.form.get("mode", "merge")
    if mode not in {"merge", "insert"}:
        mode = "merge"

    records, errors = parse_workbook(BytesIO(data))
    if not records and not errors:
        raise ApiError("文件中没有可导入的数据行")

    result = store().bulk_import(records, mode=mode)
    return jsonify(
        {
            "total": len(records) + len(errors),
            "imported": result["imported"],
            "updated": result["updated"],
            "failed": len(errors),
            "mode": mode,
            "errors": errors[:50],
            "errors_truncated": len(errors) > 50,
        }
    )


# --------------------------------------------------------------------- 异常处理
@api.errorhandler(ValidationError)
def handle_validation(exc: ValidationError):
    return jsonify({"error": {"message": exc.message, "field": exc.field}}), 400


@api.errorhandler(NotFoundError)
def handle_not_found(exc: NotFoundError):
    return jsonify({"error": {"message": str(exc)}}), 404


@api.errorhandler(WorkbookError)
def handle_workbook(exc: WorkbookError):
    return jsonify({"error": {"message": str(exc)}}), 400


@api.errorhandler(ApiError)
def handle_api_error(exc: ApiError):
    return jsonify({"error": {"message": exc.message}}), exc.status


@api.app_errorhandler(404)
def handle_404(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": {"message": "接口不存在"}}), 404
    return ("Not Found", 404)


@api.app_errorhandler(405)
def handle_405(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": {"message": "请求方法不被支持"}}), 405
    return ("Method Not Allowed", 405)
