import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from config import settings

ALLOWED_FIELDS = {
    "username", "first_name", "step", "consent", "destination", "vacation_type",
    "travel_dates", "tourists", "budget", "client_name", "phone", "status",
    "reminder_sent", "created_at", "updated_at",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the database and add new columns without deleting existing data."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                step TEXT NOT NULL DEFAULT 'new',
                consent INTEGER NOT NULL DEFAULT 0,
                destination TEXT,
                vacation_type TEXT,
                travel_dates TEXT,
                tourists TEXT,
                budget TEXT,
                client_name TEXT,
                phone TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                application_number INTEGER UNIQUE,
                reminder_sent INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # Migrations are additive: the existing applications and sequence are preserved.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(applications)")}
        migrations = {
            "application_number": "ALTER TABLE applications ADD COLUMN application_number INTEGER",
            "cancelled_from": "ALTER TABLE applications ADD COLUMN cancelled_from TEXT",
            "cancellation_notified": (
                "ALTER TABLE applications ADD COLUMN cancellation_notified INTEGER NOT NULL DEFAULT 0"
            ),
        }
        for column, sql in migrations.items():
            if column not in columns:
                conn.execute(sql)

        conn.execute(
            """CREATE TABLE IF NOT EXISTS application_sequence (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                next_number INTEGER NOT NULL
            )"""
        )
        conn.execute(
            "INSERT OR IGNORE INTO application_sequence (id, next_number) VALUES (1, 1)"
        )
        # Ensure the sequence cannot reuse a number already present in the database.
        max_number = conn.execute(
            "SELECT COALESCE(MAX(application_number), 0) FROM applications"
        ).fetchone()[0]
        conn.execute(
            "UPDATE application_sequence SET next_number = MAX(next_number, ?) WHERE id = 1",
            (int(max_number) + 1,),
        )
        conn.commit()


def get_application(user_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def create_or_reset_application(
    user_id: int,
    username: str | None,
    first_name: str | None,
    reset: bool = False,
) -> None:
    now = utc_now()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT user_id FROM applications WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing and not reset:
            conn.execute(
                "UPDATE applications SET username = ?, first_name = ?, updated_at = ? WHERE user_id = ?",
                (username, first_name, now, user_id),
            )
        elif existing:
            conn.execute(
                """UPDATE applications SET
                    username = ?, first_name = ?, step = 'new', consent = 0,
                    destination = NULL, vacation_type = NULL, travel_dates = NULL,
                    tourists = NULL, budget = NULL, client_name = NULL, phone = NULL,
                    status = 'draft', application_number = NULL,
                    cancelled_from = NULL, cancellation_notified = 0,
                    reminder_sent = 0, created_at = ?, updated_at = ?
                    WHERE user_id = ?""",
                (username, first_name, now, now, user_id),
            )
        else:
            conn.execute(
                """INSERT INTO applications
                    (user_id, username, first_name, step, consent, status, reminder_sent, created_at, updated_at)
                    VALUES (?, ?, ?, 'new', 0, 'draft', 0, ?, ?)""",
                (user_id, username, first_name, now, now),
            )
        conn.commit()


def update_application(user_id: int, **fields: Any) -> None:
    unknown = set(fields) - ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"Unsupported application fields: {', '.join(sorted(unknown))}")
    if not fields:
        return
    fields["updated_at"] = utc_now()
    if "step" in fields or any(k not in {"username", "first_name"} for k in fields):
        fields.setdefault("reminder_sent", 0)
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [user_id]
    with _connect() as conn:
        conn.execute(
            f"UPDATE applications SET {assignments} WHERE user_id = ?", values
        )
        conn.commit()


def cancel_application(user_id: int) -> dict[str, Any]:
    """Cancel once and report whether a manager notification is required.

    A previously submitted application is not deleted. Its status becomes
    'cancelled', and the caller is responsible for notifying the manager.
    Repeated calls do not create duplicate notifications after confirmation.
    """
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT status, cancelled_from, cancellation_notified
               FROM applications WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        if row is None:
            conn.commit()
            return {"found": False, "changed": False, "notify_manager": False}

        current_status = str(row["status"])
        if current_status == "cancelled":
            previous_status = row["cancelled_from"] or "cancelled"
            should_notify = previous_status == "submitted" and not bool(row["cancellation_notified"])
            conn.commit()
            return {
                "found": True,
                "changed": False,
                "previous_status": previous_status,
                "notify_manager": should_notify,
            }

        if current_status not in {"draft", "submitted"}:
            conn.commit()
            return {
                "found": True,
                "changed": False,
                "previous_status": current_status,
                "notify_manager": False,
            }

        conn.execute(
            """UPDATE applications
               SET status = 'cancelled', step = 'cancelled', reminder_sent = 1,
                   cancelled_from = ?, cancellation_notified = 0, updated_at = ?
               WHERE user_id = ? AND status = ?""",
            (current_status, utc_now(), user_id, current_status),
        )
        conn.commit()
        return {
            "found": True,
            "changed": True,
            "previous_status": current_status,
            "notify_manager": current_status == "submitted",
        }


def mark_cancellation_notified(user_id: int) -> bool:
    """Record that Telegram accepted the cancellation notice for the manager."""
    with _connect() as conn:
        cursor = conn.execute(
            """UPDATE applications SET cancellation_notified = 1, updated_at = ?
               WHERE user_id = ? AND status = 'cancelled'""",
            (utc_now(), user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def assign_application_number(user_id: int) -> int:
    """Return a stable sequential number, allocating it only once per application."""
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT application_number FROM applications WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Application not found for user_id={user_id}")
        if row["application_number"] is not None:
            return int(row["application_number"])

        sequence = conn.execute(
            "SELECT next_number FROM application_sequence WHERE id = 1"
        ).fetchone()
        number = int(sequence["next_number"])
        conn.execute(
            "UPDATE application_sequence SET next_number = ? WHERE id = 1",
            (number + 1,),
        )
        conn.execute(
            "UPDATE applications SET application_number = ?, updated_at = ? WHERE user_id = ?",
            (number, utc_now(), user_id),
        )
        conn.commit()
        return number


def mark_submitted(user_id: int) -> bool:
    """Mark as submitted only if the user has not cancelled meanwhile."""
    with _connect() as conn:
        cursor = conn.execute(
            """UPDATE applications
               SET status = 'submitted', step = 'submitted', reminder_sent = 1, updated_at = ?
               WHERE user_id = ? AND status = 'draft'""",
            (utc_now(), user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def mark_reminder_sent(user_id: int) -> None:
    update_application(user_id, reminder_sent=1)


def get_due_reminders(minutes: int) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    with _connect() as conn:
        rows = conn.execute(
            """SELECT * FROM applications
               WHERE status = 'draft' AND reminder_sent = 0
                 AND step NOT IN ('new', 'consent', 'cancelled', 'submitted')
                 AND updated_at <= ?""",
            (cutoff,),
        ).fetchall()
        return [dict(row) for row in rows]
