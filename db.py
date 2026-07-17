"""共享数据库模块"""
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'kezhang.db')

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(date, time_slot)
        );
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER NOT NULL,
            org_name TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            contact_phone TEXT NOT NULL,
            contact_qq TEXT NOT NULL,
            headcount INTEGER DEFAULT 1,
            arrival_time TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            reject_reason TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (schedule_id) REFERENCES schedules(id)
        );
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );
    ''')
    # migrations
    for col in ['arrival_time', 'reject_reason']:
        try: conn.execute(f"ALTER TABLE bookings ADD COLUMN {col} TEXT DEFAULT ''")
        except Exception: pass
    # default config values
    defaults = {
        'admin_password': 'sxybksdsdzb',
        'contact_name': '谢璐阳',
        'contact_phone': '13307756104',
        'contact_qq': '',
        'hero_title': '杨科璋沉浸课堂',
        'hero_subtitle': '桂林电子科技大学·商学院本科生第三党支部',
        'home_about': '杨科璋精神宣讲团于2025年4月正式成立，由桂林电子科技大学商学院本科生第三党支部牵头组建，是全国首个以杨科璋烈士命名的高校学生宣讲团队。团队以商学院优秀毕业生、"感动中国2017年度人物"、全国消防英雄杨科璋的先进事迹为核心，依托杨科璋沉浸课堂展厅、烈士雕像广场、科璋讲堂三大阵地，秉持"讲好英雄故事、传承红色基因、践行青年责任"的宗旨，构建"展厅沉浸式讲解 + 校园巡回宣讲 + 基层实践分享"三位一体模式。现有核心成员32名、后备宣讲员18名，已累计开展15余场宣讲活动，接待480余人次。',
        'class_item1': '事迹展陈 — 系统梳理"从桂电学子到消防英雄"的生命轨迹，实物展陈与图文史料生动呈现英雄形象',
        'class_item2': '情景演绎 — 创新角色扮演形式，宣讲员化身烈士战友、受灾群众，配合影像再现火场危急场景',
        'class_item3': '互动讨论 — "如果是我会怎么做"引导式提问，在"听讲—体验—思考—共鸣"中实现认知升华',
        'class_item4': '消防科普 — 结合英雄事迹开展校园消防安全知识与应急逃生技能培训',
        'rule1': '开放时间：周二至周五 8:00-18:00',
        'rule2': '预约时段：08:00-09:30 / 10:00-11:30',
        'rule3': '14:30-16:00 / 16:30-18:00',
        'rule4': '每时段仅接待一个单位',
        'rule5': '预约需经审核，通过后请按时到场'
    }
    for k, v in defaults.items():
        try:
            conn.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?,?)", (k, v))
        except Exception:
            pass
    conn.commit()
    conn.close()

TIME_SLOTS = ['08:00-09:30', '10:00-11:30', '14:30-16:00', '16:30-18:00']

def generate_schedules(days=14):
    """生成未来 N 天排期，仅周二到周五"""
    conn = get_conn()
    today = datetime.now()
    count = 0
    for i in range(0, days):
        d = today + timedelta(days=i)
        wd = d.weekday()  # 0=Mon, 6=Sun
        if wd < 1 or wd > 4:  # skip Mon(0) and Sat/Sun(5,6)
            continue
        ds = d.strftime('%Y-%m-%d')
        for ts in TIME_SLOTS:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO schedules (date, time_slot) VALUES (?,?)",
                    (ds, ts)
                )
                count += 1
            except Exception:
                pass
    conn.commit()
    conn.close()
    return count

def get_all_config():
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM config").fetchall()
    conn.close()
    return {r['key']: r['value'] for r in rows}

def set_config(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()

def get_admin_password():
    conn = get_conn()
    row = conn.execute("SELECT value FROM config WHERE key='admin_password'").fetchone()
    conn.close()
    return row['value'] if row else 'sxybksdsdzb'
