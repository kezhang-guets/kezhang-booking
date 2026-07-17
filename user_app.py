"""用户端 - 端口 8080"""
from flask import Flask, render_template, request, jsonify
from db import get_conn, init_db, generate_schedules, get_all_config

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('user.html')

@app.route('/api/schedules')
def api_schedules():
    generate_schedules()
    conn = get_conn()
    rows = conn.execute("SELECT * FROM schedules ORDER BY date, time_slot").fetchall()
    conn.close()
    from datetime import datetime
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    now_min = now.hour * 60 + now.minute
    result = []
    for r in rows:
        if r['date'] < today_str:
            continue
        if r['date'] == today_str:
            end = r['time_slot'].split('-')[1]
            eh, em = end.split(':')
            if int(eh) * 60 + int(em) <= now_min:
                continue
        result.append(dict(r))
    return jsonify(result)

@app.route('/api/bookings', methods=['POST'])
def api_submit():
    data = request.json
    required = ['schedule_id', 'org_name', 'contact_name', 'contact_phone', 'contact_qq', 'headcount', 'arrival_time']
    for f in required:
        if not data.get(f):
            return jsonify({'ok': False, 'msg': '请填写完整信息'}), 400
    if not data['contact_phone'].isdigit() or len(data['contact_phone']) != 11:
        return jsonify({'ok': False, 'msg': '手机号格式不正确'}), 400

    conn = get_conn()
    s = conn.execute("SELECT * FROM schedules WHERE id=?", (data['schedule_id'],)).fetchone()
    if not s:
        conn.close()
        return jsonify({'ok': False, 'msg': '时段不存在'}), 404

    # validate arrival_time falls within time_slot
    import re
    m = re.match(r'(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})', s['time_slot'])
    at = re.match(r'(\d{1,2}):(\d{2})', data['arrival_time'])
    if m and at:
        start_min = int(m.group(1)) * 60 + int(m.group(2))
        end_min = int(m.group(3)) * 60 + int(m.group(4))
        arrival_min = int(at.group(1)) * 60 + int(at.group(2))
        if arrival_min < start_min or arrival_min > end_min:
            conn.close()
            return jsonify({'ok': False, 'msg': f'到场时间应在 {s["time_slot"]} 范围内'}), 400
    else:
        conn.close()
        return jsonify({'ok': False, 'msg': '到场时间格式不正确（如 08:30）'}), 400

    try:
        conn.execute("BEGIN IMMEDIATE")
        if not s:
            conn.execute("ROLLBACK"); conn.close()
            return jsonify({'ok': False, 'msg': '时段不存在'}), 404
        if s['status'] != 'open':
            conn.execute("ROLLBACK"); conn.close()
            return jsonify({'ok': False, 'msg': '该时段已被预约'}), 400

        existing = conn.execute(
            "SELECT id FROM bookings WHERE schedule_id=? AND status IN ('pending','approved')",
            (data['schedule_id'],)
        ).fetchone()
        if existing:
            conn.execute("ROLLBACK"); conn.close()
            return jsonify({'ok': False, 'msg': '该时段已被预约'}), 400

        conn.execute("UPDATE schedules SET status='booked' WHERE id=?", (data['schedule_id'],))
        conn.execute(
            "INSERT INTO bookings (schedule_id, org_name, contact_name, contact_phone, contact_qq, headcount, arrival_time)"
            " VALUES (?,?,?,?,?,?,?)",
            (data['schedule_id'], data['org_name'], data['contact_name'],
             data['contact_phone'], data['contact_qq'], int(data['headcount']), data['arrival_time'])
        )
        conn.execute("COMMIT"); conn.close()
        return jsonify({'ok': True, 'msg': '预约成功，等待审核'})
    except Exception as e:
        conn.execute("ROLLBACK"); conn.close()
        return jsonify({'ok': False, 'msg': '提交失败，请重试'}), 500

@app.route('/api/bookings/my')
def api_my():
    phone = request.args.get('phone', '')
    if not phone: return jsonify([])
    conn = get_conn()
    rows = conn.execute(
        "SELECT b.*, s.date, s.time_slot FROM bookings b"
        " LEFT JOIN schedules s ON b.schedule_id=s.id"
        " WHERE b.contact_phone=? ORDER BY b.created_at DESC",
        (phone,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/bookings/<int:bid>/cancel', methods=['POST'])
def api_cancel(bid):
    data = request.json or {}
    phone = data.get('phone', '')
    conn = get_conn()
    b = conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
    if not b:
        conn.close()
        return jsonify({'ok': False, 'msg': '预约不存在'}), 404
    if phone and b['contact_phone'] != phone:
        conn.close()
        return jsonify({'ok': False, 'msg': '手机号不匹配'}), 403
    if b['status'] == 'rejected':
        conn.close()
        return jsonify({'ok': False, 'msg': '该预约已被拒绝，无需撤销'}), 400
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (bid,))
        conn.execute("UPDATE schedules SET status='open' WHERE id=?", (b['schedule_id'],))
        conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK"); conn.close()
        return jsonify({'ok': False, 'msg': '撤销失败'}), 500
    conn.close()
    return jsonify({'ok': True, 'msg': '撤销成功'})

@app.route('/api/config')
def api_config():
    cfg = get_all_config()
    cfg.pop('admin_password', None)
    return jsonify(cfg)

if __name__ == '__main__':
    init_db()
    generate_schedules()
    print("\n" + "=" * 50)
    print("  杨科璋沉浸课堂 - 用户预约端")
    print("  地址: http://localhost:8080")
    print("=" * 50 + "\n")
    app.run(host='0.0.0.0', port=8080, debug=False)
