"""后端接口与 Excel 往返的单元测试（标准库 unittest，无需额外依赖）。

运行::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import load_workbook  # noqa: E402

from app import create_app  # noqa: E402
from backend.excel_io import build_template, parse_workbook  # noqa: E402


class AddressBookApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp.name) / "test.db"
        self.app = create_app(db_path)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # ---------------------------------------------------------------- 工具方法
    def create(self, **overrides):
        payload = {
            "name": "测试联系人",
            "group": "工作",
            "company": "测试公司",
            "department": "研发部",
            "title": "工程师",
            "note": "",
            "starred": False,
            "methods": [
                {"type": "phone", "label": "工作", "value": "13800000001", "primary": True},
                {"type": "email", "label": "工作", "value": "test@example.com", "primary": False},
            ],
        }
        payload.update(overrides)
        return self.client.post("/api/contacts", json=payload)

    # ---------------------------------------------------------------- 基础接口
    def test_health_and_empty_meta(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        meta = self.client.get("/api/meta").get_json()
        self.assertEqual(meta["stats"]["total"], 0)
        self.assertEqual([t["key"] for t in meta["types"]][0], "phone")
        self.assertIn("工作", meta["labels"])

    def test_create_and_get_contact_with_multiple_methods(self):
        response = self.create(
            methods=[
                {"type": "phone", "label": "工作", "value": "13800000001"},
                {"type": "phone", "label": "个人", "value": "0591-22866000"},
                {"type": "email", "label": "工作", "value": "test@example.com"},
                {"type": "wechat", "value": "wx_id"},
                {"type": "qq", "value": "123456"},
                {"type": "address", "label": "家庭", "value": "福建省福州市"},
            ]
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        contact = response.get_json()
        self.assertEqual(len(contact["methods"]), 6)
        self.assertEqual(sum(1 for m in contact["methods"] if m["primary"]), 1)
        self.assertTrue(contact["methods"][0]["primary"])
        self.assertEqual(contact["methods"][1]["type"], "phone")

        fetched = self.client.get(f"/api/contacts/{contact['id']}").get_json()
        self.assertEqual(fetched["name"], "测试联系人")

    def test_validation_errors(self):
        cases = [
            ({"name": ""}, "姓名不能为空"),
            ({"methods": [{"type": "email", "value": "not-an-email"}]}, "邮箱格式不正确"),
            ({"methods": [{"type": "phone", "value": "12ab"}]}, "电话号码"),
            ({"methods": [{"type": "fax", "value": "12345"}]}, "不支持的联系方式类型"),
            ({"name": "太长" * 30}, "不能超过"),
        ]
        for overrides, keyword in cases:
            response = self.create(**overrides)
            self.assertEqual(response.status_code, 400, overrides)
            message = response.get_json()["error"]["message"]
            self.assertIn(keyword, message)

    def test_contacts_sorted_by_pinyin(self):
        for name in ["张伟", "陈志远", "白露", "阿宝"]:
            self.create(name=name)
        names = [item["name"] for item in self.client.get("/api/contacts?sort=name").get_json()["items"]]
        self.assertEqual(names, ["阿宝", "白露", "陈志远", "张伟"])

    def test_star_toggle_and_filters(self):
        first = self.create(name="张三", starred=False).get_json()
        self.create(name="李四", starred=True)

        response = self.client.patch(f"/api/contacts/{first['id']}/star", json={"starred": True})
        self.assertTrue(response.get_json()["starred"])

        starred = self.client.get("/api/contacts?starred=1").get_json()
        self.assertEqual(starred["total"], 2)
        self.assertTrue(all(item["starred"] for item in starred["items"]))

        response = self.client.patch(f"/api/contacts/{first['id']}/star", json={})
        self.assertFalse(response.get_json()["starred"])

    def test_search_and_group_filter(self):
        self.create(name="王小明", company="福州大学", methods=[{"type": "phone", "value": "13911112222"}])
        self.create(name="赵丽", group="家人", company="厦门航空", methods=[{"type": "phone", "value": "13700003333"}])

        by_phone = self.client.get("/api/contacts?q=1391111").get_json()
        self.assertEqual(by_phone["total"], 1)
        self.assertEqual(by_phone["items"][0]["name"], "王小明")

        by_company = self.client.get("/api/contacts?q=厦门").get_json()
        self.assertEqual(by_company["items"][0]["name"], "赵丽")

        by_group = self.client.get("/api/contacts?group=家人").get_json()
        self.assertEqual(by_group["total"], 1)

        groups = self.client.get("/api/meta").get_json()["groups"]
        self.assertEqual({g["name"] for g in groups}, {"工作", "家人"})

    def test_update_replaces_methods_and_delete(self):
        contact = self.create().get_json()
        updated = self.client.put(
            f"/api/contacts/{contact['id']}",
            json={
                "name": "改名后",
                "group": "朋友",
                "methods": [{"type": "phone", "value": "13900009999", "primary": True}],
            },
        ).get_json()
        self.assertEqual(updated["name"], "改名后")
        self.assertEqual(len(updated["methods"]), 1)
        self.assertEqual(updated["methods"][0]["value"], "13900009999")

        self.assertEqual(self.client.delete(f"/api/contacts/{contact['id']}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/contacts/{contact['id']}").status_code, 404)

    # ---------------------------------------------------------------- Excel
    def test_export_headers_and_structure(self):
        self.create(name="张三", starred=True)
        self.create(name="李四", group="家人")
        response = self.client.get("/api/export")
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(io.BytesIO(response.data))
        self.assertIn("通讯录", workbook.sheetnames)
        sheet = workbook["通讯录"]
        headers = [cell.value for cell in sheet[1]]
        self.assertEqual(headers[:5], ["姓名", "分组", "公司", "部门", "职位"])
        self.assertIn("星标", headers)
        self.assertEqual(sheet.max_row, 3)  # 表头 + 2 行

        rows = list(sheet.iter_rows(min_row=2, values_only=True))
        names = [row[0] for row in rows]
        self.assertEqual(sorted(names), ["张三", "李四"])
        star_index = headers.index("星标")
        self.assertIn("是", [row[star_index] for row in rows])

    def test_export_import_round_trip_is_idempotent(self):
        self.create(name="张三", starred=True)
        self.create(name="李四", group="家人")
        exported = self.client.get("/api/export").data

        records, errors = parse_workbook(io.BytesIO(exported))
        self.assertEqual(errors, [])
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["methods"][0]["type"], "phone")

        response = self.client.post(
            "/api/import",
            data={"file": (io.BytesIO(exported), "通讯录.xlsx"), "mode": "merge"},
            content_type="multipart/form-data",
        )
        report = response.get_json()
        self.assertEqual(response.status_code, 200, report)
        self.assertEqual(report["imported"], 0)
        self.assertEqual(report["updated"], 2)
        self.assertEqual(self.client.get("/api/contacts").get_json()["total"], 2)

    def test_import_insert_mode_and_row_errors(self):
        datas = build_template()
        workbook = load_workbook(io.BytesIO(datas))
        sheet = workbook["通讯录"]
        # 追加一行合法数据与一行非法数据（姓名为空）
        sheet.append(["王五", "朋友", "", "", "", "", "", "", "", "", "是", ""])
        sheet.append(["", "朋友", "", "", "", "", "", "", "", "", "否", ""])
        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)

        response = self.client.post(
            "/api/import",
            data={"file": (buffer, "test.xlsx"), "mode": "insert"},
            content_type="multipart/form-data",
        )
        report = response.get_json()
        self.assertEqual(response.status_code, 200, report)
        self.assertEqual(report["imported"], 3)  # 模板 2 行示例 + 王五
        self.assertEqual(report["failed"], 1)
        self.assertIn("姓名不能为空", report["errors"][0]["message"])
        self.assertEqual(report["errors"][0]["row"], 5)

    def test_import_rejects_bad_file(self):
        response = self.client.post(
            "/api/import",
            data={"file": (io.BytesIO(b"not an excel"), "bad.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("无法读取", response.get_json()["error"]["message"])

        response = self.client.post(
            "/api/import",
            data={"file": (io.BytesIO(b"x"), "bad.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)

    def test_template_download(self):
        response = self.client.get("/api/template")
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(io.BytesIO(response.data))
        self.assertIn("填写说明", workbook.sheetnames)
        self.assertEqual(workbook["通讯录"].max_row, 3)

    def test_export_respects_group_filter(self):
        self.create(name="张三")
        self.create(name="李四", group="家人")
        response = self.client.get("/api/export?group=家人")
        workbook = load_workbook(io.BytesIO(response.data))
        rows = list(workbook["通讯录"].iter_rows(min_row=2, values_only=True))
        self.assertEqual([row[0] for row in rows], ["李四"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
