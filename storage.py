"""Persistent local storage for the Lernraum application."""

from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import re
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

try:  # Support both ``python -m lernraum.app`` and the documented ``python app.py``.
    from .extraction import extract
except ImportError:  # pragma: no cover - exercised when this file is imported as ``storage``
    from extraction import extract


MAX_UPLOAD_BYTES = 40 * 1024 * 1024
COLORS = {"violet", "blue", "green", "orange", "rose"}
UNIT_KINDS = {"lecture", "practical", "other"}
QUESTION_TYPES = {"multiple_choice", "free_text", "image"}
EVALUATION_SOURCES = {"self", "automatic", "ai"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat().replace("+00:00", "Z")


def _iso_precise() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _parse_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _required_string(value: Any, field: str, *, maximum: int = 10000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} darf nicht leer sein.")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"{field} ist zu lang.")
    return value


def _optional_string(value: Any, field: str, *, maximum: int = 1000000) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} muss Text sein.")
    if len(value) > maximum:
        raise ValueError(f"{field} ist zu lang.")
    return value.strip() or None


def _validate_datetime(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} muss ein ISO-Datum sein.")
    try:
        # Lecture dates commonly arrive as YYYY-MM-DD; preserve that calendar date.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            date.fromisoformat(value)
            return value
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} muss ein gültiges ISO-Datum sein.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class Store:
    """SQLite-backed store; every public operation owns its connection."""

    def __init__(self, data_dir: str | Path, seed: bool = True):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.upload_dir = self.data_dir / "materials"
        self.db_path = self.data_dir / "lernraum.sqlite3"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self._initialize(seed)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 15000")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()

    def _initialize(self, seed: bool) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS modules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    code TEXT,
                    description TEXT,
                    color TEXT NOT NULL DEFAULT 'violet' CHECK(color IN ('violet','blue','green','orange','rose')),
                    semester TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS units (
                    id TEXT PRIMARY KEY,
                    module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('lecture','practical','other')),
                    date TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS materials (
                    id TEXT PRIMARY KEY,
                    module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    mime TEXT NOT NULL,
                    size INTEGER NOT NULL CHECK(size >= 0),
                    stored_name TEXT NOT NULL,
                    extraction_status TEXT NOT NULL CHECK(extraction_status IN ('ready','needs_ocr','unsupported','error')),
                    extraction_message TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL DEFAULT '',
                    pages_json TEXT NOT NULL DEFAULT '[]',
                    page_count INTEGER NOT NULL DEFAULT 0 CHECK(page_count >= 0),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS material_units (
                    material_id TEXT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
                    unit_id TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                    PRIMARY KEY(material_id, unit_id)
                );
                CREATE TABLE IF NOT EXISTS questions (
                    id TEXT PRIMARY KEY,
                    module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
                    unit_id TEXT REFERENCES units(id) ON DELETE SET NULL,
                    type TEXT NOT NULL CHECK(type IN ('multiple_choice','free_text','image')),
                    prompt TEXT NOT NULL,
                    options_json TEXT NOT NULL DEFAULT '[]',
                    correct_index INTEGER,
                    answer TEXT NOT NULL DEFAULT '',
                    explanation TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL DEFAULT '',
                    difficulty INTEGER NOT NULL CHECK(difficulty BETWEEN 1 AND 3),
                    source_material_id TEXT REFERENCES materials(id) ON DELETE SET NULL,
                    source_page INTEGER,
                    image_material_id TEXT REFERENCES materials(id) ON DELETE CASCADE,
                    is_ai INTEGER NOT NULL DEFAULT 0 CHECK(is_ai IN (0,1)),
                    reviewed INTEGER NOT NULL DEFAULT 1 CHECK(reviewed IN (0,1)),
                    created_at TEXT NOT NULL,
                    due_at TEXT,
                    mastery INTEGER NOT NULL DEFAULT 0 CHECK(mastery IN (0,50,100)),
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
                    review_stage INTEGER NOT NULL DEFAULT 0 CHECK(review_stage >= 0)
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY,
                    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
                    answer TEXT NOT NULL,
                    rating INTEGER NOT NULL CHECK(rating IN (0,1,2)),
                    correct INTEGER CHECK(correct IN (0,1)),
                    answered_at TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK(duration_seconds >= 0),
                    evaluation_source TEXT NOT NULL CHECK(evaluation_source IN ('self','automatic','ai'))
                );
                CREATE TABLE IF NOT EXISTS answer_submissions (
                    id TEXT PRIMARY KEY,
                    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
                    answer TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK(duration_seconds >= 0),
                    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','reviewed')),
                    rating INTEGER CHECK(rating IN (0,1,2)),
                    feedback TEXT NOT NULL DEFAULT '',
                    reviewed_at TEXT,
                    reviewer TEXT NOT NULL DEFAULT '',
                    attempt_id TEXT UNIQUE REFERENCES attempts(id) ON DELETE CASCADE,
                    CHECK(
                        (status='pending' AND rating IS NULL AND feedback='' AND reviewed_at IS NULL AND reviewer='' AND attempt_id IS NULL)
                        OR
                        (status='reviewed' AND rating IS NOT NULL AND rating IN (0,1,2) AND feedback<>'' AND reviewed_at IS NOT NULL AND reviewer<>'' AND attempt_id IS NOT NULL)
                    )
                );
                CREATE INDEX IF NOT EXISTS idx_units_module ON units(module_id, date, created_at);
                CREATE INDEX IF NOT EXISTS idx_materials_module ON materials(module_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_material_units_unit ON material_units(unit_id);
                CREATE INDEX IF NOT EXISTS idx_questions_module ON questions(module_id, unit_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_questions_due ON questions(due_at);
                CREATE INDEX IF NOT EXISTS idx_attempts_question ON attempts(question_id, answered_at);
                CREATE INDEX IF NOT EXISTS idx_attempts_date ON attempts(answered_at);
                CREATE INDEX IF NOT EXISTS idx_answer_submissions_question_status ON answer_submissions(question_id,status,submitted_at);
                """
            )
            if seed and conn.execute("SELECT 1 FROM app_meta WHERE key='initial_seed_done'").fetchone() is None:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    # Recheck after taking the write lock so two starters cannot seed twice.
                    if conn.execute("SELECT 1 FROM app_meta WHERE key='initial_seed_done'").fetchone() is None:
                        seed_time = _utc_now()
                        for number in (1, 2):
                            conn.execute(
                                "INSERT INTO modules(id,name,color,created_at) VALUES(?,?,?,?)",
                                (str(uuid.uuid4()), f"Modul {number}", "violet" if number == 1 else "blue",
                                 _iso(seed_time + timedelta(seconds=number))),
                            )
                        conn.execute("INSERT INTO app_meta(key,value) VALUES('initial_seed_done','1')")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

    @staticmethod
    def _id(value: Any, field: str = "ID") -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} fehlt.")
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"{field} ist ungültig.") from exc

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def _module(self, conn: sqlite3.Connection, module_id: Any) -> sqlite3.Row:
        module_id = self._id(module_id, "Modul-ID")
        row = conn.execute("SELECT * FROM modules WHERE id=?", (module_id,)).fetchone()
        if row is None:
            raise KeyError(module_id)
        return row

    def _unit(self, conn: sqlite3.Connection, unit_id: Any) -> sqlite3.Row:
        unit_id = self._id(unit_id, "Einheiten-ID")
        row = conn.execute("SELECT * FROM units WHERE id=?", (unit_id,)).fetchone()
        if row is None:
            raise KeyError(unit_id)
        return row

    def _material(self, conn: sqlite3.Connection, material_id: Any) -> sqlite3.Row:
        material_id = self._id(material_id, "Material-ID")
        row = conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
        if row is None:
            raise KeyError(material_id)
        return row

    def _question(self, conn: sqlite3.Connection, question_id: Any) -> sqlite3.Row:
        question_id = self._id(question_id, "Fragen-ID")
        row = conn.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
        if row is None:
            raise KeyError(question_id)
        return row

    def _submission(self, conn: sqlite3.Connection, submission_id: Any) -> sqlite3.Row:
        submission_id = self._id(submission_id, "Antwort-ID")
        row = conn.execute("SELECT * FROM answer_submissions WHERE id=?", (submission_id,)).fetchone()
        if row is None:
            raise KeyError(submission_id)
        return row

    def _material_dict(self, conn: sqlite3.Connection, row: sqlite3.Row, *, detail: bool) -> dict[str, Any]:
        unit_ids = [item[0] for item in conn.execute(
            "SELECT unit_id FROM material_units WHERE material_id=? ORDER BY rowid", (row["id"],)
        ).fetchall()]
        value = {
            "id": row["id"], "module_id": row["module_id"], "unit_ids": unit_ids,
            "name": row["name"], "mime": row["mime"], "size": row["size"],
            "extraction_status": row["extraction_status"], "extraction_message": row["extraction_message"],
            "page_count": row["page_count"], "created_at": row["created_at"],
            "file_url": f"/api/materials/{row['id']}/file",
        }
        if detail:
            value["text"] = row["text"]
            value["pages"] = _parse_json(row["pages_json"], [])
        return value

    def _question_dict(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "module_id": row["module_id"], "unit_id": row["unit_id"],
            "type": row["type"], "prompt": row["prompt"], "options": _parse_json(row["options_json"], []),
            "correct_index": row["correct_index"], "answer": row["answer"],
            "explanation": row["explanation"], "topic": row["topic"], "difficulty": row["difficulty"],
            "source_material_id": row["source_material_id"], "source_page": row["source_page"],
            "image_material_id": row["image_material_id"], "is_ai": bool(row["is_ai"]),
            "reviewed": bool(row["reviewed"]), "created_at": row["created_at"],
            "due_at": row["due_at"], "mastery": row["mastery"], "attempt_count": row["attempt_count"],
        }

    def _attempt_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "question_id": row["question_id"], "answer": row["answer"],
            "rating": row["rating"], "correct": None if row["correct"] is None else bool(row["correct"]),
            "answered_at": row["answered_at"], "duration_seconds": row["duration_seconds"],
            "evaluation_source": row["evaluation_source"],
        }

    @staticmethod
    def _submission_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "question_id": row["question_id"], "answer": row["answer"],
            "submitted_at": row["submitted_at"], "duration_seconds": row["duration_seconds"],
            "status": row["status"], "rating": row["rating"], "feedback": row["feedback"],
            "reviewed_at": row["reviewed_at"], "reviewer": row["reviewer"], "attempt_id": row["attempt_id"],
        }

    def _stats(self, conn: sqlite3.Connection) -> dict[str, Any]:
        now = _utc_now()
        today = now.date()
        cutoff = (today - timedelta(days=6)).isoformat()
        module_rows = conn.execute("SELECT id,name FROM modules ORDER BY created_at,id").fetchall()
        module_stats: list[dict[str, Any]] = []
        totals = {"modules": len(module_rows), "units": 0, "materials": 0, "questions": 0,
                  "attempts": 0, "due_questions": 0, "pending_answers": 0,
                  "mastery_percent": None, "accuracy_percent": None}
        graded_attempts = 0
        correct_attempts = 0
        all_attempts = conn.execute(
            "SELECT a.*,q.module_id,q.topic,q.prompt,q.type,m.name AS module_name "
            "FROM attempts a JOIN questions q ON q.id=a.question_id "
            "JOIN modules m ON m.id=q.module_id ORDER BY a.answered_at DESC,a.rowid DESC"
        ).fetchall()

        for module in module_rows:
            mid = module["id"]
            qstats = conn.execute(
                "SELECT COUNT(*) AS questions, SUM(CASE WHEN (due_at IS NULL OR due_at<=?) "
                "AND NOT EXISTS(SELECT 1 FROM answer_submissions s WHERE s.question_id=questions.id AND s.status='pending') "
                "THEN 1 ELSE 0 END) AS due, "
                "AVG(CASE WHEN attempt_count>0 THEN mastery END) AS mastery "
                "FROM questions WHERE module_id=?", (_iso(now), mid)
            ).fetchone()
            counts = {
                "units": conn.execute("SELECT COUNT(*) FROM units WHERE module_id=?", (mid,)).fetchone()[0],
                "materials": conn.execute("SELECT COUNT(*) FROM materials WHERE module_id=?", (mid,)).fetchone()[0],
                "questions": qstats["questions"] or 0,
                "due_questions": qstats["due"] or 0,
                "pending_answers": conn.execute(
                    "SELECT COUNT(*) FROM answer_submissions s JOIN questions q ON q.id=s.question_id "
                    "WHERE q.module_id=? AND s.status='pending'", (mid,)
                ).fetchone()[0],
                "attempts": conn.execute("SELECT COUNT(*) FROM attempts a JOIN questions q ON q.id=a.question_id WHERE q.module_id=?", (mid,)).fetchone()[0],
            }
            mastery_values = [row[0] for row in conn.execute(
                "SELECT mastery FROM questions WHERE module_id=? AND attempt_count>0", (mid,)
            ).fetchall()]
            mod_attempts = [a for a in all_attempts if a["module_id"] == mid]
            graded = [a for a in mod_attempts if a["correct"] is not None]
            counts["mastery_percent"] = round(sum(mastery_values) / len(mastery_values)) if mastery_values else None
            counts["accuracy_percent"] = round(sum(bool(a["correct"]) for a in graded) * 100 / len(graded)) if graded else None
            module_stats.append({"module_id": mid, "module_name": module["name"], **counts})
            for field in ("units", "materials", "questions", "due_questions", "pending_answers", "attempts"):
                totals[field] += counts[field]
            graded_attempts += len(graded)
            correct_attempts += sum(bool(a["correct"]) for a in graded)

        attempted_questions = conn.execute("SELECT mastery FROM questions WHERE attempt_count>0").fetchall()
        totals["mastery_percent"] = round(sum(row[0] for row in attempted_questions) / len(attempted_questions)) if attempted_questions else None
        totals["accuracy_percent"] = round(correct_attempts * 100 / graded_attempts) if graded_attempts else None

        # Seven UTC calendar days, including today, make charts stable across clients.
        week_rows = conn.execute(
            "SELECT substr(answered_at,1,10) AS day, COUNT(*) AS attempts, "
            "SUM(CASE WHEN rating=2 THEN 1 ELSE 0 END) AS secure "
            "FROM attempts WHERE substr(answered_at,1,10)>=? GROUP BY substr(answered_at,1,10)",
            (cutoff,),
        ).fetchall()
        week_map = {row["day"]: row for row in week_rows}
        week = []
        for offset in range(6, -1, -1):
            day = (today - timedelta(days=offset)).isoformat()
            row = week_map.get(day)
            week.append({"date": day, "attempts": row["attempts"] if row else 0, "secure": row["secure"] or 0 if row else 0})

        active_days = sorted({a["answered_at"][:10] for a in all_attempts}, reverse=True)
        streak = 0
        expected = today
        if active_days and date.fromisoformat(active_days[0]) < today - timedelta(days=1):
            streak = 0
        else:
            active = set(active_days)
            if today.isoformat() not in active:
                expected -= timedelta(days=1)
            while expected.isoformat() in active:
                streak += 1
                expected -= timedelta(days=1)

        topics_raw = conn.execute(
            "SELECT q.module_id, m.name AS module_name, COALESCE(NULLIF(TRIM(q.topic),''),'Ohne Thema') AS topic, "
            "COUNT(*) AS questions, SUM(CASE WHEN q.attempt_count>0 THEN 1 ELSE 0 END) AS attempted, "
            "SUM(CASE WHEN q.mastery=100 AND q.attempt_count>0 THEN 1 ELSE 0 END) AS secure, "
            "AVG(CASE WHEN q.attempt_count>0 THEN q.mastery END) AS mastery "
            "FROM questions q JOIN modules m ON m.id=q.module_id GROUP BY q.module_id,topic "
            "ORDER BY q.module_id,topic"
        ).fetchall()
        topic_attempt_counts = conn.execute(
            "SELECT q.module_id, COALESCE(NULLIF(TRIM(q.topic),''),'Ohne Thema') AS topic, COUNT(*) AS attempts "
            "FROM attempts a JOIN questions q ON q.id=a.question_id GROUP BY q.module_id,topic"
        ).fetchall()
        topic_attempt_map = {(r["module_id"], r["topic"]): r["attempts"] for r in topic_attempt_counts}
        topics = [{
            "module_id": row["module_id"], "module_name": row["module_name"], "topic": row["topic"],
            "questions": row["questions"], "secure": row["secure"] or 0,
            "attempts": topic_attempt_map.get((row["module_id"], row["topic"]), 0),
            "mastery_percent": round(row["mastery"]) if row["mastery"] is not None else None,
        } for row in topics_raw]

        recent_attempts = []
        for row in all_attempts[:10]:
            recent_attempts.append({
                "id": row["id"], "question_id": row["question_id"], "module_id": row["module_id"],
                "module_name": row["module_name"], "prompt": row["prompt"], "topic": row["topic"],
                "type": row["type"], "answer": row["answer"], "rating": row["rating"],
                "correct": None if row["correct"] is None else bool(row["correct"]),
                "answered_at": row["answered_at"], "duration_seconds": row["duration_seconds"],
            })
        seconds = sum(a["duration_seconds"] for a in all_attempts)
        return {
            "totals": totals,
            "modules": module_stats,
            "streak": streak,
            "study_minutes": round(seconds / 60),
            "week": week,
            "topics": topics,
            "recent_attempts": recent_attempts,
        }

    def snapshot(self) -> dict[str, Any]:
        with self._connection() as conn:
            modules = [dict(row) for row in conn.execute("SELECT * FROM modules ORDER BY created_at,id")]
            units = [dict(row) for row in conn.execute("SELECT * FROM units ORDER BY COALESCE(date,''),created_at,id")]
            materials = [self._material_dict(conn, row, detail=False) for row in conn.execute("SELECT * FROM materials ORDER BY created_at,id")]
            questions = [self._question_dict(conn, row) for row in conn.execute("SELECT * FROM questions ORDER BY created_at,id")]
            attempts = [self._attempt_dict(row) for row in conn.execute("SELECT * FROM attempts ORDER BY answered_at,id")]
            answer_submissions = [self._submission_dict(row) for row in conn.execute("SELECT * FROM answer_submissions ORDER BY submitted_at,id")]
            return {"modules": modules, "units": units, "materials": materials,
                    "questions": questions, "attempts": attempts, "answer_submissions": answer_submissions,
                    "stats": self._stats(conn)}

    def stats(self) -> dict[str, Any]:
        with self._connection() as conn:
            return self._stats(conn)

    def get_module(self, module_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            return dict(self._module(conn, module_id))

    def create_module(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Moduldaten müssen ein Objekt sein.")
        name = _required_string(data.get("name"), "Name", maximum=200)
        color = data.get("color", "violet")
        if not isinstance(color, str) or color not in COLORS:
            raise ValueError("Ungültige Modulfarbe.")
        values = {key: _optional_string(data.get(key), key, maximum=5000) for key in ("code", "description", "semester")}
        module_id = str(uuid.uuid4())
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO modules(id,name,code,description,color,semester,created_at) VALUES(?,?,?,?,?,?,?)",
                (module_id, name, values["code"], values["description"], color, values["semester"], _iso()),
            )
            row = self._module(conn, module_id)
            return dict(row)

    def update_module(self, module_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Änderungen müssen ein Objekt sein.")
        with self._transaction() as conn:
            current = dict(self._module(conn, module_id))
            for key in ("name", "code", "description", "color", "semester"):
                if key in data:
                    if key == "name":
                        current[key] = _required_string(data[key], "Name", maximum=200)
                    elif key == "color":
                        if not isinstance(data[key], str) or data[key] not in COLORS:
                            raise ValueError("Ungültige Modulfarbe.")
                        current[key] = data[key]
                    else:
                        current[key] = _optional_string(data[key], key, maximum=5000)
            conn.execute("UPDATE modules SET name=?,code=?,description=?,color=?,semester=? WHERE id=?",
                         (current["name"], current["code"], current["description"], current["color"], current["semester"], current["id"]))
            return dict(self._module(conn, module_id))

    def delete_module(self, module_id: str) -> None:
        with self._transaction() as conn:
            row = self._module(conn, module_id)
            files = [self.upload_dir / item[0] for item in conn.execute("SELECT stored_name FROM materials WHERE module_id=?", (row["id"],))]
            conn.execute("DELETE FROM modules WHERE id=?", (row["id"],))
        for path in files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def create_unit(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Einheitendaten müssen ein Objekt sein.")
        unit_id = str(uuid.uuid4())
        module_id = self._id(data.get("module_id"), "Modul-ID")
        title = _required_string(data.get("title"), "Titel", maximum=300)
        kind = data.get("kind", "other")
        if not isinstance(kind, str) or kind not in UNIT_KINDS:
            raise ValueError("Ungültiger Einheitentyp.")
        date_value = _validate_datetime(data.get("date"), "Datum")
        notes = _optional_string(data.get("notes"), "Notizen")
        with self._transaction() as conn:
            self._module(conn, module_id)
            conn.execute("INSERT INTO units(id,module_id,title,kind,date,notes,created_at) VALUES(?,?,?,?,?,?,?)",
                         (unit_id, module_id, title, kind, date_value, notes, _iso()))
            return dict(self._unit(conn, unit_id))

    def update_unit(self, unit_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Änderungen müssen ein Objekt sein.")
        with self._transaction() as conn:
            current = dict(self._unit(conn, unit_id))
            module_id = current["module_id"]
            if "module_id" in data:
                module_id = self._id(data["module_id"], "Modul-ID")
                self._module(conn, module_id)
                # Moving an entity would invalidate attached materials and questions.
                linked_material = conn.execute(
                    "SELECT 1 FROM material_units mu JOIN materials m ON m.id=mu.material_id WHERE mu.unit_id=? AND m.module_id<>? LIMIT 1",
                    (current["id"], module_id),
                ).fetchone()
                linked_question = conn.execute("SELECT 1 FROM questions WHERE unit_id=? AND module_id<>? LIMIT 1", (current["id"], module_id)).fetchone()
                if linked_material or linked_question:
                    raise ValueError("Die Einheit kann wegen zugeordneter Inhalte nicht in ein anderes Modul verschoben werden.")
            title = _required_string(data.get("title", current["title"]), "Titel", maximum=300)
            kind = data.get("kind", current["kind"])
            if not isinstance(kind, str) or kind not in UNIT_KINDS:
                raise ValueError("Ungültiger Einheitentyp.")
            date_value = _validate_datetime(data.get("date", current["date"]), "Datum")
            notes = _optional_string(data.get("notes", current["notes"]), "Notizen")
            conn.execute("UPDATE units SET module_id=?,title=?,kind=?,date=?,notes=? WHERE id=?",
                         (module_id, title, kind, date_value, notes, current["id"]))
            return dict(self._unit(conn, current["id"]))

    def delete_unit(self, unit_id: str) -> None:
        with self._transaction() as conn:
            row = self._unit(conn, unit_id)
            conn.execute("DELETE FROM units WHERE id=?", (row["id"],))

    def get_material(self, material_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            return self._material_dict(conn, self._material(conn, material_id), detail=True)

    def upload_material(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Materialdaten müssen ein Objekt sein.")
        module_id = self._id(data.get("module_id"), "Modul-ID")
        name = _required_string(data.get("name"), "Dateiname", maximum=500)
        encoded = data.get("content_base64")
        if not isinstance(encoded, str):
            raise ValueError("Dateiinhalt fehlt.")
        if len(encoded) > ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 16:
            raise ValueError("Datei ist größer als 40 MiB.")
        if encoded.startswith("data:") and "," in encoded:
            encoded = encoded.split(",", 1)[1]
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Dateiinhalt ist kein gültiges Base64.") from exc
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("Datei ist größer als 40 MiB.")
        unit_ids = self._validate_unit_ids(data.get("unit_ids", []), module_id)
        mime = data.get("mime")
        if mime is None or mime == "":
            mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if not isinstance(mime, str) or len(mime) > 200 or "/" not in mime:
            raise ValueError("Ungültiger MIME-Typ.")
        mime = mime.lower()
        suffix = Path(name).suffix.lower()
        suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else ""
        material_id = str(uuid.uuid4())
        stored_name = material_id + suffix
        path = self.upload_dir / stored_name
        try:
            path.write_bytes(content)
            extracted = extract(path, name, mime)
            with self._transaction() as conn:
                self._module(conn, module_id)
                self._assert_units(conn, module_id, unit_ids)
                conn.execute(
                    "INSERT INTO materials(id,module_id,name,mime,size,stored_name,extraction_status,extraction_message,text,pages_json,page_count,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (material_id, module_id, name, mime, len(content), stored_name,
                     extracted["extraction_status"], extracted["extraction_message"], extracted["text"],
                     _json(extracted["pages"]), extracted["page_count"], _iso()),
                )
                conn.executemany("INSERT INTO material_units(material_id,unit_id) VALUES(?,?)",
                                 [(material_id, item) for item in unit_ids])
                return self._material_dict(conn, self._material(conn, material_id), detail=False)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def _validate_unit_ids(self, unit_ids: Any, module_id: str) -> list[str]:
        if not isinstance(unit_ids, list):
            raise ValueError("unit_ids muss eine Liste sein.")
        parsed = [self._id(value, "Einheiten-ID") for value in unit_ids]
        if len(parsed) != len(set(parsed)):
            raise ValueError("Eine Einheit wurde mehrfach zugeordnet.")
        return parsed

    def _assert_units(self, conn: sqlite3.Connection, module_id: str, unit_ids: list[str]) -> None:
        for unit_id in unit_ids:
            unit = self._unit(conn, unit_id)
            if unit["module_id"] != module_id:
                raise ValueError("Einheit und Material müssen zum selben Modul gehören.")

    def update_material(self, material_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Änderungen müssen ein Objekt sein.")
        with self._transaction() as conn:
            current = self._material(conn, material_id)
            name = _required_string(data.get("name", current["name"]), "Dateiname", maximum=500)
            if "unit_ids" in data:
                unit_ids = self._validate_unit_ids(data["unit_ids"], current["module_id"])
            else:
                unit_ids = [row[0] for row in conn.execute("SELECT unit_id FROM material_units WHERE material_id=?", (current["id"],))]
            self._assert_units(conn, current["module_id"], unit_ids)
            if "text" in data:
                text = data["text"]
                if not isinstance(text, str) or len(text) > 5000000:
                    raise ValueError("Materialtext muss Text mit höchstens 5 MB sein.")
                conn.execute("UPDATE materials SET name=?,text=?,pages_json=?,page_count=1,extraction_status='ready',extraction_message='Manuell bearbeitet' WHERE id=?",
                             (name, text, _json([{"page": 1, "text": text}]), current["id"]))
                conn.execute(
                    "UPDATE questions SET reviewed=0,source_page=CASE WHEN source_page>1 THEN NULL ELSE source_page END "
                    "WHERE source_material_id=?",
                    (current["id"],),
                )
            else:
                conn.execute("UPDATE materials SET name=? WHERE id=?", (name, current["id"]))
            conn.execute("DELETE FROM material_units WHERE material_id=?", (current["id"],))
            conn.executemany("INSERT INTO material_units(material_id,unit_id) VALUES(?,?)",
                             [(current["id"], item) for item in unit_ids])
            return self._material_dict(conn, self._material(conn, current["id"]), detail=True)

    def delete_material(self, material_id: str) -> None:
        with self._transaction() as conn:
            row = self._material(conn, material_id)
            image_question = conn.execute(
                "SELECT 1 FROM questions WHERE image_material_id=? LIMIT 1", (row["id"],)
            ).fetchone()
            if image_question:
                raise ValueError("Dieses Material wird als Bild in Fragen verwendet. Lösche zuerst die Bildfragen oder ordne ihnen ein anderes Bild zu.")
            path = self.upload_dir / row["stored_name"]
            # Keep questions usable, but require the learner to review them without
            # the source and remove citations that would become invalid.
            conn.execute("UPDATE questions SET reviewed=0,source_page=NULL WHERE source_material_id=?", (row["id"],))
            conn.execute("DELETE FROM materials WHERE id=?", (row["id"],))
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def material_path(self, material_id: str) -> Path:
        with self._connection() as conn:
            row = self._material(conn, material_id)
            path = (self.upload_dir / row["stored_name"]).resolve()
            if path.parent != self.upload_dir.resolve():
                raise ValueError("Ungültiger Materialpfad.")
            if not path.is_file():
                raise KeyError(material_id)
            return path

    def get_question(self, question_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            return self._question_dict(conn, self._question(conn, question_id))

    def _question_payload(self, conn: sqlite3.Connection, data: dict[str, Any], *, default_module_id: str | None = None,
                          default_unit_id: str | None = None, existing: sqlite3.Row | None = None,
                          imported: bool = False) -> dict[str, Any]:
        def value(key: str, default: Any = None) -> Any:
            if key in data:
                return data[key]
            if existing is not None:
                stored_key = "options_json" if key == "options" else key
                if stored_key in existing.keys():
                    return _parse_json(existing[stored_key], []) if key == "options" else existing[stored_key]
            return default

        module_id = self._id(value("module_id", default_module_id), "Modul-ID")
        self._module(conn, module_id)
        unit_val = value("unit_id", default_unit_id)
        unit_id = self._id(unit_val, "Einheiten-ID") if unit_val else None
        if unit_id:
            unit = self._unit(conn, unit_id)
            if unit["module_id"] != module_id:
                raise ValueError("Einheit und Frage müssen zum selben Modul gehören.")

        qtype = value("type", "free_text")
        if not isinstance(qtype, str) or qtype not in QUESTION_TYPES:
            raise ValueError("Ungültiger Fragetyp.")
        prompt = _required_string(value("prompt"), "Frage", maximum=20000)
        options = value("options", [])
        if not isinstance(options, list) or any(not isinstance(item, str) or not item.strip() for item in options):
            raise ValueError("Antwortoptionen müssen eine Liste nichtleerer Texte sein.")
        options = [item.strip() for item in options]
        correct_index = value("correct_index")
        if qtype == "multiple_choice":
            if len(options) < 2:
                raise ValueError("Multiple-Choice-Fragen benötigen mindestens zwei Antwortoptionen.")
            if isinstance(correct_index, bool) or not isinstance(correct_index, int) or not 0 <= correct_index < len(options):
                raise ValueError("Der richtige Antwortindex ist ungültig.")
        else:
            if options or correct_index is not None:
                raise ValueError("Nur Multiple-Choice-Fragen dürfen Antwortoptionen haben.")
        answer = value("answer", "")
        explanation = value("explanation", "")
        topic = value("topic", "")
        for field, field_value in (("Musterantwort", answer), ("Erklärung", explanation), ("Thema", topic)):
            if not isinstance(field_value, str):
                raise ValueError(f"{field} muss Text sein.")
        if len(answer) > 20000 or len(explanation) > 20000 or len(topic) > 300:
            raise ValueError("Frageninhalt ist zu lang.")
        difficulty = value("difficulty", 1)
        if isinstance(difficulty, bool) or not isinstance(difficulty, int) or difficulty not in (1, 2, 3):
            raise ValueError("Schwierigkeit muss 1, 2 oder 3 sein.")
        source_id = value("source_material_id")
        source_page = value("source_page")
        image_id = value("image_material_id")
        source_id = self._id(source_id, "Quellmaterial-ID") if source_id else None
        image_id = self._id(image_id, "Bildmaterial-ID") if image_id else None
        if source_id:
            source = self._material(conn, source_id)
            if source["module_id"] != module_id:
                raise ValueError("Quellmaterial und Frage müssen zum selben Modul gehören.")
            if source_page is not None:
                if isinstance(source_page, bool) or not isinstance(source_page, int) or source_page < 1 or source_page > source["page_count"]:
                    raise ValueError("Die Quellseite liegt außerhalb des Materials.")
        elif source_page is not None:
            raise ValueError("Eine Quellseite benötigt ein Quellmaterial.")
        if image_id:
            image = self._material(conn, image_id)
            if image["module_id"] != module_id:
                raise ValueError("Bild und Frage müssen zum selben Modul gehören.")
            if image["mime"] not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                raise ValueError("Bildfragen unterstützen PNG, JPEG, WebP oder GIF aus dem Materialbereich.")
        if qtype == "image" and not image_id:
            raise ValueError("Bildfragen benötigen ein Bildmaterial.")
        is_ai = value("is_ai", False)
        reviewed = value("reviewed", True)
        if "is_ai" not in data:
            is_ai = bool(is_ai)
        if "reviewed" not in data:
            reviewed = bool(reviewed)
        if not isinstance(is_ai, bool) or not isinstance(reviewed, bool):
            raise ValueError("is_ai und reviewed müssen boolesche Werte sein.")
        if imported:
            # Import means the learner has reviewed and accepted the proposal.
            reviewed = True
        return {
            "module_id": module_id, "unit_id": unit_id, "type": qtype, "prompt": prompt,
            "options": options, "correct_index": correct_index, "answer": answer,
            "explanation": explanation, "topic": topic, "difficulty": difficulty,
            "source_material_id": source_id, "source_page": source_page, "image_material_id": image_id,
            "is_ai": is_ai, "reviewed": reviewed,
        }

    def _insert_question(self, conn: sqlite3.Connection, payload: dict[str, Any], *, question_id: str | None = None) -> dict[str, Any]:
        question_id = question_id or str(uuid.uuid4())
        created = _iso()
        conn.execute(
            "INSERT INTO questions(id,module_id,unit_id,type,prompt,options_json,correct_index,answer,explanation,topic,difficulty,source_material_id,source_page,image_material_id,is_ai,reviewed,created_at,due_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (question_id, payload["module_id"], payload["unit_id"], payload["type"], payload["prompt"], _json(payload["options"]),
             payload["correct_index"], payload["answer"], payload["explanation"], payload["topic"], payload["difficulty"],
             payload["source_material_id"], payload["source_page"], payload["image_material_id"], int(payload["is_ai"]),
             int(payload["reviewed"]), created, created),
        )
        return self._question_dict(conn, self._question(conn, question_id))

    def create_question(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Fragedaten müssen ein Objekt sein.")
        with self._transaction() as conn:
            payload = self._question_payload(conn, data)
            return self._insert_question(conn, payload)

    def update_question(self, question_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Änderungen müssen ein Objekt sein.")
        with self._transaction() as conn:
            current = self._question(conn, question_id)
            payload = self._question_payload(conn, data, existing=current)
            conn.execute(
                "UPDATE questions SET module_id=?,unit_id=?,type=?,prompt=?,options_json=?,correct_index=?,answer=?,explanation=?,topic=?,difficulty=?,source_material_id=?,source_page=?,image_material_id=?,is_ai=?,reviewed=? WHERE id=?",
                (payload["module_id"], payload["unit_id"], payload["type"], payload["prompt"], _json(payload["options"]),
                 payload["correct_index"], payload["answer"], payload["explanation"], payload["topic"], payload["difficulty"],
                 payload["source_material_id"], payload["source_page"], payload["image_material_id"], int(payload["is_ai"]),
                 int(payload["reviewed"]), current["id"]),
            )
            return self._question_dict(conn, self._question(conn, current["id"]))

    def delete_question(self, question_id: str) -> None:
        with self._transaction() as conn:
            row = self._question(conn, question_id)
            conn.execute("DELETE FROM questions WHERE id=?", (row["id"],))

    def import_questions(self, module_id: str, questions: list[dict[str, Any]], unit_id: str | None = None) -> list[dict[str, Any]]:
        if not isinstance(questions, list):
            raise ValueError("questions muss eine Liste sein.")
        if not questions:
            return []
        with self._transaction() as conn:
            module_id = self._id(module_id, "Modul-ID")
            self._module(conn, module_id)
            if unit_id:
                unit_id = self._id(unit_id, "Einheiten-ID")
                unit = self._unit(conn, unit_id)
                if unit["module_id"] != module_id:
                    raise ValueError("Einheit und Fragen müssen zum selben Modul gehören.")
            payloads = []
            for question in questions:
                if not isinstance(question, dict):
                    raise ValueError("Jede Frage muss ein Objekt sein.")
                if question.get("module_id", module_id) != module_id:
                    raise ValueError("Alle importierten Fragen müssen zum angegebenen Modul gehören.")
                payloads.append(self._question_payload(conn, question, default_module_id=module_id,
                                                       default_unit_id=unit_id, imported=True))
            return [self._insert_question(conn, payload) for payload in payloads]

    def _answer_choice(self, answer: Any, options: list[str]) -> tuple[str, int]:
        if isinstance(answer, bool):
            raise ValueError("Ungültige Antwortauswahl.")
        if isinstance(answer, int):
            index = answer
            if index < 0 or index >= len(options):
                raise ValueError("Antwortauswahl liegt außerhalb der Antwortoptionen.")
            return options[index], index
        if isinstance(answer, str):
            if re.fullmatch(r"\d+", answer):
                index = int(answer)
                if 0 <= index < len(options):
                    return options[index], index
            matches = [index for index, option in enumerate(options) if option == answer]
            if len(matches) == 1:
                return answer, matches[0]
        raise ValueError("Antwortauswahl muss ein gültiger Index oder Antworttext sein.")

    def _insert_attempt_and_schedule(
        self,
        conn: sqlite3.Connection,
        question: sqlite3.Row,
        *,
        answer: str,
        rating: int,
        correct: bool | None,
        duration_seconds: int,
        evaluation_source: str,
        answered_at: str | None = None,
        schedule_at: datetime | None = None,
        update_learning_state: bool = True,
    ) -> dict[str, Any]:
        attempt_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO attempts(id,question_id,answer,rating,correct,answered_at,duration_seconds,evaluation_source) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (attempt_id, question["id"], answer, rating, None if correct is None else int(correct),
             answered_at or _iso(), duration_seconds, evaluation_source),
        )
        if update_learning_state:
            schedule_at = schedule_at or _utc_now()
            if rating == 0:
                mastery = 0
                stage = 0
                due = _iso(schedule_at + timedelta(minutes=10))
            elif rating == 1:
                mastery = 50
                stage = max(1, question["review_stage"])
                due = _iso(schedule_at + timedelta(days=1))
            else:
                mastery = 100
                stage = question["review_stage"] + 1
                intervals = (3, 7, 14, 30, 60)
                due = _iso(schedule_at + timedelta(days=intervals[min(stage - 1, len(intervals) - 1)]))
            conn.execute(
                "UPDATE questions SET attempt_count=attempt_count+1,mastery=?,review_stage=?,due_at=? WHERE id=?",
                (mastery, stage, due, question["id"]),
            )
        else:
            # The answer is still a graded attempt, but an older submission must
            # never replace the current mastery or due date from a later answer.
            conn.execute("UPDATE questions SET attempt_count=attempt_count+1 WHERE id=?", (question["id"],))
        return self._attempt_dict(conn.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone())

    def record_attempt(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Versuchsdaten müssen ein Objekt sein.")
        question_id = self._id(data.get("question_id"), "Fragen-ID")
        raw_rating = data.get("rating")
        if isinstance(raw_rating, bool) or not isinstance(raw_rating, int) or raw_rating not in (0, 1, 2):
            raise ValueError("Bewertung muss 0, 1 oder 2 sein.")
        duration = data.get("duration_seconds", 0)
        if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0 or duration > 7 * 24 * 3600:
            raise ValueError("Dauer muss eine gültige Anzahl Sekunden sein.")
        source = data.get("evaluation_source", "self")
        if not isinstance(source, str) or source not in EVALUATION_SOURCES:
            raise ValueError("Ungültige Bewertungsquelle.")
        with self._transaction() as conn:
            question = self._question(conn, question_id)
            if not question["reviewed"]:
                raise ValueError("Diese KI-Frage ist noch nicht geprüft. Prüfe und übernimm sie zuerst, bevor du sie beantwortest.")
            raw_answer = data.get("answer")
            if question["type"] == "multiple_choice":
                options = _parse_json(question["options_json"], [])
                stored_answer, chosen = self._answer_choice(raw_answer, options)
                correct = chosen == question["correct_index"]
                rating = 2 if correct else 0
                source = "automatic"
            else:
                if not isinstance(raw_answer, str) or len(raw_answer) > 20000:
                    raise ValueError("Antwort muss Text mit höchstens 20.000 Zeichen sein.")
                stored_answer = raw_answer
                correct = None
                rating = raw_rating
            return self._insert_attempt_and_schedule(
                conn, question, answer=stored_answer, rating=rating, correct=correct,
                duration_seconds=duration, evaluation_source=source, answered_at=_iso_precise(),
            )

    def submit_answer(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Antwortdaten müssen ein Objekt sein.")
        question_id = self._id(data.get("question_id"), "Fragen-ID")
        answer = data.get("answer")
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 20000:
            raise ValueError("Antwort muss nichtleerer Text mit höchstens 20.000 Zeichen sein.")
        duration = data.get("duration_seconds", 0)
        if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0 or duration > 7 * 24 * 3600:
            raise ValueError("Dauer muss eine gültige Anzahl Sekunden sein.")
        with self._transaction() as conn:
            question = self._question(conn, question_id)
            if not question["reviewed"]:
                raise ValueError("Diese KI-Frage ist noch nicht geprüft. Prüfe und übernimm sie zuerst, bevor du sie beantwortest.")
            if question["type"] not in {"free_text", "image"}:
                raise ValueError("Antworten zur späteren Prüfung sind nur für Freitext- und Bildfragen verfügbar.")
            submission_id = str(uuid.uuid4())
            submitted_at = _iso_precise()
            conn.execute(
                "INSERT INTO answer_submissions(id,question_id,answer,submitted_at,duration_seconds,status,rating,feedback,reviewed_at,reviewer,attempt_id) "
                "VALUES(?,?,?,?,?,'pending',NULL,'',NULL,'',NULL)",
                (submission_id, question_id, answer, submitted_at, duration),
            )
            return self._submission_dict(self._submission(conn, submission_id))

    def list_answers(
        self,
        module_id: str | None = None,
        unit_id: str | None = None,
        status: str = "pending",
    ) -> list[dict[str, Any]]:
        if not isinstance(status, str) or status not in {"pending", "reviewed", "all"}:
            raise ValueError("Status muss pending, reviewed oder all sein.")
        clauses: list[str] = []
        params: list[Any] = []
        with self._connection() as conn:
            if module_id is not None:
                module = self._module(conn, module_id)
                clauses.append("q.module_id=?")
                params.append(module["id"])
            if unit_id is not None:
                unit = self._unit(conn, unit_id)
                if module_id is not None and unit["module_id"] != self._id(module_id, "Modul-ID"):
                    raise ValueError("Einheit gehört zu einem anderen Modul.")
                clauses.append("q.unit_id=?")
                params.append(unit["id"])
            if status != "all":
                clauses.append("s.status=?")
                params.append(status)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = conn.execute(
                "SELECT s.* FROM answer_submissions s JOIN questions q ON q.id=s.question_id "
                f"{where} ORDER BY s.submitted_at,s.id",
                params,
            ).fetchall()
            return [self._submission_dict(row) for row in rows]

    def _submission_is_newest_attempt(self, conn: sqlite3.Connection, submission: sqlite3.Row) -> bool:
        submitted_at = _parse_utc_iso(submission["submitted_at"])
        current_order = conn.execute(
            "SELECT rowid FROM answer_submissions WHERE id=?", (submission["id"],)
        ).fetchone()[0]
        existing_attempts = conn.execute(
            "SELECT a.answered_at,s.rowid AS submission_order FROM attempts a "
            "LEFT JOIN answer_submissions s ON s.attempt_id=a.id WHERE a.question_id=?",
            (submission["question_id"],),
        ).fetchall()
        for attempt in existing_attempts:
            attempted_at = _parse_utc_iso(attempt["answered_at"])
            if attempted_at > submitted_at:
                return False
            if attempted_at == submitted_at and (
                attempt["submission_order"] is None or attempt["submission_order"] > current_order
            ):
                # If a normal attempt has the exact same timestamp, treat it as
                # newer because its event order cannot be compared across tables.
                return False
        return True

    def get_answer(self, submission_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            submission = self._submission(conn, submission_id)
            question_id = submission["question_id"]
            question = self._question(conn, question_id)
            source = self._material(conn, question["source_material_id"]) if question["source_material_id"] else None
            image = self._material(conn, question["image_material_id"]) if question["image_material_id"] else None
            unit = self._unit(conn, question["unit_id"]) if question["unit_id"] else None
            module = self._module(conn, question["module_id"])
            return {
                **self._submission_dict(submission),
                "question": self._question_dict(conn, question),
                "module": dict(module),
                "unit": dict(unit) if unit else None,
                "source_material": self._material_dict(conn, source, detail=True) if source else None,
                "image_material": self._material_dict(conn, image, detail=False) if image else None,
            }

    def _attempt_is_newest(self, conn: sqlite3.Connection, attempt: sqlite3.Row) -> bool:
        """Whether this answer is the latest attempt, with row order breaking timestamp ties."""
        current_at = _parse_utc_iso(attempt["answered_at"])
        current_rowid = conn.execute("SELECT rowid FROM attempts WHERE id=?", (attempt["id"],)).fetchone()[0]
        later = conn.execute(
            "SELECT id,answered_at,rowid FROM attempts WHERE question_id=?",
            (attempt["question_id"],),
        ).fetchall()
        for candidate in later:
            if candidate["id"] == attempt["id"]:
                continue
            candidate_at = _parse_utc_iso(candidate["answered_at"])
            if candidate_at > current_at or (candidate_at == current_at and candidate["rowid"] > current_rowid):
                return False
        return True

    def _recompute_question_schedule(
        self,
        conn: sqlite3.Connection,
        question_id: str,
        reviewed_at: datetime,
    ) -> None:
        attempts = conn.execute(
            "SELECT id,rating,answered_at,rowid FROM attempts WHERE question_id=?",
            (question_id,),
        ).fetchall()
        attempts = sorted(
            attempts,
            key=lambda row: (_parse_utc_iso(row["answered_at"]), row["rowid"]),
        )
        stage = 0
        for attempt in attempts:
            if attempt["rating"] == 0:
                stage = 0
            elif attempt["rating"] == 1:
                stage = max(1, stage)
            else:
                stage += 1

        latest_rating = attempts[-1]["rating"]
        if latest_rating == 0:
            due = reviewed_at + timedelta(minutes=10)
        elif latest_rating == 1:
            stage = max(1, stage)
            due = reviewed_at + timedelta(days=1)
        else:
            intervals = (3, 7, 14, 30, 60)
            due = reviewed_at + timedelta(days=intervals[min(stage - 1, len(intervals) - 1)])
        conn.execute(
            "UPDATE questions SET mastery=?,review_stage=?,due_at=? WHERE id=?",
            (latest_rating * 50, stage, _iso(due), question_id),
        )

    def review_attempt(self, attempt_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Attach a chat review to an existing self-rated answer without adding an attempt."""
        if not isinstance(data, dict):
            raise ValueError("Prüfdaten müssen ein Objekt sein.")
        rating = data.get("rating")
        if isinstance(rating, bool) or not isinstance(rating, int) or rating not in (0, 1, 2):
            raise ValueError("Bewertung muss 0, 1 oder 2 sein.")
        feedback = _required_string(data.get("feedback"), "Feedback", maximum=20000)
        reviewer = _required_string(data.get("reviewer", "ChatGPT (im Chat)"), "Prüfer", maximum=300)
        attempt_id = self._id(attempt_id, "Versuchs-ID")
        with self._transaction() as conn:
            attempt = conn.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
            if attempt is None:
                raise KeyError(attempt_id)
            if conn.execute("SELECT 1 FROM answer_submissions WHERE attempt_id=?", (attempt_id,)).fetchone():
                raise ValueError("Diese Antwort wurde bereits geprüft und kann nicht ein zweites Mal bewertet werden.")
            question = self._question(conn, attempt["question_id"])
            if attempt["evaluation_source"] != "self":
                raise ValueError("Nur bisher selbst bewertete Freitext- oder Bildantworten können hier geprüft werden.")
            if question["type"] not in {"free_text", "image"}:
                raise ValueError("Die gespeicherte Antwort gehört nicht zu einer Freitext- oder Bildfrage.")
            if not question["reviewed"]:
                raise ValueError("Die Frage muss nach einer Änderung zuerst erneut geprüft werden.")

            reviewed_at_value = _utc_now()
            reviewed_at = _iso(reviewed_at_value)
            update_learning_state = self._attempt_is_newest(conn, attempt)
            updated = conn.execute(
                "UPDATE attempts SET rating=?,evaluation_source='ai' WHERE id=? AND evaluation_source='self'",
                (rating, attempt_id),
            )
            if updated.rowcount != 1:
                raise ValueError("Diese Antwort wurde zwischenzeitlich bereits geprüft.")
            submission_id = str(uuid.uuid4())
            while conn.execute("SELECT 1 FROM answer_submissions WHERE id=?", (submission_id,)).fetchone():
                submission_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO answer_submissions(id,question_id,answer,submitted_at,duration_seconds,status,rating,feedback,reviewed_at,reviewer,attempt_id) "
                "VALUES(?,?,?,?,?,'reviewed',?,?,?,?,?)",
                (submission_id, question["id"], attempt["answer"], attempt["answered_at"],
                 attempt["duration_seconds"], rating, feedback, reviewed_at, reviewer, attempt_id),
            )
            if update_learning_state:
                self._recompute_question_schedule(conn, question["id"], reviewed_at_value)
            return self._submission_dict(self._submission(conn, submission_id))

    def review_answer(self, submission_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("Prüfdaten müssen ein Objekt sein.")
        rating = data.get("rating")
        if isinstance(rating, bool) or not isinstance(rating, int) or rating not in (0, 1, 2):
            raise ValueError("Bewertung muss 0, 1 oder 2 sein.")
        feedback = _required_string(data.get("feedback"), "Feedback", maximum=20000)
        reviewer = _required_string(data.get("reviewer", "ChatGPT (im Chat)"), "Prüfer", maximum=300)
        with self._transaction() as conn:
            submission = self._submission(conn, submission_id)
            if submission["status"] != "pending":
                raise ValueError("Diese Antwort wurde bereits geprüft und kann nicht ein zweites Mal bewertet werden.")
            question = self._question(conn, submission["question_id"])
            if not question["reviewed"]:
                raise ValueError("Die Frage muss nach einer Änderung zuerst erneut geprüft werden.")
            if question["type"] not in {"free_text", "image"}:
                raise ValueError("Die eingereichte Antwort gehört nicht zu einer Freitext- oder Bildfrage.")
            reviewed_at_value = _utc_now()
            reviewed_at = _iso(reviewed_at_value)
            update_learning_state = self._submission_is_newest_attempt(conn, submission)
            attempt = self._insert_attempt_and_schedule(
                conn, question, answer=submission["answer"], rating=rating, correct=None,
                duration_seconds=submission["duration_seconds"], evaluation_source="ai",
                answered_at=submission["submitted_at"], schedule_at=reviewed_at_value,
                update_learning_state=update_learning_state,
            )
            updated = conn.execute(
                "UPDATE answer_submissions SET status='reviewed',rating=?,feedback=?,reviewed_at=?,reviewer=?,attempt_id=? "
                "WHERE id=? AND status='pending'",
                (rating, feedback, reviewed_at, reviewer, attempt["id"], submission["id"]),
            )
            if updated.rowcount != 1:
                raise ValueError("Diese Antwort wurde zwischenzeitlich bereits geprüft.")
            return self._submission_dict(self._submission(conn, submission["id"]))

    def context(self, module_id: str, unit_id: str | None = None) -> dict[str, Any]:
        with self._connection() as conn:
            module = dict(self._module(conn, module_id))
            units = conn.execute("SELECT * FROM units WHERE module_id=? ORDER BY COALESCE(date,''),created_at,id", (module["id"],)).fetchall()
            if unit_id:
                unit_id = self._id(unit_id, "Einheiten-ID")
                unit = self._unit(conn, unit_id)
                if unit["module_id"] != module["id"]:
                    raise ValueError("Einheit gehört zu einem anderen Modul.")
                units = [unit]
                material_rows = conn.execute(
                    "SELECT DISTINCT m.* FROM materials m LEFT JOIN material_units mu ON mu.material_id=m.id "
                    "WHERE m.module_id=? AND (mu.unit_id=? OR NOT EXISTS(SELECT 1 FROM material_units x WHERE x.material_id=m.id)) ORDER BY m.created_at,m.id",
                    (module["id"], unit_id),
                ).fetchall()
                question_rows = conn.execute("SELECT * FROM questions WHERE module_id=? AND unit_id=? ORDER BY created_at,id", (module["id"], unit_id)).fetchall()
                attempt_rows = conn.execute(
                    "SELECT a.* FROM attempts a JOIN questions q ON q.id=a.question_id "
                    "WHERE q.module_id=? AND q.unit_id=? ORDER BY a.answered_at,a.id",
                    (module["id"], unit_id),
                ).fetchall()
                submission_rows = conn.execute(
                    "SELECT s.* FROM answer_submissions s JOIN questions q ON q.id=s.question_id "
                    "WHERE q.module_id=? AND q.unit_id=? ORDER BY s.submitted_at,s.id",
                    (module["id"], unit_id),
                ).fetchall()
            else:
                material_rows = conn.execute("SELECT * FROM materials WHERE module_id=? ORDER BY created_at,id", (module["id"],)).fetchall()
                question_rows = conn.execute("SELECT * FROM questions WHERE module_id=? ORDER BY created_at,id", (module["id"],)).fetchall()
                attempt_rows = conn.execute(
                    "SELECT a.* FROM attempts a JOIN questions q ON q.id=a.question_id "
                    "WHERE q.module_id=? ORDER BY a.answered_at,a.id",
                    (module["id"],),
                ).fetchall()
                submission_rows = conn.execute(
                    "SELECT s.* FROM answer_submissions s JOIN questions q ON q.id=s.question_id "
                    "WHERE q.module_id=? ORDER BY s.submitted_at,s.id",
                    (module["id"],),
                ).fetchall()
            return {
                "module": module,
                "units": [dict(row) for row in units],
                "materials": [self._material_dict(conn, row, detail=True) for row in material_rows],
                "questions": [self._question_dict(conn, row) for row in question_rows],
                "attempts": [self._attempt_dict(row) for row in attempt_rows],
                "answer_submissions": [self._submission_dict(row) for row in submission_rows],
                "stats": next((row for row in self._stats(conn)["modules"] if row["module_id"] == module["id"]), None),
                "instructions": "Nutze ausschließlich die bereitgestellten Kursmaterialien als Quelle. Erfinde keine Fakten. "
                                "Verweise bei fachlichen Aussagen auf Materialname und Seite, wenn eine Seitenangabe vorliegt. "
                                "Behandle Aufgaben und Lösungsvorschläge als vertrauliche Lerninhalte und kennzeichne Unsicherheit.",
            }

    def backup(self) -> bytes:
        """Return a ZIP archive containing a consistent SQLite backup and originals."""
        with tempfile.TemporaryDirectory(prefix=".lernraum-backup-", dir=self.data_dir) as temp_dir:
            temp_path = Path(temp_dir)
            db_copy = temp_path / "lernraum.sqlite3"
            archive_path = temp_path / "backup.zip"
            with self._connection() as source:
                source.execute("BEGIN IMMEDIATE")
                try:
                    # ``serialize`` captures this transaction's exact snapshot,
                    # including a consistent view while the write lock protects files.
                    db_copy.write_bytes(source.serialize())
                    rows = source.execute("SELECT id,stored_name FROM materials ORDER BY id").fetchall()
                    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                        archive.write(db_copy, "lernraum.sqlite3")
                        for row in rows:
                            path = self.upload_dir / row["stored_name"]
                            if path.is_file():
                                archive.write(path, f"materials/{row['stored_name']}")
                    source.commit()
                except Exception:
                    source.rollback()
                    raise
            return archive_path.read_bytes()
