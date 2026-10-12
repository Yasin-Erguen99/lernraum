"""HTTP and CLI integration tests for pending-answer review."""

from __future__ import annotations

import base64
import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PACKAGE_DIR = Path(__file__).resolve().parents[1]
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

from lernraum import cli  # noqa: E402
from lernraum.app import LocalServer  # noqa: E402
from lernraum.storage import Store  # noqa: E402


class AnswerServerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="lernraum-answer-server-", dir=PACKAGE_DIR / "tests")
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name, seed=False)
        self.module = self.store.create_module({"name": "Softwaretechnik – Risikomanagement"})
        self.unit = self.store.create_unit(
            {"module_id": self.module["id"], "title": "Vorlesung 2", "kind": "lecture"}
        )
        source_text = "Risiko wird als Produkt aus Eintrittswahrscheinlichkeit und Schadenshöhe beschrieben."
        self.material = self.store.upload_material(
            {
                "module_id": self.module["id"],
                "unit_ids": [self.unit["id"]],
                "name": "Vorlesung 2 – Risikomanagement.txt",
                "mime": "text/plain",
                "content_base64": base64.b64encode(source_text.encode("utf-8")).decode("ascii"),
            }
        )
        self.server = LocalServer(("127.0.0.1", 0), self.store)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.question = self._create_question()

    def test_cli_rechecks_existing_self_answer_without_adding_an_attempt(self) -> None:
        original = self.store.record_attempt({
            "question_id": self.question["id"], "answer": "p × K", "rating": 1,
            "duration_seconds": 35,
        })
        feedback = "Die Formel p × K ist richtig. Grundlage: Vorlesung 2, Seite 1."
        args = cli.build_parser().parse_args([
            "--url", self.base_url, "answers", "review-attempt", original["id"],
            "--rating", "2", "--feedback", feedback,
        ])
        review = cli.run(args)
        self.assertEqual(review["attempt_id"], original["id"])
        self.assertEqual(review["feedback"], feedback)
        state = cli.api_request(self.base_url, "/api/state")
        self.assertEqual(len(state["attempts"]), 1)
        saved = state["attempts"][0]
        self.assertEqual(saved["id"], original["id"])
        self.assertEqual(saved["answered_at"], original["answered_at"])
        self.assertEqual(saved["duration_seconds"], 35)
        self.assertEqual(saved["rating"], 2)
        self.assertEqual(state["questions"][0]["attempt_count"], 1)
        self.assertEqual(state["questions"][0]["mastery"], 100)
        self.assertEqual(state["stats"]["totals"]["attempts"], 1)
        self.assertEqual(state["stats"]["totals"]["pending_answers"], 0)
        self.assertEqual(state["answer_submissions"][0]["status"], "reviewed")
        status, _, body = self._raw_request(
            f"/api/attempts/{original['id']}/review", method="POST",
            payload={"rating": 0, "feedback": "Erneut prüfen"},
            headers={"X-Lernraum-Client": "local"},
        )
        self.assertEqual(status, 400, body)
        self.assertEqual(len(self.store.snapshot()["attempts"]), 1)

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=3)

    def _create_question(self, prompt: str = "Wie wird das Risiko in der Vorlesung bestimmt?") -> dict:
        return self.store.create_question(
            {
                "module_id": self.module["id"],
                "unit_id": self.unit["id"],
                "type": "free_text",
                "prompt": prompt,
                "answer": "Durch Multiplikation von Eintrittswahrscheinlichkeit und Schadenshöhe.",
                "explanation": "Beide Faktoren bestimmen zusammen die Risikohöhe.",
                "topic": "Risikoanalyse",
                "difficulty": 2,
                "source_material_id": self.material["id"],
                "source_page": 1,
                "reviewed": True,
            }
        )

    def _raw_request(self, path: str, *, method: str = "GET", payload=None, headers=None):
        request_headers = dict(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json; charset=utf-8")
        request = Request(self.base_url + path, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read()
        except HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def _submit(self, question_id: str | None = None, answer: str = "R = p mal K.") -> dict:
        status, _, body = self._raw_request(
            "/api/answers",
            method="POST",
            payload={"question_id": question_id or self.question["id"], "answer": answer, "duration_seconds": 42},
            headers={"X-Lernraum-Client": "local"},
        )
        self.assertEqual(status, 201, body)
        return json.loads(body)

    def _cli_run(self, *args):
        return cli.run(cli.build_parser().parse_args(["--url", self.base_url, *args]))

    def test_pending_submission_filters_show_source_and_leaves_stats_ungraded(self) -> None:
        self.assertEqual(self.store.stats()["totals"]["due_questions"], 1)
        submission = self._submit()
        other_module = self.store.create_module({"name": "Anderes Modul"})
        other_unit = self.store.create_unit(
            {"module_id": other_module["id"], "title": "Praktikum", "kind": "practical"}
        )
        other_question = self.store.create_question(
            {
                "module_id": other_module["id"],
                "unit_id": other_unit["id"],
                "type": "free_text",
                "prompt": "Eine unabhängige Frage?",
                "answer": "Eine Antwort.",
                "difficulty": 1,
                "reviewed": True,
            }
        )
        other_submission = self._submit(other_question["id"], "Unabhängige Antwort.")

        query = urlencode({"module_id": self.module["id"], "unit_id": self.unit["id"]})
        status, _, body = self._raw_request(f"/api/answers?{query}")
        self.assertEqual(status, 200, body)
        self.assertEqual([item["id"] for item in json.loads(body)["answers"]], [submission["id"]])
        self.assertEqual(json.loads(self._raw_request("/api/answers?status=reviewed")[2])["answers"], [])
        self.assertEqual(len(json.loads(self._raw_request("/api/answers")[2])["answers"]), 2)
        self.assertEqual(len(json.loads(self._raw_request("/api/answers?status=all")[2])["answers"]), 2)

        status, _, body = self._raw_request(f"/api/answers/{submission['id']}")
        detail = json.loads(body)
        self.assertEqual(status, 200, body)
        self.assertEqual(detail["answer"], "R = p mal K.")
        self.assertEqual(detail["question"]["prompt"], self.question["prompt"])
        self.assertEqual(detail["module"]["name"], self.module["name"])
        self.assertEqual(detail["unit"]["title"], self.unit["title"])
        self.assertEqual(detail["source_material"]["id"], self.material["id"])
        self.assertIn("Eintrittswahrscheinlichkeit", detail["source_material"]["text"])
        self.assertEqual(detail["source_material"]["pages"][0]["page"], 1)

        state = json.loads(self._raw_request("/api/state")[2])
        stats = state["stats"]
        self.assertEqual(stats["totals"]["attempts"], 0)
        self.assertEqual(stats["totals"]["pending_answers"], 2)
        self.assertEqual(stats["totals"]["due_questions"], 0)
        self.assertIsNone(stats["totals"]["mastery_percent"])
        self.assertTrue(all(question["attempt_count"] == 0 for question in state["questions"]))
        self.assertEqual(state["attempts"], [])

    def test_review_saves_unicode_feedback_once_and_records_one_attempt(self) -> None:
        submission = self._submit(answer="p · K = R")
        feedback = "Teilweise richtig: Die Formel stimmt; ein Beispiel aus der Vorlesung fehlt. β und Größe sind erhalten."
        payload = {"rating": 1, "feedback": feedback, "reviewer": "ChatGPT (im Chat)"}
        status, _, body = self._raw_request(
            f"/api/answers/{submission['id']}/review",
            method="POST",
            payload=payload,
            headers={"X-Lernraum-Client": "local"},
        )
        self.assertEqual(status, 200, body)
        reviewed = json.loads(body)
        self.assertEqual(reviewed["status"], "reviewed")
        self.assertEqual(reviewed["rating"], 1)
        self.assertEqual(reviewed["feedback"], feedback)
        self.assertIsNotNone(reviewed["reviewed_at"])
        self.assertEqual(reviewed["reviewer"], "ChatGPT (im Chat)")
        self.assertIsNotNone(reviewed["attempt_id"])

        state = json.loads(self._raw_request("/api/state")[2])
        self.assertEqual(len(state["attempts"]), 1)
        attempt = state["attempts"][0]
        self.assertEqual(attempt["id"], reviewed["attempt_id"])
        self.assertEqual(attempt["question_id"], self.question["id"])
        self.assertEqual(attempt["answer"], "p · K = R")
        self.assertEqual(attempt["rating"], 1)
        self.assertIsNone(attempt["correct"])
        self.assertEqual(attempt["evaluation_source"], "ai")
        self.assertEqual(state["questions"][0]["attempt_count"], 1)

        status, _, body = self._raw_request(
            f"/api/answers/{submission['id']}/review",
            method="POST",
            payload=payload,
            headers={"X-Lernraum-Client": "local"},
        )
        self.assertEqual(status, 400, body)
        state = json.loads(self._raw_request("/api/state")[2])
        self.assertEqual(len(state["attempts"]), 1)
        self.assertEqual(state["answer_submissions"][0]["attempt_id"], reviewed["attempt_id"])

    def test_cli_parser_and_run_list_show_review_against_server_and_reads_bom_feedback(self) -> None:
        submission = self._submit(answer="Das Risiko kombiniert Wahrscheinlichkeit und Schaden.")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self._cli_run("answers", "list", "--module", self.module["id"], "--unit", self.unit["id"])
        self.assertIsNone(result)
        listing = json.loads(output.getvalue())
        self.assertEqual(listing["answers"][0]["id"], submission["id"])

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = self._cli_run("answers", "show", submission["id"])
        self.assertIsNone(result)
        detail = json.loads(output.getvalue())
        self.assertEqual(detail["source_material"]["id"], self.material["id"])
        self.assertEqual(detail["question"]["id"], self.question["id"])

        feedback = "Die Kernaussage stimmt; nenne noch die Multiplikation."
        feedback_file = Path(self.temp.name) / "feedback.txt"
        feedback_file.write_bytes(b"\xef\xbb\xbf" + feedback.encode("utf-8"))
        reviewed = self._cli_run(
            "answers", "review", submission["id"], "--rating", "1", "--feedback-file", str(feedback_file)
        )
        self.assertEqual(reviewed["status"], "reviewed")
        self.assertEqual(reviewed["feedback"], feedback)
        self.assertEqual(reviewed["reviewer"], "ChatGPT (im Chat)")
        self.assertEqual(len(self.store.snapshot()["attempts"]), 1)

    def test_invalid_rating_and_empty_feedback_leave_submission_pending(self) -> None:
        submission = self._submit()
        for payload in (
            {"rating": 3, "feedback": "Ungültiger Wert"},
            {"rating": 2, "feedback": "  \n"},
        ):
            status, _, body = self._raw_request(
                f"/api/answers/{submission['id']}/review",
                method="POST",
                payload=payload,
                headers={"X-Lernraum-Client": "local"},
            )
            self.assertEqual(status, 400, body)

        state = json.loads(self._raw_request("/api/state")[2])
        self.assertEqual(len(state["attempts"]), 0)
        self.assertEqual(state["answer_submissions"][0]["status"], "pending")
        self.assertIsNone(state["answer_submissions"][0]["rating"])
        self.assertEqual(state["stats"]["totals"]["pending_answers"], 1)

    def test_new_answer_mutations_enforce_local_header_and_origin(self) -> None:
        payload = {"question_id": self.question["id"], "answer": "Darf nicht gespeichert werden."}
        status, _, body = self._raw_request("/api/answers", method="POST", payload=payload)
        self.assertEqual(status, 403, body)

        status, _, body = self._raw_request(
            "/api/answers",
            method="POST",
            payload=payload,
            headers={"X-Lernraum-Client": "local", "Origin": "https://example.org"},
        )
        self.assertEqual(status, 403, body)
        submission = self._submit()

        review_payload = {"rating": 2, "feedback": "Korrekt."}
        status, _, body = self._raw_request(
            f"/api/answers/{submission['id']}/review", method="POST", payload=review_payload
        )
        self.assertEqual(status, 403, body)
        status, _, body = self._raw_request(
            f"/api/answers/{submission['id']}/review",
            method="POST",
            payload=review_payload,
            headers={"X-Lernraum-Client": "local", "Origin": "https://example.org"},
        )
        self.assertEqual(status, 403, body)

        state = json.loads(self._raw_request("/api/state")[2])
        self.assertEqual(len(state["answer_submissions"]), 1)
        self.assertEqual(state["answer_submissions"][0]["status"], "pending")
        self.assertEqual(state["attempts"], [])

    def test_backup_restore_keeps_pending_answer_and_review_feedback(self) -> None:
        pending = self._submit(answer="Offene Antwort mit ä und β.")
        second_question = self._create_question("Nenne die beiden Faktoren der Risikoberechnung.")
        reviewed = self._submit(second_question["id"], answer="Wahrscheinlichkeit und Schaden.")
        feedback = "Gut erklärt – ergänze noch die Verknüpfung über das Produkt."
        status, _, body = self._raw_request(
            f"/api/answers/{reviewed['id']}/review",
            method="POST",
            payload={"rating": 1, "feedback": feedback},
            headers={"X-Lernraum-Client": "local"},
        )
        self.assertEqual(status, 200, body)

        status, _, archive_bytes = self._raw_request("/api/backup")
        self.assertEqual(status, 200, archive_bytes[:200])
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            self.assertIn("lernraum.sqlite3", archive.namelist())
            restored_dir = Path(self.temp.name) / "restored"
            restored_dir.mkdir()
            (restored_dir / "lernraum.sqlite3").write_bytes(archive.read("lernraum.sqlite3"))

        restored = Store(restored_dir, seed=False)
        submissions = restored.list_answers(module_id=self.module["id"], status="all")
        self.assertEqual({item["id"] for item in submissions}, {pending["id"], reviewed["id"]})
        by_id = {item["id"]: item for item in submissions}
        self.assertEqual(by_id[pending["id"]]["status"], "pending")
        self.assertEqual(by_id[pending["id"]]["answer"], "Offene Antwort mit ä und β.")
        self.assertEqual(by_id[reviewed["id"]]["status"], "reviewed")
        self.assertEqual(by_id[reviewed["id"]]["feedback"], feedback)
        self.assertEqual(len(restored.snapshot()["attempts"]), 1)


if __name__ == "__main__":
    unittest.main()
