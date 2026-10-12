"""Mocked HTTP tests for the no-API answer review workflow."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from lernraum import cli


def _response(value: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(value, ensure_ascii=False).encode("utf-8"))


class AnswerCliTests(unittest.TestCase):
    def test_answers_list_passes_filters_and_writes_json_output(self) -> None:
        captured = []
        response_data = {"answers": [{"id": "antwort-1", "status": "pending"}]}

        def mock_urlopen(request, timeout):
            captured.append(request)
            self.assertEqual(timeout, 30)
            return _response(response_data)

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp_dir:
            output = Path(temp_dir) / "offene-antworten.json"
            with patch.object(cli, "urlopen", side_effect=mock_urlopen):
                result = cli.main([
                    "answers", "list", "--module", "modul-1", "--unit", "einheit-2",
                    "--output", str(output),
                ])

            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), response_data)

        self.assertEqual(len(captured), 1)
        request = captured[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(
            parse_qs(urlsplit(request.full_url).query),
            {"status": ["pending"], "module_id": ["modul-1"], "unit_id": ["einheit-2"]},
        )

    def test_submit_reads_utf8_answer_file_and_posts_pending_answer(self) -> None:
        captured = []
        answer_text = "Risiko = Eintrittswahrscheinlichkeit × Schadenshöhe.\nÜberwachen!"

        def mock_urlopen(request, timeout):
            captured.append(request)
            return _response({"id": "antwort-1", "status": "pending"})

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp_dir:
            answer_file = Path(temp_dir) / "antwort.txt"
            answer_file.write_text(answer_text, encoding="utf-8")
            with patch.object(cli, "urlopen", side_effect=mock_urlopen):
                result = cli.main([
                    "answers", "submit", "--question", "frage-7",
                    "--answer-file", str(answer_file), "--duration", "85",
                ])

        self.assertEqual(result, 0)
        request = captured[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, f"{cli.DEFAULT_URL}/api/answers")
        self.assertEqual(request.get_header("X-lernraum-client"), "local")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"question_id": "frage-7", "answer": answer_text, "duration_seconds": 85},
        )

    def test_review_reads_utf8_feedback_file_and_posts_default_reviewer(self) -> None:
        captured = []
        feedback_text = "Die Definition stimmt. Es fehlt noch die Begründung zum Beispiel."

        def mock_urlopen(request, timeout):
            captured.append(request)
            return _response({"id": "antwort-1", "status": "reviewed", "rating": 1})

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp_dir:
            feedback_file = Path(temp_dir) / "feedback.txt"
            feedback_file.write_text(feedback_text, encoding="utf-8")
            with patch.object(cli, "urlopen", side_effect=mock_urlopen):
                result = cli.main([
                    "answers", "review", "antwort-1", "--rating", "1",
                    "--feedback-file", str(feedback_file),
                ])

        self.assertEqual(result, 0)
        request = captured[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, f"{cli.DEFAULT_URL}/api/answers/antwort-1/review")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"rating": 1, "feedback": feedback_text, "reviewer": "ChatGPT (im Chat)"},
        )

    def test_blank_review_feedback_is_rejected_before_http_request(self) -> None:
        args = cli.build_parser().parse_args(
            ["answers", "review", "antwort-1", "--rating", "0", "--feedback", "  \n"]
        )
        with patch.object(cli, "urlopen") as urlopen, self.assertRaises(cli.LernraumError):
            cli.run(args)
        urlopen.assert_not_called()

    def test_answers_list_defaults_to_pending_and_accepts_all_status(self) -> None:
        parser = cli.build_parser()
        default_args = parser.parse_args(["answers", "list"])
        all_args = parser.parse_args(["answers", "list", "--status", "all"])
        self.assertEqual(default_args.status, "pending")
        self.assertEqual(all_args.status, "all")


if __name__ == "__main__":
    unittest.main()
