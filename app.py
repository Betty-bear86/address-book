"""通讯录管理系统 —— 应用入口。

用法::

    python app.py                    # 启动服务，默认 http://127.0.0.1:8000
    python app.py --port 8123        # 指定端口
    python app.py --demo             # 数据库为空时写入演示数据
    python app.py --host 0.0.0.0     # 允许局域网 / 云服务器访问

环境变量：ADDRESS_BOOK_DB 可覆盖数据库路径，HOST / PORT 可覆盖监听地址。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from flask import Flask, send_from_directory

from backend.api import api
from backend.contacts import ContactStore
from backend.db import Database
from backend.seed import seed_demo

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEFAULT_DB_PATH = BASE_DIR / "data" / "address_book.db"


def create_app(database_path: str | os.PathLike[str] | None = None) -> Flask:
    """应用工厂：便于测试时传入临时数据库。"""
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.json.ensure_ascii = False          # 中文直接输出，方便调试
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

    db_path = Path(database_path or os.environ.get("ADDRESS_BOOK_DB") or DEFAULT_DB_PATH)
    database = Database(db_path)
    database.init_schema()
    app.extensions["db"] = database
    app.extensions["store"] = ContactStore(database)

    app.register_blueprint(api)

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/favicon.svg")
    def favicon():
        return send_from_directory(STATIC_DIR, "favicon.svg")

    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="通讯录管理系统（极限编程作业）")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="监听地址")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="监听端口")
    parser.add_argument("--db", default=None, help="SQLite 数据库路径")
    parser.add_argument("--demo", action="store_true", help="数据库为空时写入演示数据")
    args = parser.parse_args(argv)

    app = create_app(args.db)
    if args.demo:
        if app.extensions["db"].is_empty():
            created = seed_demo(app.extensions["store"])
            print(f"[demo] 已写入 {created} 条演示联系人")
        else:
            print("[demo] 数据库中已存在数据，跳过演示数据写入")

    print(f"\n  通讯录管理系统已启动: http://{args.host}:{args.port}\n")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
