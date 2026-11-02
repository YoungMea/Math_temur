import os
import re
import json
import sqlite3
import zoneinfo
from datetime import datetime, timedelta
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
LINKS_FILE = BASE_DIR / "exam_links.json"
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


# ---------------- DATABASE & HELPERS ----------------

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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS exam_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                exam_type TEXT NOT NULL,
                language TEXT NOT NULL,
                class_group TEXT NOT NULL,
                created_at TEXT NOT NULL,
                token TEXT,
                status TEXT DEFAULT 'pending',
                opened_at TEXT,
                device TEXT,
                target_url TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_entries_tg ON exam_entries(telegram_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_entries_class ON exam_entries(class_group)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exam_entries_created ON exam_entries(created_at)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_exam_entries_token ON exam_entries(token)")

        conn.commit()


def get_admin_count():
    with closing(get_db()) as conn:
        return conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]


init_db()


def load_exam_links():
    if not LINKS_FILE.exists():
        return {}
    try:
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_all_groups():
    data = load_exam_links()
    groups = []
    for exam_type in data:
        for lang in data[exam_type]:
            for g in data[exam_type][lang]:
                if g not in groups:
                    groups.append(g)

    if not groups:
        for grade in range(2, 10):
            for num in range(1, 9):
                groups.append(f"{grade}.{num}")

    return sorted(groups, key=lambda x: [int(p) for p in x.split(".") if p.isdigit()])


def get_tashkent_now():
    try:
        tz = zoneinfo.ZoneInfo("Asia/Tashkent")
        return datetime.now(tz)
    except Exception:
        return datetime.now()


@app.template_filter("format_dt")
def format_datetime_filter(val):
    if not val:
        return "—"
    try:
        clean = str(val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is not None:
            tz = zoneinfo.ZoneInfo("Asia/Tashkent")
            dt = dt.astimezone(tz)
        return dt.strftime("%d.%m.%Y, %H:%M")
    except Exception:
        return str(val)[:16].replace("T", " ")


@app.template_filter("format_date_only")
def format_date_only_filter(val):
    if not val:
        return ""
    try:
        dt = datetime.strptime(str(val), "%Y-%m-%d")
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return str(val)


@app.template_filter("initials")
def initials_filter(val):
    if not val:
        return "??"
    parts = [p for p in str(val).strip().split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return parts[0][:2].upper()


# ---------------- MODERN UI & SHARED STYLES ----------------

BASE_STYLE = """
<style>
:root {
    --primary: #3b66f5;
    --primary-hover: #264fd4;
    --primary-light: #eff4fe;
    --primary-border: #d5e2fd;
    --bg-page: #f8fafc;
    --bg-card: #ffffff;
    --text-main: #0f172a;
    --text-muted: #64748b;
    --text-light: #94a3b8;
    --border: #e2e8f0;
    --border-hover: #cbd5e1;
    --success: #10b981;
    --success-light: #ecfdf5;
    --success-border: #a7f3d0;
    --danger: #ef4444;
    --danger-light: #fef2f2;
    --danger-border: #fecaca;
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.05);
    --shadow-md: 0 4px 12px -2px rgba(15, 23, 42, 0.06), 0 2px 6px -1px rgba(15, 23, 42, 0.03);
    --shadow-lg: 0 12px 28px -4px rgba(15, 23, 42, 0.09), 0 4px 10px -2px rgba(15, 23, 42, 0.04);
}

* { box-sizing: border-box; }
body {
    margin: 0;
    background: var(--bg-page);
    color: var(--text-main);
    font-family: 'Plus Jakarta Sans', Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
}
a { text-decoration: none; color: inherit; }
button, input, select { font: inherit; }

/* Buttons */
.button, button[type="submit"], .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 10px 18px;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: var(--primary);
    color: white;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.18s ease;
    box-shadow: 0 1px 2px rgba(59, 102, 245, 0.2);
    white-space: nowrap;
}
.button:hover, button[type="submit"]:hover, .btn:hover {
    background: var(--primary-hover);
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(59, 102, 245, 0.25);
}
.button:active, button[type="submit"]:active {
    transform: translateY(0);
}
.btn-secondary {
    background: white;
    color: var(--text-main);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
}
.btn-secondary:hover {
    background: #f8fafc;
    border-color: var(--border-hover);
    box-shadow: var(--shadow-sm);
}
.btn-outline-danger {
    background: transparent;
    color: var(--danger);
    border: 1px solid var(--danger-border);
    box-shadow: none;
}
.btn-outline-danger:hover {
    background: var(--danger-light);
    border-color: var(--danger);
    box-shadow: none;
    transform: translateY(-1px);
}
.btn-sm {
    padding: 7px 12px;
    font-size: 12px;
    border-radius: 6px;
}

/* Inputs & Form Elements */
input, select {
    min-width: 0;
    padding: 10px 13px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: white;
    color: var(--text-main);
    font-size: 14px;
    transition: all 0.15s ease;
}
input:focus, select:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(59, 102, 245, 0.15);
}
input[type="date"] {
    position: relative;
    cursor: pointer;
}
input[type="date"]::-webkit-calendar-picker-indicator {
    cursor: pointer;
    opacity: 0.7;
    transition: opacity 0.15s;
}
input[type="date"]::-webkit-calendar-picker-indicator:hover {
    opacity: 1;
}

/* Inputs with SVG Icons */
.input-with-icon {
    position: relative;
    display: flex;
    align-items: center;
    width: 100%;
}
.input-with-icon .input-icon {
    position: absolute;
    left: 11px;
    width: 16px;
    height: 16px;
    stroke: var(--text-muted);
    stroke-width: 2;
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
    pointer-events: none;
}
.input-with-icon input, .input-with-icon select {
    padding-left: 36px;
    width: 100%;
}

.input-disabled {
    background: #f1f5f9;
    color: #64748b;
    cursor: not-allowed;
    border-color: #e2e8f0;
}
.form-vertical {
    display: flex;
    flex-direction: column;
    gap: 16px;
}
.form-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
}
.form-group label {
    font-size: 13px;
    font-weight: 600;
    color: #334155;
}
.field-hint {
    font-size: 12px;
    color: var(--text-muted);
}

/* Dedicated Filter Card (UX/UI Polish) */
.filter-card {
    background: white;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 20px 22px;
    margin-bottom: 22px;
    box-shadow: var(--shadow-sm);
}
.filter-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}
.filter-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-main);
    display: flex;
    align-items: center;
    gap: 8px;
}
.filter-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 13px;
    align-items: flex-end;
}
.field-label {
    font-size: 12px;
    font-weight: 700;
    color: #475569;
    margin-bottom: 6px;
    display: block;
    letter-spacing: 0.02em;
}
.filter-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}

/* Quick Date Chips */
.quick-dates-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 16px;
    padding-top: 14px;
    border-top: 1px dashed var(--border);
}
.quick-dates-list {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}
.quick-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
}
.chip-btn {
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
    border-radius: 99px;
    border: 1px solid var(--border);
    background: #f8fafc;
    color: #475569;
    cursor: pointer;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.chip-btn:hover {
    background: #eff4fe;
    border-color: var(--primary-border);
    color: var(--primary);
}
.chip-btn.active {
    background: var(--primary);
    border-color: var(--primary);
    color: white;
}
.chip-btn.chip-clear {
    color: var(--danger);
    background: var(--danger-light);
    border-color: var(--danger-border);
}

/* Active Filter Badges */
.active-filters-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 12px;
    font-size: 13px;
}
.active-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--primary-light);
    color: var(--primary);
    border: 1px solid var(--primary-border);
    padding: 4px 10px;
    border-radius: 99px;
    font-size: 12px;
    font-weight: 600;
}
.clear-all-link {
    color: var(--danger);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    margin-left: 6px;
}
.clear-all-link:hover {
    text-decoration: underline;
}

/* Alerts */
.alert {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    border-radius: var(--radius-md);
    margin-bottom: 20px;
    font-size: 14px;
    font-weight: 500;
    animation: fadeIn 0.3s ease;
}
.alert-success {
    background: var(--success-light);
    color: #065f46;
    border: 1px solid var(--success-border);
}
.alert-error {
    background: var(--danger-light);
    color: #991b1b;
    border: 1px solid var(--danger-border);
}
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Auth Layout */
.auth-page {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 24px;
    background: radial-gradient(circle at 50% 0%, #edf2fe 0%, #f8fafc 70%);
}
.auth-card {
    width: 100%;
    max-width: 430px;
    background: white;
    padding: 38px 34px;
    border-radius: 20px;
    border: 1px solid var(--border);
    box-shadow: var(--shadow-lg);
}
.auth-logo {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    background: linear-gradient(135deg, #3b66f5 0%, #1e40af 100%);
    color: white;
    border-radius: 12px;
    font-weight: 800;
    font-size: 20px;
    margin-bottom: 18px;
    box-shadow: 0 4px 12px rgba(59, 102, 245, 0.3);
}
.auth-card h1 {
    font-size: 24px;
    font-weight: 800;
    color: var(--text-main);
    margin: 0 0 6px;
}
.auth-card p.muted {
    font-size: 14px;
    color: var(--text-muted);
    margin: 0 0 24px;
}
.auth-card input { width: 100%; }
.auth-card button { width: 100%; margin-top: 24px; padding: 13px; font-size: 15px; }

/* Sidebar */
.sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    width: 250px;
    background: white;
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 24px 16px;
    z-index: 100;
}
.brand-box {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 10px 24px;
    border-bottom: 1px solid #f1f5f9;
    margin-bottom: 16px;
}
.brand-logo {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    background: linear-gradient(135deg, #3b66f5 0%, #2546bc 100%);
    color: white;
    font-weight: 800;
    font-size: 17px;
    border-radius: 10px;
    box-shadow: 0 4px 10px rgba(59, 102, 245, 0.25);
    flex-shrink: 0;
}
.brand-name {
    font-size: 18px;
    font-weight: 800;
    color: var(--text-main);
    letter-spacing: -0.02em;
    line-height: 1.2;
}
.brand-sub {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-light);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-top: 2px;
}
.nav-label {
    color: var(--text-light);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 8px 12px;
    margin-top: 6px;
}
.nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    margin: 3px 0;
    color: #475569;
    font-size: 14px;
    font-weight: 600;
    transition: all 0.15s ease;
}
.nav-item:hover {
    background: #f8fafc;
    color: var(--primary);
}
.nav-item.active {
    background: var(--primary-light);
    color: var(--primary);
    font-weight: 700;
}
.nav-item .nav-icon {
    width: 19px;
    height: 19px;
    stroke: currentColor;
    stroke-width: 2;
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
}

/* Sidebar Footer */
.sidebar-footer {
    padding-top: 16px;
    border-top: 1px solid #f1f5f9;
}
.sidebar-user {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 10px;
    border-radius: var(--radius-md);
    background: #f8fafc;
    border: 1px solid var(--border);
}
.user-avatar {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%);
    color: #3730a3;
    font-weight: 700;
    font-size: 15px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    flex-shrink: 0;
}
.user-details {
    min-width: 0;
    flex: 1;
}
.user-name {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-main);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.user-role {
    font-size: 11px;
    color: var(--text-muted);
}

/* Main Area */
.main {
    margin-left: 250px;
    padding: 30px 36px;
    max-width: 1600px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}
.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 24px;
}
.topbar h1 {
    margin: 0;
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: var(--text-main);
}
.topbar p {
    margin: 4px 0 0;
    font-size: 14px;
    color: var(--text-muted);
}
.topbar-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}

/* Cards */
.cards {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 20px;
    margin-bottom: 24px;
}
.card {
    background: white;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 22px 24px;
    box-shadow: var(--shadow-sm);
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, box-shadow 0.2s;
}
.card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
}
.card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
}
.card-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.icon-badge {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}
.icon-badge svg {
    width: 20px;
    height: 20px;
    stroke-width: 2;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
}
.badge-blue { background: #eff4fe; color: #3b66f5; }
.badge-green { background: #ecfdf5; color: #10b981; }
.badge-purple { background: #faf5ff; color: #8b5cf6; }
.badge-amber { background: #fffbeb; color: #f59e0b; }

.card-value {
    font-size: 34px;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: var(--text-main);
    line-height: 1;
}
.card-note {
    font-size: 12px;
    color: var(--text-light);
    margin-top: 10px;
}

/* Panels */
.panel {
    background: white;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 24px;
    box-shadow: var(--shadow-sm);
}
.panel-header-with-icon {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 22px;
    padding-bottom: 16px;
    border-bottom: 1px solid #f1f5f9;
}
.panel h2 {
    font-size: 18px;
    font-weight: 700;
    margin: 0 0 4px;
    color: var(--text-main);
}
.panel-desc {
    color: var(--text-muted);
    font-size: 13px;
    margin: 0;
}
.two-columns {
    display: grid;
    grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
    gap: 22px;
}

/* Class Bars */
.class-row { margin: 16px 0; }
.class-meta {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 8px;
    font-size: 13px;
}
.class-meta span { font-weight: 600; color: #334155; }
.class-meta strong { color: var(--primary); font-weight: 700; }
.bar-bg {
    height: 8px;
    background: #edf2f7;
    border-radius: 99px;
    overflow: hidden;
}
.bar {
    height: 100%;
    background: linear-gradient(90deg, #3b66f5 0%, #6366f1 100%);
    border-radius: 99px;
}

/* Groups Grid (64 ta guruh uchun) */
.groups-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 14px;
    margin-top: 18px;
}
.group-card {
    background: white;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 16px;
    transition: all 0.18s ease;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.group-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
    border-color: var(--primary-border);
}
.group-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}
.group-title {
    font-size: 17px;
    font-weight: 800;
    color: var(--text-main);
}
.grade-badge {
    font-size: 11px;
    font-weight: 700;
    color: var(--primary);
    background: var(--primary-light);
    padding: 3px 8px;
    border-radius: 6px;
}
.group-entries {
    font-size: 13px;
    color: var(--text-muted);
    margin-bottom: 12px;
    font-weight: 500;
}
.group-entries strong {
    color: var(--text-main);
}
.group-links-status {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-bottom: 14px;
}
.mini-badge {
    font-size: 10px;
    font-weight: 700;
    padding: 3px 6px;
    border-radius: 4px;
    text-transform: uppercase;
}
.mini-badge-active {
    background: #ecfdf5;
    color: #065f46;
    border: 1px solid #a7f3d0;
}
.mini-badge-empty {
    background: #f1f5f9;
    color: #94a3b8;
    border: 1px solid #e2e8f0;
}

/* Filter Tabs */
.filter-tabs {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-bottom: 18px;
}
.filter-tab {
    padding: 7px 14px;
    background: white;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted);
    transition: all 0.15s ease;
}
.filter-tab:hover {
    background: #f8fafc;
    color: var(--primary);
}
.filter-tab.active {
    background: var(--primary);
    color: white;
    border-color: var(--primary);
}

/* Tables */
.table-panel {
    background: white;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    overflow: hidden;
}
.table-heading {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    padding: 20px 24px;
    border-bottom: 1px solid var(--border);
}
.table-heading h2 { margin: 0 0 4px; font-size: 18px; font-weight: 700; }
.search-form {
    display: flex;
    align-items: center;
    gap: 9px;
    flex-wrap: wrap;
}
.table-scroll { overflow-x: auto; }
table {
    width: 100%;
    border-collapse: collapse;
    min-width: 750px;
}
th, td {
    text-align: left;
    padding: 15px 20px;
    border-bottom: 1px solid #f1f5f9;
}
th {
    background: #f8fafc;
    color: #64748b;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
td {
    font-size: 14px;
    color: #1e293b;
}
tr:hover td {
    background: #fafcff;
}

/* User cell with Avatar (UX polish) */
.user-cell {
    display: flex;
    align-items: center;
    gap: 11px;
}
.user-avatar-sm {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: linear-gradient(135deg, #eff4fe 0%, #dbeafe 100%);
    color: var(--primary);
    font-weight: 800;
    font-size: 13px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    border: 1px solid var(--primary-border);
}
.user-title {
    font-weight: 700;
    color: var(--text-main);
    font-size: 14px;
}

/* Copyable Telegram ID badge */
.copy-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #f1f5f9;
    padding: 4px 9px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    color: #334155;
    border: 1px solid #e2e8f0;
    transition: all 0.15s ease;
    user-select: none;
}
.copy-badge:hover {
    background: #eff4fe;
    border-color: var(--primary-border);
    color: var(--primary);
}
.copy-icon {
    width: 13px;
    height: 13px;
    stroke: currentColor;
    stroke-width: 2;
    fill: none;
    opacity: 0.7;
}

/* Badges */
.badge-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 99px;
    font-size: 12px;
    font-weight: 700;
    white-space: nowrap;
}
.badge-group {
    background: var(--primary-light);
    color: var(--primary);
    border: 1px solid var(--primary-border);
}
.badge-exam {
    background: #eff4fe;
    color: #2563eb;
    border: 1px solid #bfdbfe;
}
.badge-mini {
    background: #faf5ff;
    color: #7c3aed;
    border: 1px solid #e9d5ff;
}
.badge-uzb {
    background: #ecfdf5;
    color: #059669;
    border: 1px solid #a7f3d0;
}
.badge-rus {
    background: #fffbeb;
    color: #d97706;
    border: 1px solid #fde68a;
}
.badge-opened {
    background: #ecfdf5;
    color: #047857;
    border: 1px solid #a7f3d0;
}
.badge-pending {
    background: #f8fafc;
    color: #64748b;
    border: 1px solid #e2e8f0;
}
.device-pill {
    font-size: 11px;
    background: #f1f5f9;
    color: #475569;
    padding: 2px 7px;
    border-radius: 5px;
    font-weight: 600;
}

.time-cell {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-weight: 600;
    color: #334155;
    font-size: 13px;
}
.time-row {
    display: flex;
    align-items: center;
    gap: 6px;
}
.time-icon {
    width: 14px;
    height: 14px;
    stroke: var(--text-muted);
    stroke-width: 2;
    fill: none;
    flex-shrink: 0;
}

.empty {
    text-align: center;
    padding: 50px 20px;
    color: var(--text-muted);
    font-size: 14px;
}
.table-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 24px;
    background: #fafbfc;
    border-top: 1px solid var(--border);
    color: var(--text-muted);
    font-size: 13px;
    font-weight: 500;
}

/* Recent list */
.recent-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    background: #f8fafc;
    border: 1px solid #f1f5f9;
    border-radius: var(--radius-sm);
    margin-top: 9px;
}
.recent-student {
    display: flex;
    align-items: center;
    gap: 10px;
}
.recent-time {
    font-size: 12px;
    color: var(--text-muted);
    font-weight: 500;
    white-space: nowrap;
}

/* Footer */
footer {
    margin-top: auto;
    padding: 28px 0 10px;
    color: var(--text-light);
    text-align: center;
    font-size: 13px;
}

/* Responsive */
@media (max-width: 1050px) {
    .sidebar { width: 210px; }
    .main { margin-left: 210px; padding: 22px; }
    .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .two-columns { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
    .sidebar {
        position: static;
        width: 100%;
        border-right: 0;
        border-bottom: 1px solid var(--border);
        padding: 14px;
    }
    .brand-box { padding-bottom: 10px; margin-bottom: 10px; }
    .nav-label { display: none; }
    .sidebar-menu { display: flex; flex-wrap: wrap; gap: 4px; }
    .nav-item { padding: 8px 10px; margin: 0; font-size: 13px; }
    .sidebar-footer { display: none; }
    .main { margin-left: 0; padding: 16px; }
    .cards { grid-template-columns: 1fr; gap: 12px; }
    .topbar h1 { font-size: 22px; }
    .filter-grid { grid-template-columns: 1fr; }
    .filter-actions { width: 100%; flex-direction: column; }
    .filter-actions button, .filter-actions a { width: 100%; }
}
</style>
<script>
function copyToClipboard(text, el) {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(text).then(function() {
        var original = el.innerHTML;
        el.innerHTML = '<span style="color:#059669; font-weight:700;">✓ Nusxalandi!</span>';
        setTimeout(function() {
            el.innerHTML = original;
        }, 1400);
    });
}
function setFilterDate(val) {
    var input = document.getElementById('filter-date');
    if (input) {
        input.value = val;
        document.getElementById('exam-filter-form').submit();
    }
}
</script>
"""


# ---------------- AUTH TEMPLATES ----------------

REGISTER_HTML = """
<!doctype html>
<html lang="uz">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Math Temur | Registratsiya</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    """ + BASE_STYLE + """
</head>
<body>
    <main class="auth-page">
        <section class="auth-card">
            <div class="auth-logo">MT</div>
            <h1>Math Temur</h1>
            <p class="muted">Boshqaruv tizimiga birinchi adminni ro‘yxatdan o‘tkazish</p>
            
            {% if error %}
            <div class="alert alert-error">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <span>{{ error }}</span>
            </div>
            {% endif %}

            <form method="post" class="form-vertical">
                <div class="form-group">
                    <label>Ism-familiya</label>
                    <input name="full_name" placeholder="Masalan: Temur Rustamov" maxlength="100" autocomplete="name" required>
                </div>
                <div class="form-group">
                    <label>Login</label>
                    <input name="username" placeholder="Masalan: admin" minlength="3" maxlength="50" pattern="[A-Za-z0-9_.-]+" autocomplete="username" required>
                    <span class="field-hint">Lotin harflari, raqam yoki nuqta</span>
                </div>
                <div class="form-group">
                    <label>Parol</label>
                    <input name="password" type="password" placeholder="Kamida 8 ta belgi" minlength="8" autocomplete="new-password" required>
                </div>
                <div class="form-group">
                    <label>Parolni tasdiqlash</label>
                    <input name="confirm_password" type="password" placeholder="Parolni qayta tering" minlength="8" autocomplete="new-password" required>
                </div>
                <button type="submit">Admin akkauntini yaratish</button>
            </form>
        </section>
    </main>
</body>
</html>
"""

LOGIN_HTML = """
<!doctype html>
<html lang="uz">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Math Temur | Kirish</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    """ + BASE_STYLE + """
</head>
<body>
    <main class="auth-page">
        <section class="auth-card">
            <div class="auth-logo">MT</div>
            <h1>Xush kelibsiz</h1>
            <p class="muted">Math Temur boshqaruv paneliga kiring</p>
            
            {% if error %}
            <div class="alert alert-error">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <span>{{ error }}</span>
            </div>
            {% endif %}

            <form method="post" class="form-vertical">
                <div class="form-group">
                    <label>Login</label>
                    <input name="username" placeholder="Loginni kiriting" autocomplete="username" required autofocus>
                </div>
                <div class="form-group">
                    <label>Parol</label>
                    <input name="password" type="password" placeholder="Parolni kiriting" autocomplete="current-password" required>
                </div>
                <button type="submit">Panelga kirish</button>
            </form>
        </section>
    </main>
</body>
</html>
"""


# ---------------- MAIN PANEL TEMPLATE ----------------

PANEL_HTML = """
<!doctype html>
<html lang="uz">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Math Temur | {{ page_title }}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    """ + BASE_STYLE + """
</head>
<body>

<aside class="sidebar">
    <div>
        <div class="brand-box">
            <div class="brand-logo">MT</div>
            <div>
                <div class="brand-name">Math Temur</div>
                <div class="brand-sub">Boshqaruv Tizimi</div>
            </div>
        </div>

        <div class="nav-label">Asosiy menyu</div>
        <div class="sidebar-menu">
            <a class="nav-item {% if page == 'dashboard' %}active{% endif %}" href="{{ url_for('dashboard') }}">
                <svg class="nav-icon" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/></svg>
                <span>Dashboard</span>
            </a>
            <a class="nav-item {% if page == 'students' %}active{% endif %}" href="{{ url_for('students_page') }}">
                <svg class="nav-icon" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                <span>O‘quvchilar</span>
            </a>
            <a class="nav-item {% if page == 'classes' %}active{% endif %}" href="{{ url_for('classes_page') }}">
                <svg class="nav-icon" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
                <span>Sinf guruhlari</span>
            </a>
            <a class="nav-item {% if page == 'exam_entries' %}active{% endif %}" href="{{ url_for('exam_entries_page') }}">
                <svg class="nav-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <span>Examga kirishlar</span>
            </a>
            <a class="nav-item {% if page == 'statistics' %}active{% endif %}" href="{{ url_for('statistics') }}">
                <svg class="nav-icon" viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg>
                <span>Statistika</span>
            </a>

            <div class="nav-label" style="margin-top: 14px;">Xavfsizlik</div>
            <a class="nav-item {% if page == 'settings' %}active{% endif %}" href="{{ url_for('settings_page') }}">
                <svg class="nav-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                <span>Sozlamalar</span>
            </a>
        </div>
    </div>

    <div class="sidebar-footer">
        <a href="{{ url_for('settings_page') }}" class="sidebar-user" title="Sozlamalarga o‘tish">
            <div class="user-avatar">{{ admin_name[:1]|upper }}</div>
            <div class="user-details">
                <div class="user-name">{{ admin_name }}</div>
                <div class="user-role">Administrator</div>
            </div>
        </a>
    </div>
</aside>

<main class="main">
    <header class="topbar">
        <div>
            <h1>{{ page_title }}</h1>
            <p>{{ subtitle }}</p>
        </div>
        <div class="topbar-actions">
            <a href="{{ url_for('settings_page') }}" class="button btn-secondary" title="Parolni o‘zgartirish">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                <span>Sozlamalar</span>
            </a>
            <form method="post" action="{{ url_for('logout') }}" style="margin: 0;">
                <button type="submit" class="button btn-outline-danger" title="Tizimdan chiqish">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                    <span>Chiqish</span>
                </button>
            </form>
        </div>
    </header>

    {% if page == 'dashboard' %}
    <section class="cards">
        <article class="card">
            <div class="card-top">
                <span class="card-label">Jami o‘quvchilar</span>
                <div class="icon-badge badge-blue">
                    <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                </div>
            </div>
            <div class="card-value">{{ total_students }}</div>
            <div class="card-note">Botda ro‘yxatdan o‘tgan o‘quvchilar</div>
        </article>
        <article class="card">
            <div class="card-top">
                <span class="card-label">Barcha sinf guruhlari</span>
                <div class="icon-badge badge-green">
                    <svg viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
                </div>
            </div>
            <div class="card-value">{{ total_classes }}</div>
            <div class="card-note">2-9 sinflar (har birida 8 tadan guruh)</div>
        </article>
        <article class="card">
            <div class="card-top">
                <span class="card-label">Examga kirishlar soni</span>
                <div class="icon-badge badge-purple">
                    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                </div>
            </div>
            <div class="card-value">{{ total_entries }}</div>
            <div class="card-note">Jami so‘rovlar · <strong style="color: #047857;">{{ opened_entries }} tasi imtihonga kirdi</strong></div>
        </article>
    </section>

    <section class="two-columns">
        <article class="panel">
            <div class="panel-header-with-icon">
                <div class="icon-badge badge-blue">
                    <svg viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg>
                </div>
                <div>
                    <h2>Eng faol sinf guruhlari</h2>
                    <p class="panel-desc">Examga eng ko‘p kirilgan guruhlar reytingi</p>
                </div>
            </div>

            {% for item in group_stats %}
            <div class="class-row">
                <div class="class-meta">
                    <span>{{ item.class_group }}-guruh</span>
                    <strong>{{ item.total }} marta kirilgan ({{ (item.total * 100 / total_entries)|round(1) if total_entries else 0 }}%)</strong>
                </div>
                <div class="bar-bg">
                    <div class="bar" style="width: {{ (item.total * 100 / total_entries)|round(1) if total_entries else 0 }}%"></div>
                </div>
            </div>
            {% else %}
            <div class="empty">Hozircha examga kirishlar mavjud emas.</div>
            {% endfor %}

            <div style="margin-top: 20px;">
                <a class="button btn-secondary" href="{{ url_for('classes_page') }}" style="width: 100%;">
                    <span>Barcha 64 ta sinf guruhini ko‘rish</span>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </a>
            </div>
        </article>

        <article class="panel">
            <div class="panel-header-with-icon">
                <div class="icon-badge badge-purple">
                    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                </div>
                <div>
                    <h2>Oxirgi exam faolligi</h2>
                    <p class="panel-desc">O‘quvchilarning so‘nggi imtihonga kirishlari</p>
                </div>
            </div>

            {% for row in recent_entries %}
            <div class="recent-item">
                <div class="recent-student">
                    <div class="user-avatar-sm" style="width: 32px; height: 32px; font-size: 11px;">{{ row.full_name | initials }}</div>
                    <div>
                        <div style="font-weight: 700; font-size: 14px; color: var(--text-main);">{{ row.full_name }}</div>
                        <div style="display: flex; gap: 6px; align-items: center; margin-top: 2px;">
                            <span class="badge-pill badge-group" style="padding: 1px 7px; font-size: 11px;">{{ row.class_group }}</span>
                            {% if row.status == 'opened' %}
                            <span style="font-size: 11px; font-weight: 700; color: #047857;">🟢 Kirdi</span>
                            {% else %}
                            <span style="font-size: 11px; font-weight: 600; color: #64748b;">⏳ Ochmagan</span>
                            {% endif %}
                        </div>
                    </div>
                </div>
                <div class="recent-time">{{ (row.opened_at or row.created_at) | format_dt }}</div>
            </div>
            {% else %}
            <div class="empty">Hozircha o‘quvchilar imtihonga kirmagan.</div>
            {% endfor %}

            <div style="margin-top: 20px;">
                <a class="button" href="{{ url_for('exam_entries_page') }}" style="width: 100%;">
                    <span>Barcha exam kirishlari tarixi</span>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </a>
            </div>
        </article>
    </section>

    {% elif page == 'students' %}
    <section class="table-panel">
        <div class="table-heading">
            <div>
                <h2>O‘quvchilar ro‘yxati</h2>
                <p class="panel-desc">Bazada ro‘yxatdan o‘tgan o‘quvchilarning asosiy shaxsiy ma’lumotlari</p>
            </div>
            <form class="search-form" method="get" action="{{ url_for('students_page') }}">
                <div class="input-with-icon" style="width: 290px;">
                    <svg class="input-icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    <input name="q" value="{{ search }}" placeholder="Ism, telefon yoki Telegram ID...">
                </div>
                <button type="submit">
                    <span>Qidirish</span>
                </button>
                {% if search %}
                <a class="button btn-secondary" href="{{ url_for('students_page') }}">Tozalash</a>
                {% endif %}
            </form>
        </div>
        <div class="table-scroll">
            <table>
                <thead>
                    <tr>
                        <th style="width: 60px;">№</th>
                        <th>O‘quvchi</th>
                        <th>Telefon raqami</th>
                        <th>Telegram ID</th>
                        <th>Ro‘yxatdan o‘tgan vaqti</th>
                    </tr>
                </thead>
                <tbody>
                {% for student in students %}
                <tr>
                    <td style="color: var(--text-light); font-weight: 600;">{{ loop.index }}</td>
                    <td>
                        <div class="user-cell">
                            <div class="user-avatar-sm">{{ student.full_name | initials }}</div>
                            <div>
                                <div class="user-title">{{ student.full_name or '—' }}</div>
                            </div>
                        </div>
                    </td>
                    <td style="font-weight: 500;">{{ student.phone or '—' }}</td>
                    <td>
                        <span class="copy-badge" onclick="copyToClipboard('{{ student.telegram_id }}', this)" title="Nusxalash uchun bosing">
                            <code>{{ student.telegram_id }}</code>
                            <svg class="copy-icon" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                        </span>
                    </td>
                    <td style="color: var(--text-muted); font-weight: 500;">
                        <span class="time-row">
                            <svg class="time-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                            <span>{{ student.created_at | format_dt }}</span>
                        </span>
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="5" class="empty">Kiritilgan parametrlar bo‘yicha o‘quvchi topilmadi.</td>
                </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
        <div class="table-footer">
            <div>Jami o‘quvchilar: <strong>{{ students|length }}</strong> nafar</div>
            {% if search %}
            <div style="color: var(--primary);">Qidiruv: "{{ search }}"</div>
            {% endif %}
        </div>
    </section>

    {% elif page == 'classes' %}
    <div class="filter-tabs">
        <a href="{{ url_for('classes_page') }}" class="filter-tab {% if not selected_grade %}active{% endif %}">Barcha sinflar (64)</a>
        {% for gr in all_grades %}
        <a href="{{ url_for('classes_page', grade=gr) }}" class="filter-tab {% if selected_grade == gr %}active{% endif %}">{{ gr }}-sinf (8)</a>
        {% endfor %}
    </div>

    <section class="panel">
        <div class="panel-header-with-icon">
            <div class="icon-badge badge-green">
                <svg viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
            </div>
            <div>
                <h2>Sinf guruhlari ro‘yxati</h2>
                <p class="panel-desc">exam_links.json asosidagi barcha 64 ta guruh holati va examga kirishlar soni</p>
            </div>
        </div>

        <div class="groups-grid">
            {% for c in classes_cards %}
            <div class="group-card">
                <div>
                    <div class="group-card-header">
                        <span class="group-title">{{ c.group }}-guruh</span>
                        <span class="grade-badge">{{ c.grade }}-sinf</span>
                    </div>

                    <div class="group-entries">
                        Examga kirishlar: <strong>{{ c.entries_count }} ta</strong>
                    </div>

                    <div class="group-links-status">
                        <span class="mini-badge {% if c.has_exam %}mini-badge-active{% else %}mini-badge-empty{% endif %}">
                            Exam: {% if c.has_exam %}Mavjud{% else %}Yo‘q{% endif %}
                        </span>
                        <span class="mini-badge {% if c.has_mini %}mini-badge-active{% else %}mini-badge-empty{% endif %}">
                            Mini: {% if c.has_mini %}Mavjud{% else %}Yo‘q{% endif %}
                        </span>
                    </div>
                </div>

                <a href="{{ url_for('exam_entries_page', group=c.group) }}" class="button btn-secondary btn-sm" style="width: 100%;">
                    <span>Kirishlar tarixini ko‘rish</span>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </a>
            </div>
            {% endfor %}
        </div>
    </section>

    {% elif page == 'exam_entries' %}
    <!-- DEDICATED MODERN FILTER CARD -->
    <section class="filter-card">
        <div class="filter-card-header">
            <span class="filter-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
                <span>Filtrlar va Sanani tanlash</span>
            </span>
            {% if search or selected_date or selected_group or selected_type or selected_lang or selected_status %}
            <a class="clear-all-link" href="{{ url_for('exam_entries_page') }}">Barcha filtrlarni tozalash ✕</a>
            {% endif %}
        </div>

        <form id="exam-filter-form" method="get" action="{{ url_for('exam_entries_page') }}">
            <div class="filter-grid">
                <div>
                    <label class="field-label">Qidiruv</label>
                    <div class="input-with-icon">
                        <svg class="input-icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                        <input name="q" value="{{ search }}" placeholder="Ism, tel yoki ID...">
                    </div>
                </div>

                <div>
                    <label class="field-label">Sana (Kalendar)</label>
                    <div class="input-with-icon">
                        <svg class="input-icon" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                        <input type="date" id="filter-date" name="date" value="{{ selected_date }}">
                    </div>
                </div>

                <div>
                    <label class="field-label">Sinf guruhi</label>
                    <div class="input-with-icon">
                        <svg class="input-icon" viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
                        <select name="group">
                            <option value="">Barcha guruhlar (64)</option>
                            {% for grp in all_groups %}
                            <option value="{{ grp }}" {% if selected_group == grp %}selected{% endif %}>{{ grp }}-guruh</option>
                            {% endfor %}
                        </select>
                    </div>
                </div>

                <div>
                    <label class="field-label">Imtihon turi</label>
                    <div class="input-with-icon">
                        <svg class="input-icon" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
                        <select name="exam_type">
                            <option value="">Barcha turlar</option>
                            <option value="Exam" {% if selected_type == 'Exam' %}selected{% endif %}>Exam</option>
                            <option value="Mini Exam" {% if selected_type == 'Mini Exam' %}selected{% endif %}>Mini Exam</option>
                        </select>
                    </div>
                </div>

                <div>
                    <label class="field-label">Til</label>
                    <div class="input-with-icon">
                        <svg class="input-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                        <select name="language">
                            <option value="">Barcha tillar</option>
                            <option value="Uzb" {% if selected_lang == 'Uzb' %}selected{% endif %}>O‘zbekcha</option>
                            <option value="Rus" {% if selected_lang == 'Rus' %}selected{% endif %}>Ruscha</option>
                        </select>
                    </div>
                </div>

                <div>
                    <label class="field-label">Holati (Status)</label>
                    <div class="input-with-icon">
                        <svg class="input-icon" viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                        <select name="status">
                            <option value="">Barcha holatlar</option>
                            <option value="opened" {% if selected_status == 'opened' %}selected{% endif %}>🟢 Imtihonga kirdi</option>
                            <option value="pending" {% if selected_status == 'pending' %}selected{% endif %}>⏳ Ochmagan</option>
                        </select>
                    </div>
                </div>

                <div class="filter-actions">
                    <button type="submit" style="width: 100%;">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                        <span>Filtrlash</span>
                    </button>
                    {% if search or selected_date or selected_group or selected_type or selected_lang or selected_status %}
                    <a class="button btn-secondary" href="{{ url_for('exam_entries_page') }}" title="Tozalash">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </a>
                    {% endif %}
                </div>
            </div>

            <div class="quick-dates-bar">
                <div class="quick-dates-list">
                    <span class="quick-label">Tezkor sana:</span>
                    <button type="button" class="chip-btn {% if selected_date == today_str %}active{% endif %}" onclick="setFilterDate('{{ today_str }}')">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                        <span>Bugun ({{ today_str | format_date_only }})</span>
                    </button>
                    <button type="button" class="chip-btn {% if selected_date == yesterday_str %}active{% endif %}" onclick="setFilterDate('{{ yesterday_str }}')">
                        <span>Kecha ({{ yesterday_str | format_date_only }})</span>
                    </button>
                    {% if selected_date %}
                    <button type="button" class="chip-btn chip-clear" onclick="setFilterDate('')">
                        <span>Sanani tozalash ✕</span>
                    </button>
                    {% endif %}
                </div>
                <div style="font-size: 13px; color: var(--text-muted); font-weight: 600;">
                    Topildi: <strong style="color: var(--primary);">{{ entries|length }} ta</strong> yozuv
                </div>
            </div>

            {% if search or selected_date or selected_group or selected_type or selected_lang or selected_status %}
            <div class="active-filters-bar">
                <span class="quick-label">Faol filtrlar:</span>
                {% if search %}
                <span class="active-badge">Qidiruv: "{{ search }}"</span>
                {% endif %}
                {% if selected_date %}
                <span class="active-badge">📅 Sana: {{ selected_date | format_date_only }}</span>
                {% endif %}
                {% if selected_group %}
                <span class="active-badge">🎓 Guruh: {{ selected_group }}</span>
                {% endif %}
                {% if selected_type %}
                <span class="active-badge">📝 Imtihon: {{ selected_type }}</span>
                {% endif %}
                {% if selected_lang %}
                <span class="active-badge">🌐 Til: {{ selected_lang }}</span>
                {% endif %}
                {% if selected_status %}
                <span class="active-badge">⚡ Holati: {% if selected_status == 'opened' %}🟢 Kirdi{% else %}⏳ Ochmagan{% endif %}</span>
                {% endif %}
                <a class="clear-all-link" href="{{ url_for('exam_entries_page') }}">Barchasini tozalash</a>
            </div>
            {% endif %}
        </form>
    </section>

    <!-- ENTRIES TABLE -->
    <section class="table-panel">
        <div class="table-scroll">
            <table>
                <thead>
                    <tr>
                        <th style="width: 50px;">№</th>
                        <th>O‘quvchi</th>
                        <th>Telefon raqami</th>
                        <th>Telegram ID</th>
                        <th>Sinf guruhi</th>
                        <th>Imtihon & Til</th>
                        <th>Holati</th>
                        <th>Kirgan vaqti & Qurilma</th>
                    </tr>
                </thead>
                <tbody>
                {% for row in entries %}
                <tr>
                    <td style="color: var(--text-light); font-weight: 600;">{{ loop.index }}</td>
                    <td>
                        <div class="user-cell">
                            <div class="user-avatar-sm">{{ row.full_name | initials }}</div>
                            <div>
                                <div class="user-title">{{ row.full_name }}</div>
                            </div>
                        </div>
                    </td>
                    <td style="font-weight: 500;">{{ row.phone }}</td>
                    <td>
                        <span class="copy-badge" onclick="copyToClipboard('{{ row.telegram_id }}', this)" title="Nusxalash uchun bosing">
                            <code>{{ row.telegram_id }}</code>
                            <svg class="copy-icon" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                        </span>
                    </td>
                    <td><span class="badge-pill badge-group">{{ row.class_group }}-guruh</span></td>
                    <td>
                        <div style="display: flex; gap: 5px; flex-wrap: wrap;">
                            {% if row.exam_type == 'Mini Exam' %}
                            <span class="badge-pill badge-mini">Mini</span>
                            {% else %}
                            <span class="badge-pill badge-exam">Exam</span>
                            {% endif %}
                            {% if row.language == 'Rus' %}
                            <span class="badge-pill badge-rus">Rus</span>
                            {% else %}
                            <span class="badge-pill badge-uzb">Uzb</span>
                            {% endif %}
                        </div>
                    </td>
                    <td>
                        {% if row.status == 'opened' %}
                        <span class="badge-pill badge-opened">🟢 Kirdi</span>
                        {% else %}
                        <span class="badge-pill badge-pending">⏳ Ochmagan</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if row.status == 'opened' and row.opened_at %}
                        <div class="time-cell">
                            <span class="time-row">
                                <svg class="time-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                                <span>{{ row.opened_at | format_dt }}</span>
                            </span>
                            {% if row.device %}
                            <span class="device-pill" style="align-self: flex-start;">📱 {{ row.device }}</span>
                            {% endif %}
                        </div>
                        {% else %}
                        <div class="time-cell">
                            <span class="time-row" style="color: #94a3b8; font-weight: 500; font-size: 12px;">
                                <span>Havola berilgan: {{ row.created_at | format_dt }}</span>
                            </span>
                            <span style="color: #d97706; font-size: 11px; font-weight: 600;">Hali ochmagan</span>
                        </div>
                        {% endif %}
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="8" class="empty">
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
                            <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="1.5"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                            <span style="font-weight: 600; color: #475569;">Tanlangan sana yoki parametrlar bo‘yicha hech qanday kirish topilmadi.</span>
                            <span style="font-size: 13px; color: #94a3b8;">Boshqa sanani tanlang yoki filtrlarni tozalab ko‘ring.</span>
                            {% if search or selected_date or selected_group or selected_type or selected_lang or selected_status %}
                            <a class="button btn-secondary btn-sm" href="{{ url_for('exam_entries_page') }}" style="margin-top: 8px;">Filtrlarni tozalash</a>
                            {% endif %}
                        </div>
                    </td>
                </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
        <div class="table-footer">
            <div>Jami ko‘rsatilgan: <strong>{{ entries|length }}</strong> ta qayd</div>
            {% if selected_date %}
            <div style="color: var(--primary); font-weight: 600;">📅 Tanlangan sana: {{ selected_date | format_date_only }}</div>
            {% endif %}
        </div>
    </section>

    {% elif page == 'statistics' %}
    <section class="cards">
        <article class="card">
            <div class="card-top">
                <span class="card-label">Jami o‘quvchilar</span>
                <div class="icon-badge badge-blue">
                    <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                </div>
            </div>
            <div class="card-value">{{ total_students }}</div>
            <div class="card-note">Tizimdagi jami o‘quvchilar</div>
        </article>
        <article class="card">
            <div class="card-top">
                <span class="card-label">Barcha guruhlar</span>
                <div class="icon-badge badge-green">
                    <svg viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
                </div>
            </div>
            <div class="card-value">{{ total_classes }}</div>
            <div class="card-note">2 dan 9-sinfgacha bo‘lgan guruhlar</div>
        </article>
        <article class="card">
            <div class="card-top">
                <span class="card-label">Jami exam kirishlari</span>
                <div class="icon-badge badge-purple">
                    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                </div>
            </div>
            <div class="card-value">{{ total_entries }}</div>
            <div class="card-note">O‘quvchilarning imtihon faolligi</div>
        </article>
    </section>

    <section class="panel">
        <div class="panel-header-with-icon">
            <div class="icon-badge badge-blue">
                <svg viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg>
            </div>
            <div>
                <h2>Guruhlar faolligi statistikasi</h2>
                <p class="panel-desc">Qaysi sinf guruhlari o‘quvchilari imtihonlarga eng ko‘p kirganligi tahlili</p>
            </div>
        </div>

        {% for item in group_stats %}
        <div class="class-row">
            <div class="class-meta">
                <span>{{ item.class_group }}-sinf guruhi</span>
                <strong>{{ item.total }} marta · {{ (item.total * 100 / total_entries)|round(1) if total_entries else 0 }}%</strong>
            </div>
            <div class="bar-bg">
                <div class="bar" style="width: {{ (item.total * 100 / total_entries)|round(1) if total_entries else 0 }}%"></div>
            </div>
        </div>
        {% else %}
        <div class="empty">Statistika uchun exam kirishlari mavjud emas.</div>
        {% endfor %}
    </section>

    {% elif page == 'settings' %}
    {% if success %}
    <div class="alert alert-success">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
        <span>{{ success }}</span>
    </div>
    {% endif %}

    {% if error %}
    <div class="alert alert-error">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span>{{ error }}</span>
    </div>
    {% endif %}

    <div class="two-columns">
        <article class="panel">
            <div class="panel-header-with-icon">
                <div class="icon-badge badge-blue">
                    <svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                </div>
                <div>
                    <h2>Parolni o‘zgartirish</h2>
                    <p class="panel-desc">Akkaunt xavfsizligini oshirish uchun parolni yangilang</p>
                </div>
            </div>

            <form method="post" action="{{ url_for('settings_page') }}" class="form-vertical">
                <input type="hidden" name="action" value="change_password">
                <div class="form-group">
                    <label>Joriy (eski) parol</label>
                    <input type="password" name="current_password" placeholder="Hozirgi parolingizni kiriting" required autocomplete="current-password">
                </div>
                <div class="form-group">
                    <label>Yangi parol</label>
                    <input type="password" name="new_password" minlength="8" placeholder="Yangi parol (kamida 8 belgi)" required autocomplete="new-password">
                    <span class="field-hint">Kamida 8 ta belgidan iborat ishonchli parol kiriting</span>
                </div>
                <div class="form-group">
                    <label>Yangi parolni tasdiqlash</label>
                    <input type="password" name="confirm_password" minlength="8" placeholder="Yangi parolni qayta kiriting" required autocomplete="new-password">
                </div>
                <button type="submit">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                    <span>Yangi parolni saqlash</span>
                </button>
            </form>
        </article>

        <article class="panel">
            <div class="panel-header-with-icon">
                <div class="icon-badge badge-purple">
                    <svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                </div>
                <div>
                    <h2>Profil ma’lumotlari</h2>
                    <p class="panel-desc">Admin ismi va tizim ma’lumotlari</p>
                </div>
            </div>

            <form method="post" action="{{ url_for('settings_page') }}" class="form-vertical">
                <input type="hidden" name="action" value="update_profile">
                <div class="form-group">
                    <label>Login (username)</label>
                    <input type="text" value="{{ admin_info.username }}" disabled class="input-disabled">
                    <span class="field-hint">Login tizim identifikatori bo‘lib, uni o‘zgartirib bo‘lmaydi</span>
                </div>
                <div class="form-group">
                    <label>Ism-familiya</label>
                    <input type="text" name="full_name" value="{{ admin_info.full_name }}" maxlength="100" required>
                </div>
                <div class="form-group">
                    <label>Akkaunt yaratilgan sana</label>
                    <input type="text" value="{{ admin_info.created_at[:19] if admin_info.created_at else '—' }}" disabled class="input-disabled">
                </div>
                <button type="submit" class="button btn-secondary">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>
                    <span>Ismni yangilash</span>
                </button>
            </form>
        </article>
    </div>
    {% endif %}

    <footer>Math Temur © 2026 · Ta’lim boshqaruv tizimi</footer>
</main>
</body>
</html>
"""


# ---------------- AUTHENTICATION & VIEWS ----------------

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


# ---------------- EXAM REDIRECT TRACKING ROUTE ----------------

@app.route("/exam/go/<token>")
def redirect_exam_link(token):
    token = str(token).strip()
    with closing(get_db()) as conn:
        entry = conn.execute(
            "SELECT * FROM exam_entries WHERE token = ?",
            (token,)
        ).fetchone()

        if not entry:
            return render_template_string("""
            <!doctype html><html lang="uz"><head><meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Havola topilmadi | Math Temur</title>
            <style>
            body { font-family: -apple-system, Inter, sans-serif; display: grid; place-items: center; min-height: 100vh; background: #f8fafc; color: #1e293b; text-align: center; margin: 0; padding: 20px; }
            .card { background: white; padding: 36px 28px; border-radius: 16px; border: 1px solid #e2e8f0; max-width: 440px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
            h2 { color: #e11d48; margin-top: 0; }
            p { color: #64748b; font-size: 14px; line-height: 1.6; }
            </style>
            </head><body><div class="card">
            <h2>⚠️ Havola topilmadi</h2>
            <p>Ushbu imtihon havolasi eskirgan yoki mavjud emas. Iltimos, Telegram bot orqali guruhni qaytadan tanlang.</p>
            </div></body></html>
            """), 404

        ua = request.headers.get("User-Agent", "")
        device = "Boshqa qurilma"
        if "iPhone" in ua or "iPad" in ua:
            device = "iPhone / iOS"
        elif "Android" in ua:
            device = "Android"
        elif "Windows" in ua:
            device = "Windows PC"
        elif "Macintosh" in ua:
            device = "Mac OS"
        elif "Linux" in ua:
            device = "Linux"

        now = get_tashkent_now().isoformat()
        conn.execute("""
            UPDATE exam_entries
            SET status = 'opened',
                opened_at = COALESCE(opened_at, ?),
                device = ?
            WHERE token = ?
        """, (now, device, token))
        conn.commit()

        target = entry["target_url"]
        if not target or not target.startswith(("http://", "https://")):
            return render_template_string("""
            <!doctype html><html lang="uz"><head><meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Havola tayyor emas | Math Temur</title>
            <style>
            body { font-family: -apple-system, Inter, sans-serif; display: grid; place-items: center; min-height: 100vh; background: #f8fafc; color: #1e293b; text-align: center; margin: 0; padding: 20px; }
            .card { background: white; padding: 36px 28px; border-radius: 16px; border: 1px solid #e2e8f0; max-width: 440px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
            h2 { color: #f59e0b; margin-top: 0; }
            p { color: #64748b; font-size: 14px; line-height: 1.6; }
            </style>
            </head><body><div class="card">
            <h2>⏳ Test havolasi tayyor emas</h2>
            <p>Ushbu guruh uchun Google Forms testi hali joylanmagan. Iltimos, o‘qituvchingizga murojaat qiling.</p>
            </div></body></html>
            """), 200

        return redirect(target, code=302)


# ---------------- SHARED DATA & PANELS ----------------

def get_dashboard_data(conn):
    total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    entry_row = conn.execute("""
        SELECT 
            COUNT(*) as total, 
            COALESCE(SUM(CASE WHEN status = 'opened' THEN 1 ELSE 0 END), 0) as opened 
        FROM exam_entries
    """).fetchone()
    total_entries = entry_row["total"]
    opened_entries = entry_row["opened"]

    group_stats = conn.execute("""
        SELECT class_group, COUNT(*) as total
        FROM exam_entries
        GROUP BY class_group
        ORDER BY total DESC, class_group ASC
    """).fetchall()

    recent_entries = conn.execute("""
        SELECT 
            e.id,
            e.telegram_id,
            COALESCE(s.full_name, 'Noma‘lum') AS full_name,
            COALESCE(s.phone, '—') AS phone,
            e.exam_type,
            e.language,
            e.class_group,
            e.status,
            e.opened_at,
            e.device,
            e.created_at
        FROM exam_entries e
        LEFT JOIN students s ON e.telegram_id = s.telegram_id
        ORDER BY e.created_at DESC
        LIMIT 6
    """).fetchall()

    return total_students, 64, total_entries, opened_entries, group_stats, recent_entries


def render_panel(page, title, subtitle, **extra):
    with closing(get_db()) as conn:
        total_students, total_classes, total_entries, opened_entries, group_stats, recent_entries = get_dashboard_data(conn)

    tashkent_now = get_tashkent_now()
    today_str = tashkent_now.strftime("%Y-%m-%d")
    yesterday_str = (tashkent_now - timedelta(days=1)).strftime("%Y-%m-%d")

    data = {
        "page": page,
        "page_title": title,
        "subtitle": subtitle,
        "admin_name": session.get("admin_name", "Admin"),
        "total_students": total_students,
        "total_classes": total_classes,
        "total_entries": total_entries,
        "opened_entries": opened_entries,
        "group_stats": group_stats,
        "recent_entries": recent_entries,
        "today_str": today_str,
        "yesterday_str": yesterday_str,
        "search": "",
        "students": [],
        "classes_cards": [],
        "entries": [],
        "all_groups": [],
        "all_grades": [str(i) for i in range(2, 10)],
        "selected_grade": "",
        "selected_date": "",
        "selected_group": "",
        "selected_type": "",
        "selected_lang": "",
        "selected_status": "",
        "success": None,
        "error": None,
    }
    data.update(extra)
    return render_template_string(PANEL_HTML, **data)


@app.route("/dashboard")
@login_required
def dashboard():
    return render_panel(
        "dashboard", "Dashboard",
        "Math Temur tizimining asosiy ko‘rsatkichlari va so‘nggi imtihon faolligi",
    )


@app.route("/students")
@login_required
def students_page():
    search = request.args.get("q", "").strip()[:100]

    sql = """
        SELECT telegram_id, full_name, phone, created_at
        FROM students
        WHERE 1 = 1
    """
    params = []

    if search:
        sql += """
            AND (
                COALESCE(full_name, '') LIKE ? COLLATE NOCASE
                OR COALESCE(phone, '') LIKE ?
                OR CAST(telegram_id AS TEXT) LIKE ?
            )
        """
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    sql += " ORDER BY created_at DESC"

    with closing(get_db()) as conn:
        students = conn.execute(sql, params).fetchall()

    return render_panel(
        "students", "O‘quvchilar",
        "Bazada ro‘yxatdan o‘tgan barcha o‘quvchilar ma’lumotlari",
        students=students,
        search=search,
    )


@app.route("/classes")
@login_required
def classes_page():
    selected_grade = request.args.get("grade", "").strip()
    all_groups = get_all_groups()
    exam_links_data = load_exam_links()

    with closing(get_db()) as conn:
        cursor = conn.execute("SELECT class_group, COUNT(*) as cnt FROM exam_entries GROUP BY class_group")
        entry_counts = dict(cursor.fetchall())

    cards = []
    for g in all_groups:
        grade = g.split(".")[0]
        if selected_grade and grade != selected_grade:
            continue

        has_exam = bool(
            exam_links_data.get("Exam", {}).get("Rus", {}).get(g) or
            exam_links_data.get("Exam", {}).get("Uzb", {}).get(g)
        )
        has_mini = bool(
            exam_links_data.get("Mini Exam", {}).get("Rus", {}).get(g) or
            exam_links_data.get("Mini Exam", {}).get("Uzb", {}).get(g)
        )

        cards.append({
            "group": g,
            "grade": grade,
            "entries_count": entry_counts.get(g, 0),
            "has_exam": has_exam,
            "has_mini": has_mini,
        })

    return render_panel(
        "classes", "Sinf guruhlari",
        "exam_links.json dagi barcha sinflar (2-9 sinflar) va guruhlar holati",
        classes_cards=cards,
        selected_grade=selected_grade,
    )


@app.route("/exam-entries")
@login_required
def exam_entries_page():
    search = request.args.get("q", "").strip()[:100]
    selected_date = request.args.get("date", "").strip()[:10]
    selected_group = request.args.get("group", "").strip()[:20]
    selected_type = request.args.get("exam_type", "").strip()[:20]
    selected_lang = request.args.get("language", "").strip()[:20]
    selected_status = request.args.get("status", "").strip()[:20]

    sql = """
        SELECT 
            e.id,
            e.telegram_id,
            COALESCE(s.full_name, 'Noma‘lum') AS full_name,
            COALESCE(s.phone, '—') AS phone,
            e.exam_type,
            e.language,
            e.class_group,
            e.status,
            e.opened_at,
            e.device,
            e.token,
            e.created_at
        FROM exam_entries e
        LEFT JOIN students s ON e.telegram_id = s.telegram_id
        WHERE 1 = 1
    """
    params = []

    if search:
        sql += """
            AND (
                COALESCE(s.full_name, '') LIKE ? COLLATE NOCASE
                OR COALESCE(s.phone, '') LIKE ?
                OR CAST(e.telegram_id AS TEXT) LIKE ?
            )
        """
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    if selected_date:
        sql += """
            AND (
                substr(e.created_at, 1, 10) = ?
                OR date(e.created_at, '+5 hours') = ?
            )
        """
        params.extend([selected_date, selected_date])

    if selected_group:
        sql += " AND e.class_group = ?"
        params.append(selected_group)

    if selected_type:
        sql += " AND e.exam_type = ?"
        params.append(selected_type)

    if selected_lang:
        sql += " AND e.language = ?"
        params.append(selected_lang)

    if selected_status:
        if selected_status == "opened":
            sql += " AND e.status = 'opened'"
        elif selected_status == "pending":
            sql += " AND (e.status = 'pending' OR e.status IS NULL)"

    sql += " ORDER BY e.created_at DESC"

    with closing(get_db()) as conn:
        entries = conn.execute(sql, params).fetchall()

    return render_panel(
        "exam_entries", "Examga kirishlar tarixi",
        "O‘quvchilar qachon sinf va guruh tanlab imtihonga kirganligi bo‘yicha to‘liq qaydnoma",
        entries=entries,
        search=search,
        selected_date=selected_date,
        selected_group=selected_group,
        selected_type=selected_type,
        selected_lang=selected_lang,
        selected_status=selected_status,
        all_groups=get_all_groups(),
    )


@app.route("/statistics")
@login_required
def statistics():
    return render_panel(
        "statistics", "Statistika",
        "O‘quvchilar va guruhlar bo‘yicha umumiy faollik ko‘rsatkichlari",
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    admin_id = session.get("admin_id")
    success = None
    error = None

    with closing(get_db()) as conn:
        admin = conn.execute(
            "SELECT id, full_name, username, password_hash, created_at FROM admins WHERE id = ?",
            (admin_id,)
        ).fetchone()

    if not admin:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "change_password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not check_password_hash(admin["password_hash"], current_password):
                error = "Hozirgi (eski) parol noto‘g‘ri kiritildi."
            elif len(new_password) < 8:
                error = "Yangi parol kamida 8 ta belgidan iborat bo‘lishi kerak."
            elif new_password != confirm_password:
                error = "Yangi parollar bir-biriga mos kelmadi. Qayta tekshirib ko‘ring."
            else:
                new_hash = generate_password_hash(new_password)
                with closing(get_db()) as conn:
                    conn.execute(
                        "UPDATE admins SET password_hash = ? WHERE id = ?",
                        (new_hash, admin_id)
                    )
                    conn.commit()
                with closing(get_db()) as conn:
                    admin = conn.execute(
                        "SELECT id, full_name, username, password_hash, created_at FROM admins WHERE id = ?",
                        (admin_id,)
                    ).fetchone()
                success = "Parolingiz muvaffaqiyatli o‘zgartirildi!"

        elif action == "update_profile":
            full_name = request.form.get("full_name", "").strip()
            if not full_name:
                error = "Ism-familiya bo‘sh bo‘lishi mumkin emas."
            elif len(full_name) > 100:
                error = "Ism-familiya juda uzun (maksimal 100 ta belgi)."
            else:
                with closing(get_db()) as conn:
                    conn.execute(
                        "UPDATE admins SET full_name = ? WHERE id = ?",
                        (full_name, admin_id)
                    )
                    conn.commit()
                session["admin_name"] = full_name
                with closing(get_db()) as conn:
                    admin = conn.execute(
                        "SELECT id, full_name, username, password_hash, created_at FROM admins WHERE id = ?",
                        (admin_id,)
                    ).fetchone()
                success = "Profil ma’lumotlari muvaffaqiyatli yangilandi!"

    return render_panel(
        "settings", "Sozlamalar va Xavfsizlik",
        "Admin parolini yangilash va hisob ma’lumotlarini boshqarish",
        admin_info=admin,
        success=success,
        error=error,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
