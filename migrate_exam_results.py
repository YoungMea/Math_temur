
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "database.db"


def migrate():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Baza topilmadi: {DB_PATH}. "
            "Yangi bo'sh baza yaratilmadi."
        )

    connection = sqlite3.connect(DB_PATH)

    try:
        connection.execute("BEGIN IMMEDIATE")

        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

        if "students" not in tables:
            raise RuntimeError(
                "students jadvali topilmadi. "
                "Mavjud baza tuzilishini tekshiring."
            )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS exam_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                response_id TEXT NOT NULL UNIQUE,

                student_telegram_id TEXT,
                student_name TEXT NOT NULL,
                class_name TEXT NOT NULL,

                score REAL,
                max_score REAL,

                submitted_at TEXT NOT NULL,
                source_form TEXT NOT NULL,

                match_status TEXT NOT NULL DEFAULT 'needs_review'
                    CHECK (
                        match_status IN (
                            'matched',
                            'needs_review'
                        )
                    ),

                created_at TEXT NOT NULL DEFAULT (
                    datetime('now')
                )
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_exam_results_student
            ON exam_results(student_telegram_id)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_exam_results_class
            ON exam_results(class_name)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_exam_results_submitted
            ON exam_results(submitted_at)
            """
        )

        connection.commit()

        print("Migratsiya muvaffaqiyatli yakunlandi.")
        print("Mavjud students jadvali saqlandi.")
        print("exam_results jadvali tayyor.")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    migrate()
