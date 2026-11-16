"""演示数据：首次运行时 ``python app.py --demo`` 可一键写入，便于演示与截图。"""

from __future__ import annotations

from typing import Any

DEMO_CONTACTS: list[dict[str, Any]] = [
    {
        "name": "林晓",
        "group": "工作",
        "company": "福州大学",
        "department": "计算机与大数据学院",
        "title": "辅导员",
        "note": "负责 2026 级软件工程专业，周三下午在办公室。",
        "starred": True,
        "methods": [
            {"type": "phone", "label": "工作", "value": "13806001111", "primary": True},
            {"type": "email", "label": "工作", "value": "linxiao@fzu.edu.cn", "primary": False},
            {"type": "wechat", "label": "", "value": "linxiao_fzu", "primary": False},
            {"type": "address", "label": "工作", "value": "福建省福州市闽侯县学园路 2 号 计算机学院 A305", "primary": False},
        ],
    },
    {
        "name": "陈志远",
        "group": "工作",
        "company": "福州大学",
        "department": "计算机与大数据学院",
        "title": "副教授",
        "note": "软件工程课程组负责人，负责本次极限编程作业的评分。",
        "starred": True,
        "methods": [
            {"type": "phone", "label": "工作", "value": "0591-22866001", "primary": True},
            {"type": "email", "label": "工作", "value": "chenzhiyuan@fzu.edu.cn", "primary": False},
            {"type": "qq", "label": "", "value": "88266001", "primary": False},
        ],
    },
    {
        "name": "王思颖",
        "group": "工作",
        "company": "字节跳动",
        "department": "飞书前端团队",
        "title": "前端工程师",
        "note": "上一届学长，内推与简历咨询可以找他。",
        "starred": True,
        "methods": [
            {"type": "phone", "label": "个人", "value": "18650012233", "primary": True},
            {"type": "email", "label": "个人", "value": "siying.wang@example.com", "primary": False},
            {"type": "wechat", "label": "", "value": "wsiying_dev", "primary": False},
        ],
    },
    {
        "name": "黄雅静",
        "group": "朋友",
        "company": "厦门大学",
        "department": "信息学院",
        "title": "硕士研究生",
        "note": "一起做项目的老搭档，擅长后端与数据库设计。",
        "starred": False,
        "methods": [
            {"type": "phone", "label": "个人", "value": "13559087766", "primary": True},
            {"type": "email", "label": "学校", "value": "huangyj@example.edu.cn", "primary": False},
            {"type": "qq", "label": "", "value": "12087766", "primary": False},
        ],
    },
    {
        "name": "张伟",
        "group": "家人",
        "company": "",
        "department": "",
        "title": "",
        "note": "爸爸，周末固定视频。",
        "starred": True,
        "methods": [
            {"type": "phone", "label": "家庭", "value": "13905910088", "primary": True},
            {"type": "address", "label": "家庭", "value": "福建省泉州市丰泽区田安路 88 号 3 栋 502", "primary": False},
        ],
    },
    {
        "name": "李慧兰",
        "group": "家人",
        "company": "",
        "department": "",
        "title": "",
        "note": "妈妈，喜欢喝铁观音。",
        "starred": True,
        "methods": [
            {"type": "phone", "label": "家庭", "value": "13905910099", "primary": True},
            {"type": "wechat", "label": "", "value": "lihuilan_660", "primary": False},
        ],
    },
    {
        "name": "林建国",
        "group": "客户",
        "company": "福建新大陆科技集团",
        "department": "产品部",
        "title": "产品总监",
        "note": "实习项目对接人，会议固定在周一上午十点。",
        "starred": False,
        "methods": [
            {"type": "phone", "label": "工作", "value": "13905012345", "primary": True},
            {"type": "phone", "label": "工作", "value": "0591-83801234", "primary": False},
            {"type": "email", "label": "工作", "value": "linjg@example.com", "primary": False},
            {"type": "address", "label": "工作", "value": "福建省福州市马尾区儒江东路 136 号", "primary": False},
        ],
    },
    {
        "name": "赵敏",
        "group": "客户",
        "company": "厦门建发集团",
        "department": "信息技术部",
        "title": "项目经理",
        "note": "Excel 导入导出需求的确认人。",
        "starred": False,
        "methods": [
            {"type": "phone", "label": "工作", "value": "13606008899", "primary": True},
            {"type": "email", "label": "工作", "value": "zhaomin@example.cn", "primary": False},
        ],
    },
    {
        "name": "陈嘉豪",
        "group": "同学",
        "company": "福州大学",
        "department": "计算机与大数据学院",
        "title": "2024 级本科生",
        "note": "同桌，一起上极限编程课。",
        "starred": False,
        "methods": [
            {"type": "phone", "label": "个人", "value": "15750812345", "primary": True},
            {"type": "qq", "label": "", "value": "305812345", "primary": False},
            {"type": "wechat", "label": "", "value": "chenjh_2024", "primary": False},
        ],
    },
    {
        "name": "刘思远",
        "group": "同学",
        "company": "福州大学",
        "department": "土木工程学院",
        "title": "2024 级本科生",
        "note": "宿舍楼友，电脑维修小能手。",
        "starred": False,
        "methods": [
            {"type": "phone", "label": "个人", "value": "15806007711", "primary": True},
            {"type": "email", "label": "学校", "value": "liusy@example.edu.cn", "primary": False},
        ],
    },
    {
        "name": "吴宇轩",
        "group": "服务",
        "company": "中国移动",
        "department": "鼓楼营业厅",
        "title": "客户经理",
        "note": "宽带续费与套餐咨询。",
        "starred": False,
        "methods": [
            {"type": "phone", "label": "工作", "value": "10086", "primary": True},
            {"type": "phone", "label": "工作", "value": "15959012345", "primary": False},
        ],
    },
    {
        "name": "郑晓雯",
        "group": "朋友",
        "company": "厦门航空",
        "department": "客舱部",
        "title": "乘务员",
        "note": "经常帮忙查特价机票。",
        "starred": False,
        "methods": [
            {"type": "phone", "label": "个人", "value": "13306001234", "primary": True},
            {"type": "wechat", "label": "", "value": "zhengxw_mf", "primary": False},
        ],
    },
    {
        "name": "孙立",
        "group": "工作",
        "company": "福州大学",
        "department": "教务处",
        "title": "教务科科长",
        "note": "选课、学分认定相关问题咨询。",
        "starred": False,
        "methods": [
            {"type": "phone", "label": "工作", "value": "0591-22866200", "primary": True},
            {"type": "email", "label": "工作", "value": "sunli@fzu.edu.cn", "primary": False},
            {"type": "address", "label": "工作", "value": "福建省福州市闽侯县学园路 2 号 行政楼 205", "primary": False},
        ],
    },
    {
        "name": "何雨桐",
        "group": "朋友",
        "company": "",
        "department": "",
        "title": "",
        "note": "摄影社认识的朋友，会拍毕业照。",
        "starred": False,
        "methods": [
            {"type": "phone", "label": "个人", "value": "18059008877", "primary": True},
            {"type": "wechat", "label": "", "value": "hyt_photo", "primary": False},
            {"type": "other", "label": "", "value": "Instagram: @hyt.photo", "primary": False},
        ],
    },
]


def seed_demo(store) -> int:
    """写入演示数据，返回写入条数。"""
    created = 0
    for payload in DEMO_CONTACTS:
        store.create(payload)
        created += 1
    return created
