"""
统一应用 - 用于云端部署
/     → 用户预约端
/admin → 管理后台
/api/* → 用户端 API
/admin/api/* → 管理端 API
"""
from flask import Flask, render_template, request, jsonify
from db import get_conn, init_db, generate_schedules, get_all_config, set_config, get_admin_password
import re

app = Flask(__name__)

def check_admin():
    pw = get_admin_password()
    return (request.args.get('token','') == pw or (request.json or {}).get('token','') == pw)

# ====== 页面路由 ======
@app.route('/')
def user_page():
    return render_template('user.html')

@app.route('/admin')
@app.route('/admin/')
def admin_page():
    return render_template('admin.html')

# ====== 用户端 API ======
@app.route('/api/schedules')
def api_schedules():
    generate_schedules()
    conn = get_conn()
    rows = conn.execute("SELECT * FROM schedules ORDER BY date, time_slot").fetchall()
    conn.close()
    # 过滤已过期：今天之前的日期，以及今天已过的时间段
    from datetime import datetime
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    now_min = now.hour * 60 + now.minute
    result = []
    for r in rows:
        if r['date'] < today_str:
            continue
        if r['date'] == today_str:
            end = r['time_slot'].split('-')[1]  # "09:30"
            eh, em = end.split(':')
            if int(eh) * 60 + int(em) <= now_min:
                continue
        result.append(dict(r))
    return jsonify(result)

@app.route('/api/bookings', methods=['POST'])
def api_submit():
    data = request.json
    required = ['schedule_id','org_name','contact_name','contact_phone','contact_qq','headcount','arrival_time']
    for f in required:
        if not data.get(f):
            return jsonify({'ok':False,'msg':'请填写完整信息'}),400
    if not data['contact_phone'].isdigit() or len(data['contact_phone'])!=11:
        return jsonify({'ok':False,'msg':'手机号格式不正确'}),400

    conn = get_conn()
    s = conn.execute("SELECT * FROM schedules WHERE id=?",(data['schedule_id'],)).fetchone()
    if not s:
        conn.close(); return jsonify({'ok':False,'msg':'时段不存在'}),404

    # validate arrival_time
    m = re.match(r'(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})', s['time_slot'])
    at = re.match(r'(\d{1,2}):(\d{2})', data['arrival_time'])
    if m and at:
        start_min = int(m.group(1))*60+int(m.group(2))
        end_min = int(m.group(3))*60+int(m.group(4))
        arrival_min = int(at.group(1))*60+int(at.group(2))
        if arrival_min < start_min or arrival_min > end_min:
            conn.close(); return jsonify({'ok':False,'msg':f'到场时间应在 {s["time_slot"]} 范围内'}),400
    else:
        conn.close(); return jsonify({'ok':False,'msg':'到场时间格式不正确（如08:30）'}),400

    try:
        conn.execute("BEGIN IMMEDIATE")
        if s['status'] != 'open':
            conn.execute("ROLLBACK"); conn.close()
            return jsonify({'ok':False,'msg':'该时段已被预约'}),400
        existing = conn.execute(
            "SELECT id FROM bookings WHERE schedule_id=? AND status IN ('pending','approved')",
            (data['schedule_id'],)
        ).fetchone()
        if existing:
            conn.execute("ROLLBACK"); conn.close()
            return jsonify({'ok':False,'msg':'该时段已被预约'}),400

        conn.execute("UPDATE schedules SET status='booked' WHERE id=?",(data['schedule_id'],))
        conn.execute(
            "INSERT INTO bookings (schedule_id,org_name,contact_name,contact_phone,contact_qq,headcount,arrival_time)"
            " VALUES (?,?,?,?,?,?,?)",
            (data['schedule_id'],data['org_name'],data['contact_name'],data['contact_phone'],
             data['contact_qq'],int(data['headcount']),data['arrival_time'])
        )
        conn.execute("COMMIT"); conn.close()
        return jsonify({'ok':True,'msg':'预约成功，等待审核'})
    except Exception as e:
        conn.execute("ROLLBACK"); conn.close()
        return jsonify({'ok':False,'msg':'提交失败'}),500

@app.route('/api/bookings/my')
def api_my():
    phone = request.args.get('phone','')
    if not phone: return jsonify([])
    conn = get_conn()
    rows = conn.execute(
        "SELECT b.*, s.date, s.time_slot FROM bookings b"
        " LEFT JOIN schedules s ON b.schedule_id=s.id"
        " WHERE b.contact_phone=? ORDER BY b.created_at DESC", (phone,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/config')
def public_config():
    cfg = get_all_config()
    cfg.pop('admin_password', None)
    return jsonify(cfg)

# ====== 管理端 API ======
@app.route('/admin/api/login', methods=['POST'])
def admin_login():
    pw = request.json.get('password','')
    real_pw = get_admin_password()
    if pw == real_pw:
        return jsonify({'ok':True,'token':real_pw})
    return jsonify({'ok':False,'msg':'密码错误'}),401

@app.route('/admin/api/bookings')
def admin_bookings():
    if not check_admin(): return jsonify({'ok':False}),401
    conn = get_conn()
    rows = conn.execute(
        "SELECT b.*, s.date, s.time_slot FROM bookings b"
        " LEFT JOIN schedules s ON b.schedule_id=s.id"
        " ORDER BY b.created_at DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/admin/api/bookings/<int:bid>/review', methods=['POST'])
def admin_review(bid):
    if not check_admin(): return jsonify({'ok':False}),401
    action = request.json.get('action')
    reason = request.json.get('reason','')
    if action not in ('approve','reject','cancel','complete'):
        return jsonify({'ok':False}),400

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        b = conn.execute("SELECT * FROM bookings WHERE id=?",(bid,)).fetchone()
        if not b:
            conn.execute("ROLLBACK"); conn.close()
            return jsonify({'ok':False}),404

        status_map = {'approve':'approved','reject':'rejected','cancel':'cancelled','complete':'completed'}
        status = status_map[action]

        if action in ('reject','cancel'):
            if action=='reject':
                conn.execute("UPDATE bookings SET status=?, reject_reason=? WHERE id=?",(status,reason,bid))
            else:
                conn.execute("UPDATE bookings SET status=? WHERE id=?",(status,bid))
            conn.execute("UPDATE schedules SET status='open' WHERE id=?",(b['schedule_id'],))
        else:
            conn.execute("UPDATE bookings SET status=? WHERE id=?",(status,bid))

        conn.execute("COMMIT"); conn.close()
        return jsonify({'ok':True})
    except Exception:
        conn.execute("ROLLBACK"); conn.close()
        return jsonify({'ok':False}),500

@app.route('/admin/api/bookings/<int:bid>/delete', methods=['POST'])
def admin_delete(bid):
    if not check_admin(): return jsonify({'ok':False}),401
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        b = conn.execute("SELECT * FROM bookings WHERE id=?",(bid,)).fetchone()
        if not b:
            conn.execute("ROLLBACK"); conn.close()
            return jsonify({'ok':False}),404
        conn.execute("DELETE FROM bookings WHERE id=?",(bid,))
        conn.execute("UPDATE schedules SET status='open' WHERE id=?",(b['schedule_id'],))
        conn.execute("COMMIT"); conn.close()
        return jsonify({'ok':True})
    except Exception:
        conn.execute("ROLLBACK"); conn.close()
        return jsonify({'ok':False}),500

@app.route('/admin/api/stats')
def admin_stats():
    if not check_admin(): return jsonify({'ok':False}),401
    conn = get_conn()
    stats = {}
    for s in ['pending','approved','rejected','cancelled','completed']:
        stats[s] = conn.execute("SELECT COUNT(*) FROM bookings WHERE status=?",(s,)).fetchone()[0]
    stats['total'] = sum(stats.values())
    conn.close()
    return jsonify(stats)

@app.route('/admin/api/config')
def admin_config():
    if not check_admin(): return jsonify({'ok':False}),401
    cfg = get_all_config()
    cfg.pop('admin_password',None)
    return jsonify(cfg)

@app.route('/admin/api/config', methods=['POST'])
def admin_config_update():
    if not check_admin(): return jsonify({'ok':False}),401
    data = request.json
    for k,v in data.items():
        if k != 'admin_password': set_config(k,v)
    return jsonify({'ok':True})

@app.route('/admin/api/change_password', methods=['POST'])
def admin_change_password():
    if not check_admin(): return jsonify({'ok':False}),401
    old = request.json.get('old_password','')
    new = request.json.get('new_password','')
    if not new or len(new)<6:
        return jsonify({'ok':False,'msg':'新密码至少6位'}),400
    if old != get_admin_password():
        return jsonify({'ok':False,'msg':'旧密码错误'}),400
    set_config('admin_password',new)
    return jsonify({'ok':True,'msg':'密码修改成功'})

@app.route('/admin/api/init', methods=['POST'])
def admin_init():
    if not check_admin(): return jsonify({'ok':False}),401
    count = generate_schedules()
    return jsonify({'ok':True,'count':count})

if __name__ == '__main__':
    init_db()
    generate_schedules()
    print("\n" + "="*50)
    print("  杨科璋沉浸课堂预约系统")
    print("  用户端: http://localhost:5000/")
    print("  管理端: http://localhost:5000/admin")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
