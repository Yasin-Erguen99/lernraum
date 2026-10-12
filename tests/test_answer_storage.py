from __future__ import annotations

import base64
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from lernraum.storage import Store


class AnswerSubmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        modules = self.store.snapshot()["modules"]
        self.module, self.other_module = modules

    def question(self, *, module_id: str | None = None, unit_id: str | None = None,
                 qtype: str = "free_text", **extra) -> dict:
        return self.store.create_question({
            "module_id": module_id or self.module["id"],
            "unit_id": unit_id,
            "type": qtype,
            "prompt": f"Frage {qtype}",
            **extra,
        })

    def upload_text(self, module_id: str, name: str = "quelle.txt") -> dict:
        return self.store.upload_material({
            "module_id": module_id,
            "unit_ids": [],
            "name": name,
            "mime": "text/plain",
            "content_base64": base64.b64encode("Quelle mit Umlaut: Grüße".encode("utf-8")).decode("ascii"),
        })

    def upload_image(self, module_id: str) -> dict:
        # A small valid PNG; the storage layer preserves originals without OCR.
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/kWQAAAAASUVORK5CYII="
        )
        return self.store.upload_material({
            "module_id": module_id, "unit_ids": [], "name": "bild.png", "mime": "image/png",
            "content_base64": base64.b64encode(png).decode("ascii"),
        })

    def test_legacy_database_migration_preserves_existing_attempts(self) -> None:
        question = self.question()
        attempt = self.store.record_attempt({
            "question_id": question["id"], "answer": "bereits bewertet", "rating": 2, "duration_seconds": 37,
        })
        previous_question = self.store.get_question(question["id"])
        conn = sqlite3.connect(self.store.db_path)
        try:
            conn.execute("DROP TABLE answer_submissions")
            conn.commit()
        finally:
            conn.close()

        migrated = Store(self.temp.name, seed=False)
        state = migrated.snapshot()
        self.assertEqual([item["id"] for item in state["attempts"]], [attempt["id"]])
        self.assertEqual(migrated.get_question(question["id"])["attempt_count"], previous_question["attempt_count"])
        self.assertEqual(migrated.list_answers(), [])
        self.assertEqual(
            migrated.submit_answer({"question_id": question["id"], "answer": "nach Migration"})["status"],
            "pending",
        )

    def test_pending_answer_is_unrated_does_not_create_attempt_or_schedule(self) -> None:
        question = self.question()
        before = self.store.get_question(question["id"])
        submission = self.store.submit_answer({
            "question_id": question["id"], "answer": "  Meine ausführliche Antwort  ", "duration_seconds": 53,
        })
        self.assertEqual(submission["status"], "pending")
        self.assertIsNone(submission["rating"])
        self.assertEqual(submission["feedback"], "")
        self.assertIsNone(submission["reviewed_at"])
        self.assertEqual(submission["reviewer"], "")
        self.assertIsNone(submission["attempt_id"])
        self.assertEqual(submission["answer"], "  Meine ausführliche Antwort  ")
        self.assertEqual(self.store.snapshot()["attempts"], [])
        after = self.store.get_question(question["id"])
        for field in ("attempt_count", "mastery", "due_at"):
            self.assertEqual(after[field], before[field])
        stats = self.store.stats()
        self.assertEqual(stats["totals"]["pending_answers"], 1)
        self.assertEqual(stats["modules"][0]["pending_answers"], 1)
        self.assertEqual(stats["totals"]["due_questions"], 0)

    def test_submit_validates_answer_question_kind_review_state_and_duration(self) -> None:
        mc = self.question(qtype="multiple_choice", options=["A", "B"], correct_index=0)
        unreviewed = self.question(reviewed=False)
        for payload in (
            {"question_id": mc["id"], "answer": "A"},
            {"question_id": unreviewed["id"], "answer": "Antwort"},
            {"question_id": self.question()["id"], "answer": "  "},
            {"question_id": self.question()["id"], "answer": "x" * 20001},
            {"question_id": self.question()["id"], "answer": "x", "duration_seconds": -1},
            {"question_id": self.question()["id"], "answer": "x", "duration_seconds": 604801},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.store.submit_answer(payload)

        image_material = self.upload_image(self.module["id"])
        image_question = self.question(qtype="image", image_material_id=image_material["id"])
        image_submission = self.store.submit_answer({"question_id": image_question["id"], "answer": "Das ist ein Kreis."})
        self.assertEqual(image_submission["status"], "pending")

    def test_review_creates_one_ai_attempt_and_cannot_be_applied_twice(self) -> None:
        question = self.question()
        submission = self.store.submit_answer({
            "question_id": question["id"], "answer": "Meine Antwort", "duration_seconds": 88,
        })
        reviewed = self.store.review_answer(submission["id"], {"rating": 1, "feedback": "Gute Idee, nenne noch den Zusammenhang."})
        self.assertEqual(reviewed["status"], "reviewed")
        self.assertEqual(reviewed["rating"], 1)
        self.assertEqual(reviewed["reviewer"], "ChatGPT (im Chat)")
        self.assertTrue(reviewed["reviewed_at"])
        self.assertTrue(reviewed["attempt_id"])
        self.assertEqual(reviewed["feedback"], "Gute Idee, nenne noch den Zusammenhang.")
        attempts = self.store.snapshot()["attempts"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["id"], reviewed["attempt_id"])
        self.assertEqual(attempts[0]["answer"], submission["answer"])
        self.assertEqual(attempts[0]["answered_at"], submission["submitted_at"])
        self.assertEqual(attempts[0]["duration_seconds"], 88)
        self.assertEqual(attempts[0]["evaluation_source"], "ai")
        self.assertIsNone(attempts[0]["correct"])
        self.assertEqual(self.store.get_question(question["id"])["attempt_count"], 1)
        self.assertEqual(self.store.get_question(question["id"])["mastery"], 50)
        due = datetime.fromisoformat(self.store.get_question(question["id"])["due_at"].replace("Z", "+00:00"))
        reviewed_at = datetime.fromisoformat(reviewed["reviewed_at"].replace("Z", "+00:00"))
        self.assertEqual((due - reviewed_at).days, 1)

        with self.assertRaisesRegex(ValueError, "bereits geprüft"):
            self.store.review_answer(submission["id"], {"rating": 0, "feedback": "Nochmals"})
        self.assertEqual(len(self.store.snapshot()["attempts"]), 1)
        self.assertEqual(self.store.get_question(question["id"])["attempt_count"], 1)

    def test_old_submission_review_does_not_replace_state_from_newer_answer(self) -> None:
        question = self.question()
        earlier = self.store.submit_answer({"question_id": question["id"], "answer": "ältere Antwort"})
        later = self.store.submit_answer({"question_id": question["id"], "answer": "neuere Antwort"})
        self.assertLess(earlier["submitted_at"], later["submitted_at"])

        newer_review = self.store.review_answer(later["id"], {"rating": 2, "feedback": "Sehr gut."})
        state_after_newer = self.store.get_question(question["id"])
        older_review = self.store.review_answer(earlier["id"], {"rating": 0, "feedback": "Die spätere Antwort war besser."})
        state_after_older = self.store.get_question(question["id"])
        self.assertEqual(older_review["status"], "reviewed")
        self.assertEqual(older_review["attempt_id"], next(a["id"] for a in self.store.snapshot()["attempts"] if a["answer"] == "ältere Antwort"))
        self.assertEqual(state_after_older["attempt_count"], 2)
        for field in ("mastery", "due_at"):
            self.assertEqual(state_after_older[field], state_after_newer[field])
        conn = sqlite3.connect(self.store.db_path)
        try:
            stages = conn.execute("SELECT review_stage FROM questions WHERE id=?", (question["id"],)).fetchone()
        finally:
            conn.close()
        self.assertEqual(stages[0], 1)
        attempts = {attempt["id"]: attempt for attempt in self.store.snapshot()["attempts"]}
        self.assertEqual(attempts[newer_review["attempt_id"]]["answered_at"], later["submitted_at"])
        self.assertEqual(attempts[older_review["attempt_id"]]["answered_at"], earlier["submitted_at"])

    def test_review_rechecks_current_question_type_without_partial_attempt(self) -> None:
        question = self.question()
        submission = self.store.submit_answer({"question_id": question["id"], "answer": "Antwort"})
        self.store.update_question(question["id"], {
            "type": "multiple_choice", "options": ["A", "B"], "correct_index": 0,
        })
        with self.assertRaisesRegex(ValueError, "Freitext- oder Bildfrage"):
            self.store.review_answer(submission["id"], {"rating": 2, "feedback": "Gut."})
        self.assertEqual(self.store.list_answers(status="pending")[0]["id"], submission["id"])
        self.assertEqual(self.store.snapshot()["attempts"], [])
        self.assertEqual(self.store.get_question(question["id"])["attempt_count"], 0)

    def test_answer_context_and_detail_include_only_scoped_submissions_and_sources(self) -> None:
        unit_one = self.store.create_unit({"module_id": self.module["id"], "title": "VL 1", "kind": "lecture"})
        unit_two = self.store.create_unit({"module_id": self.module["id"], "title": "VL 2", "kind": "lecture"})
        other_unit = self.store.create_unit({"module_id": self.other_module["id"], "title": "Fremd", "kind": "other"})
        source = self.upload_text(self.module["id"])
        image = self.upload_image(self.module["id"])
        first_question = self.question(
            unit_id=unit_one["id"], qtype="image", image_material_id=image["id"],
            source_material_id=source["id"], source_page=1,
        )
        second_question = self.question(unit_id=unit_two["id"])
        foreign_question = self.question(module_id=self.other_module["id"], unit_id=other_unit["id"])
        first = self.store.submit_answer({"question_id": first_question["id"], "answer": "Antwort eins"})
        second = self.store.submit_answer({"question_id": second_question["id"], "answer": "Antwort zwei"})
        foreign = self.store.submit_answer({"question_id": foreign_question["id"], "answer": "Fremde Antwort"})

        detail = self.store.get_answer(first["id"])
        self.assertEqual(detail["module"]["id"], self.module["id"])
        self.assertEqual(detail["unit"]["id"], unit_one["id"])
        self.assertEqual(detail["source_material"]["text"], "Quelle mit Umlaut: Grüße")
        self.assertEqual(detail["source_material"]["pages"][0]["page"], 1)
        self.assertEqual(detail["image_material"]["mime"], "image/png")

        unit_context = self.store.context(self.module["id"], unit_one["id"])
        self.assertEqual([row["id"] for row in unit_context["answer_submissions"]], [first["id"]])
        module_context = self.store.context(self.module["id"])
        self.assertEqual({row["id"] for row in module_context["answer_submissions"]}, {first["id"], second["id"]})
        self.assertNotIn(foreign["id"], {row["id"] for row in module_context["answer_submissions"]})
        self.assertEqual({row["id"] for row in self.store.list_answers(module_id=self.module["id"], status="all")}, {first["id"], second["id"]})
        self.assertEqual({row["id"] for row in self.store.list_answers(unit_id=unit_one["id"])}, {first["id"]})
        with self.assertRaises(ValueError):
            self.store.list_answers(module_id=self.module["id"], unit_id=other_unit["id"])

    def test_backup_preserves_pending_submission_and_reviewed_submission(self) -> None:
        pending_question = self.question()
        pending = self.store.submit_answer({"question_id": pending_question["id"], "answer": "Noch offen"})
        reviewed_question = self.question()
        reviewed = self.store.submit_answer({"question_id": reviewed_question["id"], "answer": "Schon geprüft"})
        reviewed = self.store.review_answer(reviewed["id"], {"rating": 2, "feedback": "Sicher."})
        with zipfile.ZipFile(BytesIO(self.store.backup())) as archive:
            restored_dir = Path(self.temp.name) / "restored"
            restored_dir.mkdir()
            archive.extractall(restored_dir)

        restored = Store(restored_dir, seed=False)
        self.assertEqual({row["id"] for row in restored.list_answers(status="all")}, {pending["id"], reviewed["id"]})
        restored_review = restored.get_answer(reviewed["id"])
        self.assertEqual(restored_review["attempt_id"], reviewed["attempt_id"])
        self.assertEqual(restored_review["rating"], 2)
        self.assertEqual(len(restored.snapshot()["attempts"]), 1)


if __name__ == "__main__":
    unittest.main()
