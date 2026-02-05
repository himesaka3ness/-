import requests
import hashlib
import time
from flask import Flask, render_template_string, request, redirect
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# --- 設定 ---
BLOCKED_LANGS = ['zh', 'ru', 'ko']
NG_WORDS = ["死ね", "殺す", "詐欺", "麻薬", "闇バイト", "爆破", "テロ"]
POST_INTERVAL = 10 

def init_db():
    # Render環境では /tmp フォルダを使うのが安全です
    with sqlite3.connect('emergency.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, message TEXT, 
                         device TEXT, country TEXT, user_id TEXT, time TEXT, is_foreign INTEGER)''')

def generate_id(ip):
    seed = datetime.now().strftime('%Y%m%d')
    hash_obj = hashlib.md5((ip + seed).encode())
    return hash_obj.hexdigest()[:8]

def get_location_info(ip):
    try:
        res = requests.get(f'http://ip-api.com/json/{ip}?fields=status,countryCode', timeout=3).json()
        if res.get('status') == 'success':
            code = res.get('countryCode')
            return code, (1 if code != "JP" else 0)
        return "??", 0
    except:
        return "??", 0

def get_device_info(ua):
    ua = ua.lower()
    if 'iphone' in ua: return "iPhone"
    if 'android' in ua: return "Android"
    if 'windows' in ua: return "Windows"
    if 'macintosh' in ua: return "Mac"
    if 'linux' in ua: return "Linux"
    return "Guest"

html_template = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚨 緊急連絡Node</title>
    <style>
        body { background-color: #0b0e14; color: #d1d5db; font-family: sans-serif; margin: 0; padding: 10px; }
        .container { max-width: 600px; margin: auto; }
        .header { background: #1f2937; padding: 12px; border-radius: 8px; text-align: center; border: 1px solid #374151; margin-bottom: 15px; }
        .input-area { background: #111827; padding: 15px; border-radius: 12px; border: 1px solid #374151; margin-bottom: 20px; }
        input, textarea { width: 100%; padding: 12px; margin: 8px 0; background: #1f2937; border: 1px solid #4b5563; color: white; border-radius: 8px; box-sizing: border-box; font-size: 16px; }
        button { width: 100%; padding: 15px; background: #10b981; border: none; font-weight: bold; border-radius: 8px; cursor: pointer; color: white; font-size: 16px; }
        .post { background: #1f2937; padding: 12px; border-radius: 8px; margin-top: 10px; border-bottom: 2px solid #374151; }
        .badge { display: inline-block; background: #374151; color: #10b981; padding: 2px 6px; border-radius: 4px; font-size: 0.7em; margin-right: 4px; font-weight: bold; }
        .foreign-alert { background: #ef4444; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.7em; font-weight: bold; }
        .warning { color: #f87171; font-size: 0.75em; font-weight: bold; display: block; margin-bottom: 5px; }
        .meta { font-size: 0.75em; color: #9ca3af; margin-top: 8px; }
        .id-text { color: #60a5fa; font-family: monospace; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">🚨 緊急連絡Node <br><small>監視・防衛モード</small></div>
        <div class="input-area">
            <form action="/post_msg" method="post">
                <input type="text" name="name" placeholder="名前" required maxlength="10">
                <textarea name="message" rows="3" placeholder="状況を入力..." required maxlength="200"></textarea>
                <button type="submit">送信</button>
            </form>
        </div>
        {% for post in posts %}
        <div class="post">
            {% if is_old(post[6]) %}<span class="warning">⚠️ 古い情報(24h経過)</span>{% endif %}
            <div class="badge">📍 {{ post[4] }}</div>
            {% if post[7] == 1 %}<span class="foreign-alert">⚠️ 外国からの接続</span>{% endif %}
            <div class="badge">{{ post[3] }}</div>
            <div style="margin-top:8px; word-wrap: break-word;">{{ post[2] }}</div>
            <div class="meta">投稿者: {{ post[1] }} <span class="id-text">ID:{{ post[5] }}</span> ｜ {{ post[6] }}</div>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

last_post_times = {}
last_post_contents = {}

def is_old(time_str):
    try:
        ptime = datetime.strptime(time_str, '%m/%d %H:%M').replace(year=datetime.now().year)
        return datetime.now() - ptime > timedelta(hours=24)
    except:
        return False

@app.route('/')
def index():
    init_db()
    with sqlite3.connect('emergency.db') as conn:
        posts = conn.execute('SELECT * FROM posts ORDER BY id DESC LIMIT 50').fetchall()
    return render_template_string(html_template, posts=posts, is_old=is_old)

@app.route('/post_msg', methods=['POST'])
def post_msg():
    ua = request.headers.get('User-Agent', '')
    lang = request.headers.get('Accept-Language', '').lower()
    ip = request.headers.getlist("X-Forwarded-For")[0] if request.headers.getlist("X-Forwarded-For") else request.remote_addr

    if any(b in lang for b in BLOCKED_LANGS) or not lang:
        return "Forbidden Region", 403

    now = time.time()
    msg = request.form.get('message', '').strip()
    if ip in last_post_times and now - last_post_times[ip] < POST_INTERVAL:
        return f"Wait {POST_INTERVAL}s", 429
    if ip in last_post_contents and last_post_contents[ip] == msg:
        return "Duplicate message", 400

    user_id = generate_id(ip)
    device = get_device_info(ua)
    location_code, is_foreign = get_location_info(ip)
    
    if any(w in msg for w in NG_WORDS):
        return "NG word detected", 400

    name = request.form.get('name', 'Anonymous')[:10]
    post_time = datetime.now().strftime('%m/%d %H:%M')
    
    with sqlite3.connect('emergency.db') as conn:
        conn.execute('INSERT INTO posts (name, message, device, country, user_id, time, is_foreign) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (name, msg, device, location_code, user_id, post_time, is_foreign))
    
    last_post_times[ip] = now
    last_post_contents[ip] = msg
    return redirect('/')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
