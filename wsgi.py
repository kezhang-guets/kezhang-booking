"""
PythonAnywhere WSGI 配置文件
用户端：/, /api/*
管理端：/admin, /admin/api/*
"""
import sys
import os

# 项目路径（PythonAnywhere 上需修改为你的路径）
project_home = '/home/George66Ls/kezhang-booking'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from db import init_db, generate_schedules
from app import app as application

# 初始化数据库 + 自动排期
init_db()
generate_schedules()
