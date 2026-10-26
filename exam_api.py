
import os
import re
import sqlite3
import secrets
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from flask import Blueprint, request, jsonify


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"

load_dotenv(BASE_DIR / ".env")

exam_api = Blueprint("exam_api", __name__, url_prefix="/api")


def normalize_name(value):
    """Bo'sh joylarni tartibga keltirib, ismni solishtirishga tayyorlaydi."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def parse_number(value, field_name):
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        raise ValueError(f"{field_name} noto'g'ri.")

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} son bo'lishi kerak.")

    if number < 0:
        raise ValueError(f"{field_name} manfiy bo'lishi mumkin emas.")

    return number


@exam_api.post("/exam-results")
def receive_exam_result():
    expected_key = os.getenv("MATH_TEMUR_WEBHOOK_SECRET", "")
    supplied_key = request.headers.get("X-API-Key", "")

    if not expected_key or not secrets.compare_digest(
        supplied_key, expected_key
    ):
        return jsonify({"error": "Ruxsat berilmadi."}), 401

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "JSON ma'lumot yuboring."}), 400

    response_id = str(data.get("response_id", "")).strip()
    student_name = str(data.get("student_name", "")).strip()
    class_name = str(data.get("class_name", "")).strip()
    submitted_at = str(data.get("submitted_at", "")).strip()
    source_form = str(data.get("source_form", "")).strip()

    if not all([
        response_id,
        student_name,
        class_name,
        submitted_at,
        source_form,
    ]):
        return jsonify({
            "error": (
                "response_id, student_name, class_name, "
                "submitted_at va source_form majburiy."
            )
        }), 400

    # Faqat oldindan ruxsat berilgan sinflar qabul qilinadi.
    if class_name not in {"5.1", "6.4"}:
        return jsonify({"error": "Noma'lum sinf."}), 400

    try:
        score = parse_number(data.get("score"), "score")
        max_score = parse_number(data.get("max_score"), "max_score")
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    if score is not None and max_score is not None and score > max_score:
        return jsonify({
            "error": "Ball maksimal balldan katta bo'lishi mumkin emas."
        }), 400

    try:
        # Sana kelajakdagi Google Apps Script'dan ISO formatda yuboriladi.
        datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
    except ValueError:
        return jsonify({
            "error": "submitted_at ISO sana-vaqt formatida bo'lishi kerak."
        }), 400

    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row

    try:
        # Ism va sinf bo'yicha nomzodlarni olamiz.
        students = connection.execute(
            """
            SELECT telegram_id, full_name, class_name
            FROM students
            WHERE TRIM(COALESCE(class_name, '')) = ?
            """,
            (class_name,),
        ).fetchall()

        wanted_name = normalize_name(student_name)

        matches = [
            student for student in students
            if normalize_name(student["full_name"] or "") == wanted_name
        ]

        matched_student_id = None
        match_status = "needs_review"

        # Faqat bitta aniq moslik bo'lsa, avtomatik bog'laymiz.
        if len(matches) == 1:
            matched_student_id = str(matches[0]["telegram_id"])
            match_status = "matched"

        with connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO exam_results (
                    response_id,
                    student_telegram_id,
                    student_name,
                    class_name,
                    score,
                    max_score,
                    submitted_at,
                    source_form,
                    match_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    response_id,
                    matched_student_id,
                    student_name,
                    class_name,
                    score,
                    max_score,
                    submitted_at,
                    source_form,
                    match_status,
                ),
            )

        if cursor.rowcount == 0:
            return jsonify({
                "status": "duplicate",
                "message": "Bu javob avval qabul qilingan."
            }), 200

        return jsonify({
            "status": match_status,
            "message": (
                "Natija saqlandi."
                if match_status == "matched"
                else "Natija saqlandi, o'quvchini tekshirish kerak."
            ),
        }), 201

    except sqlite3.Error:
        return jsonify({
            "error": "Baza bilan ishlashda xatolik yuz berdi."
        }), 500

    finally:
        connection.close()
