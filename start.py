"""
一键启动脚本 - 生产模式
同时启动用户端 (8080) 和管理端 (8081)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from waitress import serve
from db import init_db, generate_schedules

# 初始化数据库 + 自动排期
init_db()
generate_schedules()

import user_app
import admin_app

import threading

def run_user():
    print("用户预约端 → http://10.33.31.89:8080")
    serve(user_app.app, host='0.0.0.0', port=8080)

def run_admin():
    print("管理后台   → http://10.33.31.89:8081")
    serve(admin_app.app, host='0.0.0.0', port=8081)

print("\n" + "=" * 50)
print("  杨科璋沉浸课堂预约系统 - 生产模式")
print("=" * 50)
print()

t1 = threading.Thread(target=run_user, daemon=False)
t2 = threading.Thread(target=run_admin, daemon=False)
t1.start()
t2.start()
print("  服务已启动，按 Ctrl+C 停止\n")

try:
    t1.join()
    t2.join()
except KeyboardInterrupt:
    print("\n  服务已停止")
