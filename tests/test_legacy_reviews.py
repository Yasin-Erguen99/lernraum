from __future__ import annotations

import tempfile
import sqlite3
import unittest
from datetime import datetime
from pathlib import Path

from lernraum.storage import Store


class LegacyAttemptReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.module = self.store.snapshot()["modules"][0]

    def question(self, *, qtype: str = "free_text", reviewed: bool = True, **extra) -> dict:
        data = {
            "module_id": self.module["id"],
            "type": qtype,
            "prompt": f"Frage {qtype}",
            "reviewed": reviewed,
            **extra,
        }
        if qtype == "multiple_choice":
            data.update(options=["A", "B"], correct_index=0)
        return self.store.create_question(data)

    def legacy_attempt(self, question: dict, *, rating: int = 1, answer: str = "Meine Antwort",
                       duration_seconds: int = 41) -> dict:
        return self.store.record_attempt({
            "question_id": question["id"],
            "answer": answer,
            "rating": rating,
            "duration_seconds": duration_seconds,
        })

    def learning_state(self, question_id: str) -> tuple[int, int, int, str | None]:
        conn = sqlite3.connect(self.store.db_path)
        try:
            return conn.execute(
                "SELECT attempt_count,mastery,review_stage,due_at FROM questions WHERE id=?",
                (question_id,),
            ).fetchone()
        finally:
            conn.close()

    def test_review_updates_original_attempt_once_and_surfaces_feedback_everywhere(self) -> None:
        question = self.question()
        original = self.legacy_attempt(question, rating=1, answer="  Erklärte Antwort  ", duration_seconds=83)
        before = self.learning_state(question["id"])
        self.assertEqual(self.store.list_answers(status="pending"), [])

        reviewed = self.store.review_attempt(original["id"], {
            "rating": 2,
            "feedback": "Die Kernaussage stimmt; die Begründung ist nachvollziehbar.",
        })
        self.assertNotEqual(reviewed["id"], original["id"])
        self.assertEqual(reviewed["attempt_id"], original["id"])
        attempts = self.store.snapshot()["attempts"]
        self.assertEqual(len(attempts), 1)
        saved = attempts[0]
        self.assertEqual(saved["id"], original["id"])
        self.assertEqual(saved["answer"], original["answer"])
        self.assertEqual(saved["answered_at"], original["answered_at"])
        self.assertEqual(saved["duration_seconds"], 83)
        self.assertEqual(saved["rating"], 2)
        self.assertEqual(saved["evaluation_source"], "ai")
        self.assertIsNone(saved["correct"])

        after = self.learning_state(question["id"])
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[1], 100)
        # The previous rating of 1 had already advanced the stage once. Rechecking
        # the same answer changes its grade but must not advance the stage again.
        self.assertEqual(after[2], 1)
        due = datetime.fromisoformat(after[3].replace("Z", "+00:00"))
        reviewed_at = datetime.fromisoformat(reviewed["reviewed_at"].replace("Z", "+00:00"))
        self.assertEqual((due - reviewed_at).days, 3)

        self.assertEqual(self.store.list_answers(status="pending"), [])
        reviewed_list = self.store.list_answers(status="reviewed")
        self.assertEqual(len(reviewed_list), 1)
        self.assertEqual(reviewed_list[0]["id"], reviewed["id"])
        self.assertEqual(reviewed_list[0]["feedback"], reviewed["feedback"])
        self.assertEqual(reviewed_list[0]["attempt_id"], original["id"])
        detail = self.store.get_answer(reviewed["id"])
        self.assertEqual(detail["feedback"], reviewed["feedback"])
        self.assertEqual(detail["answer"], original["answer"])
        self.assertEqual(detail["question"]["id"], question["id"])
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["answer_submissions"], reviewed_list)
        self.assertEqual(self.store.context(self.module["id"])["answer_submissions"], reviewed_list)

        with self.assertRaisesRegex(ValueError, "bereits geprüft"):
            self.store.review_attempt(original["id"], {"rating": 0, "feedback": "Noch einmal"})
        self.assertEqual(len(self.store.snapshot()["attempts"]), 1)

    def test_invalid_review_rolls_back_without_creating_a_submission(self) -> None:
        question = self.question()
        original = self.legacy_attempt(question)
        for data in (
            {"rating": True, "feedback": "Text"},
            {"rating": 3, "feedback": "Text"},
            {"rating": 1, "feedback": "  "},
            {"rating": 1, "feedback": "x" * 20001},
        ):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    self.store.review_attempt(original["id"], data)
                stored = self.store.snapshot()["attempts"][0]
                self.assertEqual(stored["rating"], 1)
                self.assertEqual(stored["evaluation_source"], "self")
                self.assertEqual(len(self.store.snapshot()["answer_submissions"]), 0)
                self.assertEqual(self.store.list_answers(), [])

    def test_review_of_older_attempt_does_not_change_current_learning_state(self) -> None:
        question = self.question()
        older = self.legacy_attempt(question, rating=1, answer="Frühere Antwort")
        newer = self.legacy_attempt(question, rating=2, answer="Spätere Antwort")
        before = self.learning_state(question["id"])

        self.store.review_attempt(older["id"], {
            "rating": 0,
            "feedback": "Die ältere Antwort war unvollständig.",
        })
        after = self.learning_state(question["id"])
        self.assertEqual(after, before)
        self.assertEqual(self.store.list_answers(), [])
        attempts = {row["id"]: row for row in self.store.snapshot()["attempts"]}
        self.assertEqual(attempts[older["id"]]["rating"], 0)
        self.assertEqual(attempts[newer["id"]]["rating"], 2)

    def test_rejects_non_self_non_free_text_and_unreviewed_attempts(self) -> None:
        mc = self.question(qtype="multiple_choice")
        mc_attempt = self.store.record_attempt({"question_id": mc["id"], "answer": 0, "rating": 2})
        ai_question = self.question()
        ai_attempt = self.store.record_attempt({
            "question_id": ai_question["id"], "answer": "Antwort", "rating": 1,
            "evaluation_source": "ai",
        })
        edited_question = self.question()
        edited_attempt = self.legacy_attempt(edited_question)
        self.store.update_question(edited_question["id"], {"reviewed": False})

        for attempt in (mc_attempt, ai_attempt, edited_attempt):
            with self.subTest(attempt=attempt["id"]):
                with self.assertRaises(ValueError):
                    self.store.review_attempt(attempt["id"], {"rating": 2, "feedback": "Prüfung"})
        self.assertEqual(len(self.store.snapshot()["answer_submissions"]), 0)
        self.assertEqual(self.store.list_answers(status="pending"), [])

    def test_uses_reviewed_submission_attempt_count_and_retains_latest_order_on_timestamp_tie(self) -> None:
        question = self.question()
        first = self.legacy_attempt(question, rating=1, answer="Gleiche Sekunde, erste Zeile")
        second = self.legacy_attempt(question, rating=1, answer="Gleiche Sekunde, zweite Zeile")
        # Force identical precise timestamps so rowid is the deterministic tie-breaker.
        conn = sqlite3.connect(self.store.db_path)
        try:
            conn.execute("UPDATE attempts SET answered_at=? WHERE id IN (?,?)", (
                "2026-01-02T03:04:05.123456Z", first["id"], second["id"],
            ))
            conn.commit()
        finally:
            conn.close()
        before = self.learning_state(question["id"])
        self.store.review_attempt(first["id"], {"rating": 0, "feedback": "Älter bei gleicher Zeit."})
        self.assertEqual(self.learning_state(question["id"]), before)
        self.assertEqual(self.store.list_answers(), [])


if __name__ == "__main__":
    unittest.main()
