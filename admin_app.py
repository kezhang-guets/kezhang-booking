"""管理端 - 端口 8081"""
from flask import Flask, render_template, request, jsonify
from db import get_conn, init_db, generate_schedules, TIME_SLOTS, get_all_config, set_config, get_admin_password

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('admin.html')

def check_auth():
    pw = get_admin_password()
    return (request.args.get('token', '') == pw or
            (request.json or {}).get('token', '') == pw)

@app.route('/api/login', methods=['POST'])
def api_login():
    pw = request.json.get('password', '')
    real_pw = get_admin_password()
    if pw == real_pw:
        return jsonify({'ok': True, 'token': real_pw})
    return jsonify({'ok': False, 'msg': '密码错误'}), 401

# ---------- 系统设置 ----------

@app.route('/api/config')
def api_config():
    if not check_auth(): return jsonify({'ok':False}), 401
    cfg = get_all_config()
    cfg.pop('admin_password', None)
    return jsonify(cfg)

@app.route('/api/config', methods=['POST'])
def api_config_update():
    if not check_auth(): return jsonify({'ok':False}), 401
    data = request.json
    for k, v in data.items():
        if k == 'admin_password' and v:
            set_config(k, v)
        elif k != 'admin_password':
            set_config(k, v)
    return jsonify({'ok': True})

@app.route('/api/change_password', methods=['POST'])
def api_change_password():
    if not check_auth(): return jsonify({'ok':False}), 401
    old_pw = request.json.get('old_password', '')
    new_pw = request.json.get('new_password', '')
    if not new_pw or len(new_pw) < 6:
        return jsonify({'ok': False, 'msg': '新密码至少6位'}), 400
    if old_pw != get_admin_password():
        return jsonify({'ok': False, 'msg': '旧密码错误'}), 400
    set_config('admin_password', new_pw)
    return jsonify({'ok': True, 'msg': '密码修改成功，请用新密码重新登录'})

# ---------- 排期（已被自动生成替代，保留接口） ----------

@app.route('/api/schedules', methods=['POST'])
def api_add_schedule():
    if not check_auth(): return jsonify({'ok':False}), 401
    data = request.json
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO schedules (date, time_slot) VALUES (?,?)",
                 (data['date'], data['time_slot']))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ---------- 预约审核 ----------

@app.route('/api/bookings')
def api_bookings():
    if not check_auth(): return jsonify({'ok':False}), 401
    conn = get_conn()
    rows = conn.execute(
        "SELECT b.*, s.date, s.time_slot FROM bookings b"
        " LEFT JOIN schedules s ON b.schedule_id=s.id"
        " ORDER BY b.created_at DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/bookings/<int:bid>/review', methods=['POST'])
def api_review(bid):
    if not check_auth(): return jsonify({'ok':False}), 401
    action = request.json.get('action')
    reason = request.json.get('reason', '')
    if action not in ('approve', 'reject', 'cancel', 'complete'):
        return jsonify({'ok': False}), 400

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        b = conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
        if not b:
            conn.execute("ROLLBACK"); conn.close()
            return jsonify({'ok': False}), 404

        status_map = {'approve':'approved', 'reject':'rejected', 'cancel':'cancelled', 'complete':'completed'}
        status = status_map[action]

        if action == 'complete':
            s = conn.execute("SELECT date, time_slot FROM schedules WHERE id=?",(b['schedule_id'],)).fetchone()
            if s:
                from datetime import datetime, timezone, timedelta
                tz = timezone(timedelta(hours=8))
                now = datetime.now(tz)
                end_time = s['time_slot'].split('-')[1]
                eh, em = end_time.split(':')
                slot_end = datetime.strptime(s['date']+' '+eh+':'+em, '%Y-%m-%d %H:%M').replace(tzinfo=tz)
                if now < slot_end:
                    conn.execute("ROLLBACK"); conn.close()
                    return jsonify({'ok':False,'msg':'该时段尚未结束，不能完结'}),400

        if action in ('reject', 'cancel'):
            if action == 'reject':
                conn.execute("UPDATE bookings SET status=?, reject_reason=? WHERE id=?", (status, reason, bid))
            else:
                conn.execute("UPDATE bookings SET status=? WHERE id=?", (status, bid))
            conn.execute("UPDATE schedules SET status='open' WHERE id=?", (b['schedule_id'],))
        else:
            conn.execute("UPDATE bookings SET status=? WHERE id=?", (status, bid))

        conn.execute("COMMIT"); conn.close()
        return jsonify({'ok': True})
    except Exception:
        conn.execute("ROLLBACK"); conn.close()
        return jsonify({'ok': False}), 500

@app.route('/api/stats')
def api_stats():
    if not check_auth(): return jsonify({'ok':False}), 401
    conn = get_conn()
    stats = {}
    for s in ['pending','approved','rejected','cancelled','completed']:
        stats[s] = conn.execute("SELECT COUNT(*) FROM bookings WHERE status=?", (s,)).fetchone()[0]
    stats['total'] = sum(stats.values())
    conn.close()
    return jsonify(stats)

@app.route('/api/init', methods=['POST'])
def api_init():
    if not check_auth(): return jsonify({'ok':False}), 401
    count = generate_schedules()
    return jsonify({'ok': True, 'count': count})

if __name__ == '__main__':
    init_db()
    print("\n" + "=" * 50)
    print("  杨科璋沉浸课堂 - 管理后台")
    print("  地址: http://localhost:8081")
    print("=" * 50 + "\n")
    app.run(host='0.0.0.0', port=8081, debug=False)
