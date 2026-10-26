
import os
import re
import sqlite3
from pathlib import Path
from contextlib import closing
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask, render_template_string, request,
    redirect, url_for, session
)
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"
SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(".env faylida FLASK_SECRET_KEY sozlanmagan.")

app = Flask(__name__)
from exam_api import exam_api

app.register_blueprint(exam_api)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_db()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def get_admin_count():
    with closing(get_db()) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM admins"
        ).fetchone()[0]


init_db()


# ---------------- SHARED DESIGN ----------------

BASE_STYLE = """
<style>
* { box-sizing: border-box; }
body {
    margin: 0;
    background: #f5f7fc;
    color: #202b43;
    font-family: Inter, Arial, sans-serif;
}
a { text-decoration: none; color: inherit; }
button, input, select { font: inherit; }
button, .button {
    padding: 11px 15px;
    border: 0;
    border-radius: 9px;
    background: #3156c9;
    color: white;
    cursor: pointer;
    display: inline-block;
}
button:hover, .button:hover { background: #2445aa; }
input, select {
    min-width: 0;
    padding: 11px 12px;
    border: 1px solid #dfe5ef;
    border-radius: 9px;
    background: white;
}
input:focus, select:focus {
    outline: 2px solid #cbd7ff;
    border-color: #3156c9;
}
.muted { color: #7d879b; }
.error {
    background: #fff0f0;
    color: #a32626;
    padding: 12px;
    border-radius: 9px;
    margin-bottom: 15px;
}
.auth-page {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 20px;
}
.auth-card {
    width: 100%;
    max-width: 420px;
    background: white;
    padding: 32px;
    border-radius: 18px;
    box-shadow: 0 10px 40px #23345d0d;
}
.auth-card h1 { color: #3156c9; margin-top: 0; }
.auth-card label {
    display: block;
    font-size: 14px;
    font-weight: 600;
    margin: 16px 0 7px;
}
.auth-card input { width: 100%; }
.auth-card button { width: 100%; margin-top: 22px; }

.sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    width: 230px;
    background: white;
    border-right: 1px solid #e8edf5;
    padding: 27px 17px;
}
.brand {
    color: #3156c9;
    font-size: 23px;
    font-weight: 800;
    padding: 0 10px;
}
.brand-sub {
    font-size: 11px;
    color: #929bad;
    padding: 7px 10px 28px;
}
.nav-label {
    color: #9aa2b2;
    font-size: 11px;
    text-transform: uppercase;
    padding: 10px;
}
.nav-item {
    display: block;
    padding: 13px 12px;
    border-radius: 9px;
    margin: 4px 0;
    color: #536078;
    font-size: 14px;
}
.nav-item:hover { background: #f5f7fc; }
.nav-item.active {
    background: #edf2ff;
    color: #3156c9;
    font-weight: 700;
}
.main {
    margin-left: 230px;
    padding: 28px;
    max-width: 1700px;
}
.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 15px;
    margin-bottom: 25px;
}
.topbar h1 { margin: 0; font-size: 27px; }
.topbar p { margin: 7px 0 0; font-size: 14px; }
.admin-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}
.admin-name {
    background: white;
    border: 1px solid #e8edf5;
    padding: 10px 13px;
    border-radius: 9px;
    font-size: 13px;
}
.logout button {
    color: #536078;
    background: white;
    border: 1px solid #dfe5ef;
}
.cards {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 17px;
    margin-bottom: 22px;
}
.card, .panel {
    background: white;
    border: 1px solid #eaf0f7;
    border-radius: 15px;
    padding: 22px;
    min-width: 0;
}
.card-label { font-size: 13px; color: #7d879b; }
.card-value {
    font-size: 32px;
    font-weight: 800;
    margin-top: 12px;
    overflow-wrap: anywhere;
}
.card-note { font-size: 12px; color: #939bad; margin-top: 6px; }
.panel h2 { font-size: 18px; margin: 0 0 7px; }
.panel-desc { color: #8a93a5; font-size: 13px; margin-bottom: 20px; }
.two-columns {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
    gap: 18px;
}
.class-row { margin: 17px 0; }
.class-meta {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 8px;
    font-size: 13px;
}
.bar-bg {
    height: 9px;
    background: #edf1f8;
    border-radius: 10px;
    overflow: hidden;
}
.bar {
    height: 100%;
    background: #5575e6;
    border-radius: 10px;
}
.class-item {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    background: #f7f9fd;
    padding: 13px;
    border-radius: 9px;
    margin-top: 10px;
}
.class-total { color: #3156c9; font-weight: 700; }
.table-panel {
    background: white;
    border: 1px solid #eaf0f7;
    border-radius: 15px;
    overflow: hidden;
}
.table-heading {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;
    flex-wrap: wrap;
    padding: 21px;
}
.table-heading h2 { margin: 0 0 6px; font-size: 18px; }
.search-form {
    display: flex;
    gap: 9px;
    flex-wrap: wrap;
}
.search-form input { width: 230px; }
.search-form select { min-width: 140px; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; min-width: 600px; }
th, td {
    text-align: left;
    padding: 15px 20px;
    border-top: 1px solid #edf0f6;
}
th {
    background: #fafbfe;
    color: #7c879b;
    font-size: 12px;
    font-weight: 600;
}
td { font-size: 14px; }
.badge {
    display: inline-block;
    padding: 6px 10px;
    background: #edf2ff;
    color: #3156c9;
    border-radius: 8px;
    font-size: 12px;
}
.empty {
    text-align: center;
    padding: 35px;
    color: #8a93a5;
}
.table-footer {
    padding: 14px 20px;
    border-top: 1px solid #edf0f6;
    color: #7d879b;
    font-size: 13px;
}
footer {
    padding: 24px 0 5px;
    color: #a0a7b5;
    text-align: center;
    font-size: 12px;
}
@media(max-width: 1000px) {
    .sidebar { width: 190px; }
    .main { margin-left: 190px; padding: 20px; }
    .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .two-columns { grid-template-columns: 1fr; }
}
@media(max-width: 650px) {
    .sidebar {
        position: static;
        width: 100%;
        padding: 17px;
        border-right: 0;
        border-bottom: 1px solid #e8edf5;
    }
    .brand-sub { padding-bottom: 10px; }
    .nav-label { display: none; }
    .nav-item { display: inline-block; padding: 10px; }
    .main { margin: 0; padding: 15px; }
    .cards { grid-template-columns: 1fr; gap: 12px; }
    .topbar h1 { font-size: 23px; }
    .search-form { width: 100%; }
    .search-form input, .search-form select,
    .search-form button { width: 100%; }
    .table-heading { padding: 17px; }
}
</style>
"""


# ---------------- AUTH PAGES ----------------

REGISTER_HTML = """
<!doctype html><html lang="uz"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Math Temur | Registration</title>
""" + BASE_STYLE + """
</head><body><main class="auth-page"><section class="auth-card">
<h1>Math Temur</h1><p class="muted">Birinchi admin akkauntini yaratish</p>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
<form method="post">
<label>Ism-familiya</label>
<input name="full_name" maxlength="100" autocomplete="name" required>
<label>Login</label>
<input name="username" minlength="3" maxlength="50"
pattern="[A-Za-z0-9_.-]+" autocomplete="username" required>
<label>Parol</label>
<input name="password" type="password" minlength="8" autocomplete="new-password" required>
<label>Parolni tasdiqlash</label>
<input name="confirm_password" type="password" minlength="8" autocomplete="new-password" required>
<button type="submit">Admin yaratish</button>
</form></section></main></body></html>
"""

LOGIN_HTML = """
<!doctype html><html lang="uz"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Math Temur | Login</title>
""" + BASE_STYLE + """
</head><body><main class="auth-page"><section class="auth-card">
<h1>Math Temur</h1><p class="muted">Admin paneliga kirish</p>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
<form method="post">
<label>Login</label><input name="username" autocomplete="username" required>
<label>Parol</label><input name="password" type="password" autocomplete="current-password" required>
<button type="submit">Kirish</button>
</form></section></main></body></html>
"""


# ---------------- SHARED PANEL TEMPLATE ----------------

PANEL_HTML = """
<!doctype html><html lang="uz"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Math Temur | {{ page_title }}</title>
""" + BASE_STYLE + """
</head><body>
<aside class="sidebar">
    <div class="brand">Math Temur</div>
    <div class="brand-sub">TA'LIM BOSHQARUV TIZIMI</div>
    <div class="nav-label">Asosiy menyu</div>
    <a class="nav-item {% if page == 'dashboard' %}active{% endif %}"
       href="{{ url_for('dashboard') }}">⌂ &nbsp; Dashboard</a>
    <a class="nav-item {% if page == 'statistics' %}active{% endif %}"
       href="{{ url_for('statistics') }}">▤ &nbsp; Statistika</a>
    <a class="nav-item {% if page == 'students' %}active{% endif %}"
       href="{{ url_for('students_page') }}">♙ &nbsp; O‘quvchilar</a>
</aside>

<main class="main">
<header class="topbar">
    <div><h1>{{ page_title }}</h1><p class="muted">{{ subtitle }}</p></div>
    <div class="admin-actions">
        <div class="admin-name">♙ {{ admin_name }}</div>
        <form class="logout" method="post" action="{{ url_for('logout') }}">
            <button type="submit">Chiqish</button>
        </form>
    </div>
</header>

{% if page == 'dashboard' %}
<section class="cards">
    <article class="card">
        <div class="card-label">Jami o‘quvchilar</div>
        <div class="card-value">{{ total_students }}</div>
        <div class="card-note">Bazadagi barcha o‘quvchilar</div>
    </article>
    <article class="card">
        <div class="card-label">Sinf guruhlari</div>
        <div class="card-value">{{ class_count }}</div>
        <div class="card-note">O‘quvchisi bor sinflar</div>
    </article>
    <article class="card">
        <div class="card-label">Sinf tanlamaganlar</div>
        <div class="card-value">{{ unassigned_count }}</div>
        <div class="card-note">Sinf biriktirilmagan o‘quvchilar</div>
    </article>
</section>

<section class="two-columns">
    <article class="panel">
        <h2>Sinflar bo‘yicha ko‘rinish</h2>
        <div class="panel-desc">Har bir sinfdagi o‘quvchilar soni</div>
        {% for item in class_stats %}
        <div class="class-row">
            <div class="class-meta"><span>{{ item.class_name }}</span><strong>{{ item.total }}</strong></div>
            <div class="bar-bg"><div class="bar"
            style="width: {{ (item.total * 100 / total_students)|round(1) if total_students else 0 }}%"></div></div>
        </div>
        {% else %}<div class="empty">Hozircha statistika yo‘q.</div>{% endfor %}
    </article>
    <article class="panel">
        <h2>Tezkor ma’lumot</h2>
        <div class="panel-desc">O‘quvchilar boshqaruvi</div>
        {% for item in class_stats %}
        <div class="class-item"><span>{{ item.class_name }}</span><span class="class-total">{{ item.total }} nafar</span></div>
        {% else %}<div class="empty">Hozircha sinflar yo‘q.</div>{% endfor %}
        <p style="margin-top:20px"><a class="button" href="{{ url_for('students_page') }}">O‘quvchilarni ko‘rish</a></p>
    </article>
</section>

{% elif page == 'statistics' %}
<section class="cards">
    <article class="card"><div class="card-label">Jami o‘quvchilar</div><div class="card-value">{{ total_students }}</div></article>
    <article class="card"><div class="card-label">Sinf guruhlari</div><div class="card-value">{{ class_count }}</div></article>
    <article class="card"><div class="card-label">Sinf tanlamaganlar</div><div class="card-value">{{ unassigned_count }}</div></article>
</section>
<section class="panel">
    <h2>Sinflar statistikasi</h2>
    <div class="panel-desc">Diagramma umumiy o‘quvchilar soniga nisbatan ko‘rsatilgan.</div>
    {% for item in class_stats %}
    <div class="class-row">
        <div class="class-meta">
            <span>{{ item.class_name }}</span>
            <strong>{{ item.total }} nafar · {{ (item.total * 100 / total_students)|round(1) if total_students else 0 }}%</strong>
        </div>
        <div class="bar-bg"><div class="bar"
        style="width: {{ (item.total * 100 / total_students)|round(1) if total_students else 0 }}%"></div></div>
    </div>
    {% else %}<div class="empty">Statistika uchun ma’lumot yo‘q.</div>{% endfor %}
</section>

{% elif page == 'students' %}
<section class="table-panel">
    <div class="table-heading">
        <div>
            <h2>O‘quvchilar ro‘yxati</h2>
            <div class="muted" style="font-size:13px">Ism, telefon yoki sinf bo‘yicha qidiring.</div>
        </div>
        <form class="search-form" method="get" action="{{ url_for('students_page') }}">
            <input name="q" value="{{ search }}" placeholder="Ism yoki telefon...">
            <select name="class_name">
                <option value="">Barcha sinflar</option>
                {% for cls in all_classes %}
                <option value="{{ cls }}" {% if selected_class == cls %}selected{% endif %}>{{ cls }}</option>
                {% endfor %}
            </select>
            <button type="submit">Filtrlash</button>
            {% if search or selected_class %}
            <a class="button" href="{{ url_for('students_page') }}">Tozalash</a>
            {% endif %}
        </form>
    </div>
    <div class="table-scroll">
    <table>
        <thead><tr><th>№</th><th>Ism-familiya</th><th>Telefon</th><th>Sinf</th></tr></thead>
        <tbody>
        {% for student in students %}
        <tr>
            <td>{{ loop.index }}</td>
            <td>{{ student.full_name or '—' }}</td>
            <td>{{ student.phone or '—' }}</td>
            <td><span class="badge">{{ student.class_name or 'Tanlanmagan' }}</span></td>
        </tr>
        {% else %}
        <tr><td colspan="4" class="empty">Mos o‘quvchi topilmadi.</td></tr>
        {% endfor %}
        </tbody>
    </table>
    </div>
    <div class="table-footer">
        Topilgan o‘quvchilar: {{ students|length }}
        {% if search %} · Qidiruv: {{ search }}{% endif %}
        {% if selected_class %} · Sinf: {{ selected_class }}{% endif %}
    </div>
</section>
{% endif %}
<footer>Math Temur © 2026</footer>
</main></body></html>
"""


# ---------------- AUTHENTICATION ----------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
def home():
    if "admin_id" in session:
        return redirect(url_for("dashboard"))
    if get_admin_count() == 0:
        return redirect(url_for("register"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if get_admin_count() > 0:
        return redirect(url_for("login"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not full_name or not username or not password:
            error = "Barcha maydonlarni to‘ldiring."
        elif len(full_name) > 100 or len(username) > 50:
            error = "Ism yoki login juda uzun."
        elif len(username) < 3 or not re.fullmatch(r"[A-Za-z0-9_.-]+", username):
            error = "Login kamida 3 belgidan iborat bo‘lsin. Lotin harflari, raqam, nuqta, _ yoki - ishlating."
        elif len(password) < 8:
            error = "Parol kamida 8 ta belgidan iborat bo‘lishi kerak."
        elif password != confirm:
            error = "Parollar mos kelmayapti."
        else:
            conn = get_db()
            try:
                conn.execute("BEGIN IMMEDIATE")
                if conn.execute("SELECT id FROM admins LIMIT 1").fetchone():
                    conn.rollback()
                    return redirect(url_for("login"))

                cursor = conn.execute(
                    "INSERT INTO admins (full_name, username, password_hash) VALUES (?, ?, ?)",
                    (full_name, username, generate_password_hash(password)),
                )
                admin_id = cursor.lastrowid
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                return render_template_string(REGISTER_HTML, error="Bu login band.")
            finally:
                conn.close()

            session.clear()
            session["admin_id"] = admin_id
            session["admin_name"] = full_name
            return redirect(url_for("dashboard"))

        return render_template_string(REGISTER_HTML, error=error)

    return render_template_string(REGISTER_HTML, error=None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if "admin_id" in session:
        return redirect(url_for("dashboard"))
    if get_admin_count() == 0:
        return redirect(url_for("register"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with closing(get_db()) as conn:
            admin = conn.execute(
                "SELECT id, full_name, password_hash FROM admins WHERE username = ?",
                (username,),
            ).fetchone()

        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["full_name"]
            return redirect(url_for("dashboard"))

        error = "Login yoki parol noto‘g‘ri."

    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- SHARED DATA ----------------

def get_statistics(conn):
    total = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]

    class_count = conn.execute("""
        SELECT COUNT(DISTINCT TRIM(class_name))
        FROM students
        WHERE class_name IS NOT NULL AND TRIM(class_name) != ''
    """).fetchone()[0]

    unassigned = conn.execute("""
        SELECT COUNT(*) FROM students
        WHERE class_name IS NULL OR TRIM(class_name) = ''
    """).fetchone()[0]

    classes = conn.execute("""
        SELECT TRIM(class_name) AS class_name, COUNT(*) AS total
        FROM students
        WHERE class_name IS NOT NULL AND TRIM(class_name) != ''
        GROUP BY TRIM(class_name)
        ORDER BY TRIM(class_name) COLLATE NOCASE
    """).fetchall()

    return total, class_count, unassigned, classes


def render_panel(page, title, subtitle, **extra):
    with closing(get_db()) as conn:
        total, class_count, unassigned, classes = get_statistics(conn)
        all_classes = [
            row["class_name"]
            for row in conn.execute("""
                SELECT DISTINCT TRIM(class_name) AS class_name
                FROM students
                WHERE class_name IS NOT NULL AND TRIM(class_name) != ''
                ORDER BY TRIM(class_name) COLLATE NOCASE
            """).fetchall()
        ]

    data = {
        "page": page,
        "page_title": title,
        "subtitle": subtitle,
        "admin_name": session.get("admin_name", "Admin"),
        "total_students": total,
        "class_count": class_count,
        "unassigned_count": unassigned,
        "class_stats": classes,
        "all_classes": all_classes,
        "search": "",
        "selected_class": "",
        "students": [],
    }
    data.update(extra)
    return render_template_string(PANEL_HTML, **data)


@app.route("/dashboard")
@login_required
def dashboard():
    return render_panel(
        "dashboard", "Dashboard",
        "Math Temur tizimining umumiy ko‘rinishi",
    )


@app.route("/statistics")
@login_required
def statistics():
    return render_panel(
        "statistics", "Statistika",
        "O‘quvchilar va sinflar bo‘yicha ko‘rsatkichlar",
    )


@app.route("/students")
@login_required
def students_page():
    # Qiymatlarni tozalash
    search = request.args.get("q", "").strip()[:100]
    selected_class = request.args.get("class_name", "").strip()[:50]

    # Parametrli SQL: foydalanuvchi kiritgan matn SQL kodiga aylanmaydi.
    sql = """
        SELECT full_name, phone, class_name
        FROM students
        WHERE 1 = 1
    """
    params = []

    if search:
        sql += """
            AND (
                COALESCE(full_name, '') LIKE ? COLLATE NOCASE
                OR COALESCE(phone, '') LIKE ?
            )
        """
        pattern = f"%{search}%"
        params.extend([pattern, pattern])

    if selected_class:
        sql += " AND TRIM(COALESCE(class_name, '')) = ?"
        params.append(selected_class)

    sql += " ORDER BY created_at DESC"

    with closing(get_db()) as conn:
        students = conn.execute(sql, params).fetchall()

        # Tanlangan sinf ro‘yxatda haqiqatan mavjudligini tekshirish
        valid_classes = {
            row["class_name"]
            for row in conn.execute("""
                SELECT DISTINCT TRIM(class_name) AS class_name
                FROM students
                WHERE class_name IS NOT NULL AND TRIM(class_name) != ''
            """).fetchall()
        }

    if selected_class and selected_class not in valid_classes:
        selected_class = ""

    return render_panel(
        "students", "O‘quvchilar",
        "O‘quvchilarni qidirish va sinf bo‘yicha filtrlash",
        students=students,
        search=search,
        selected_class=selected_class,
    )


if __name__ == "__main__":
    app.run(debug=True)
