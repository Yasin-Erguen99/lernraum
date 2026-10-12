"""Mocked-transport tests for the optional AI adapter; these never call a provider."""

from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from lernraum import ai


def _http_response(payload: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _openai_response(result: object, status: str = "completed") -> dict[str, object]:
    if result is None:
        output = []
    else:
        output = [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(result, ensure_ascii=False)}],
            }
        ]
    return {"status": status, "output": output}


def _question(
    *,
    question_type: str = "multiple_choice",
    material_id: str = "mat-1",
    page: int | None = 2,
) -> dict[str, object]:
    if question_type == "multiple_choice":
        options = ["Option A", "Option B", "Option C"]
        correct_index: int | None = 1
        answer = "Option B"
    else:
        options = []
        correct_index = None
        answer = "The expected answer from the source."
    return {
        "type": question_type,
        "prompt": "Which statement is supported by the source?",
        "options": options,
        "correct_index": correct_index,
        "answer": answer,
        "explanation": "The cited text explains this point.",
        "topic": "Foundations",
        "difficulty": 2,
        "source_material_id": material_id,
        "source_page": page,
    }


class AiAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dotenv_patch = patch.object(ai, "_dotenv_values", return_value={})
        self.dotenv_patch.start()
        self.addCleanup(self.dotenv_patch.stop)

    @staticmethod
    def _context() -> dict[str, object]:
        return {
            "materials": [
                {
                    "id": "mat-1",
                    "name": "Vorlesung 1.pdf",
                    "pages": [
                        {"page": 1, "text": "Grundbegriffe werden eingeführt."},
                        {"page": 2, "text": "Das zweite Prinzip folgt aus dem ersten."},
                    ],
                    "text": "Grundbegriffe werden eingeführt. Das zweite Prinzip folgt aus dem ersten.",
                },
                {
                    "id": "mat-2",
                    "name": "Praktikum.txt",
                    "text": "Im Praktikum wird das Verfahren angewendet.",
                },
            ]
        }

    @staticmethod
    def _generation_request(**overrides: object) -> dict[str, object]:
        result: dict[str, object] = {
            "material_ids": ["mat-1"],
            "count": 1,
            "types": ["multiple_choice"],
            "difficulty": 2,
        }
        result.update(overrides)
        return result

    def test_status_has_no_implicit_provider_or_model(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(ai.urllib.request, "urlopen") as urlopen:
            result = ai.status()

        self.assertEqual(
            result,
            {
                "provider": None,
                "configured": False,
                "model": None,
                "reason": "Noch kein KI-Dienst eingerichtet.",
            },
        )
        urlopen.assert_not_called()

    def test_generate_sends_openai_responses_structured_output_and_marks_proposals(self) -> None:
        generated = {"questions": [_question()]}
        captured: list[tuple[object, int]] = []

        def fake_urlopen(request: object, timeout: int) -> io.BytesIO:
            captured.append((request, timeout))
            return _http_response(_openai_response(generated))

        with patch.dict(
            os.environ,
            {
                "LERNRAUM_AI_PROVIDER": "openai",
                "LERNRAUM_AI_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key-do-not-disclose",
            },
            clear=True,
        ), patch.object(ai.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = ai.generate(self._context(), self._generation_request())

        self.assertEqual(len(captured), 1)
        request, timeout = captured[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key-do-not-disclose")
        self.assertEqual(timeout, ai.REQUEST_TIMEOUT_SECONDS)
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "test-model")
        self.assertIs(body["store"], False)
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertIs(body["text"]["format"]["strict"], True)
        self.assertEqual(result[0]["source_material_id"], "mat-1")
        self.assertEqual(result[0]["source_page"], 2)
        self.assertIs(result[0]["is_ai"], True)
        self.assertIs(result[0]["reviewed"], False)

    def test_generate_validates_material_and_page_citations(self) -> None:
        bad_question = _question(material_id="not-selected")
        with patch.dict(
            os.environ,
            {
                "LERNRAUM_AI_PROVIDER": "openai",
                "LERNRAUM_AI_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            clear=True,
        ), patch.object(
            ai.urllib.request,
            "urlopen",
            return_value=_http_response(_openai_response({"questions": [bad_question]})),
        ):
            with self.assertRaisesRegex(ValueError, "Material"):
                ai.generate(self._context(), self._generation_request())

        bad_question = _question(page=99)
        with patch.dict(
            os.environ,
            {
                "LERNRAUM_AI_PROVIDER": "openai",
                "LERNRAUM_AI_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            clear=True,
        ), patch.object(
            ai.urllib.request,
            "urlopen",
            return_value=_http_response(_openai_response({"questions": [bad_question]})),
        ):
            with self.assertRaisesRegex(ValueError, "Seite"):
                ai.generate(self._context(), self._generation_request())

    def test_generate_fails_explicitly_when_source_context_exceeds_cap(self) -> None:
        context = self._context()
        with patch.dict(os.environ, {}, clear=True), patch.object(ai, "MAX_CONTEXT_CHARS", 20), patch.object(
            ai.urllib.request, "urlopen"
        ) as urlopen:
            with self.assertRaisesRegex(ValueError, "umfangreich"):
                ai.generate(context, self._generation_request())
        urlopen.assert_not_called()

    def test_generate_does_not_call_provider_when_unconfigured(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(ai.urllib.request, "urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "Noch kein KI-Dienst"):
                ai.generate(self._context(), self._generation_request())
        urlopen.assert_not_called()

    def test_openai_refusal_and_incomplete_responses_are_clean_errors(self) -> None:
        cases = [
            (
                {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "private"}]}]},
                "abgelehnt",
            ),
            (_openai_response(None, status="incomplete"), "unvollständig"),
        ]
        for response, message in cases:
            with self.subTest(message=message), patch.dict(
                os.environ,
                {
                    "LERNRAUM_AI_PROVIDER": "openai",
                    "LERNRAUM_AI_MODEL": "test-model",
                    "OPENAI_API_KEY": "test-key",
                },
                clear=True,
            ), patch.object(ai.urllib.request, "urlopen", return_value=_http_response(response)):
                with self.assertRaisesRegex(ValueError, message):
                    ai.generate(self._context(), self._generation_request())

    def test_ollama_uses_generate_endpoint_json_schema_and_nonstreaming(self) -> None:
        generated = {"questions": [_question(question_type="free_text", page=None)]}
        captured: list[object] = []

        def fake_urlopen(request: object, timeout: int) -> io.BytesIO:
            captured.append(request)
            return _http_response({"done": True, "done_reason": "stop", "response": json.dumps(generated)})

        context = {"materials": [{"id": "mat-1", "name": "Notizen", "text": "Das erwartete Prinzip steht hier."}]}
        with patch.dict(
            os.environ,
            {
                "LERNRAUM_AI_PROVIDER": "ollama",
                "LERNRAUM_AI_MODEL": "local-model",
                "LERNRAUM_OLLAMA_URL": "http://localhost:11434/",
            },
            clear=True,
        ), patch.object(ai.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = ai.generate(context, self._generation_request(types=["free_text"]))

        request = captured[0]
        self.assertEqual(request.full_url, "http://localhost:11434/api/generate")
        body = json.loads(request.data.decode("utf-8"))
        self.assertIs(body["stream"], False)
        self.assertEqual(body["model"], "local-model")
        self.assertEqual(body["format"]["properties"]["questions"]["type"], "array")
        self.assertEqual(result[0]["type"], "free_text")
        self.assertIsNone(result[0]["source_page"])

    def test_evaluate_returns_rating_and_explanation_as_feedback_without_saving(self) -> None:
        feedback = {"rating": 1, "feedback": "Teilweise richtig: erkläre noch den zweiten Schritt."}
        captured: list[object] = []

        def fake_urlopen(request: object, timeout: int) -> io.BytesIO:
            captured.append(request)
            return _http_response(_openai_response(feedback))

        with patch.dict(
            os.environ,
            {
                "LERNRAUM_AI_PROVIDER": "openai",
                "LERNRAUM_AI_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            clear=True,
        ), patch.object(ai.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = ai.evaluate(
                {"prompt": "Explain the concept", "answer": "Expected explanation", "explanation": "Two steps."},
                "I described the first step.",
            )

        self.assertEqual(result, feedback)
        self.assertEqual(set(result), {"rating", "feedback"})
        body = json.loads(captured[0].data.decode("utf-8"))
        self.assertIs(body["store"], False)
        self.assertIn("student_answer", body["input"][1]["content"])

    def test_provider_http_failure_does_not_echo_response_body_or_key(self) -> None:
        secret = "test-key-that-must-not-appear"
        failure = urllib.error.HTTPError(
            "https://api.openai.com/v1/responses",
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(secret.encode("utf-8")),
        )
        with patch.dict(
            os.environ,
            {
                "LERNRAUM_AI_PROVIDER": "openai",
                "LERNRAUM_AI_MODEL": "test-model",
                "OPENAI_API_KEY": secret,
            },
            clear=True,
        ), patch.object(ai.urllib.request, "urlopen", side_effect=failure):
            with self.assertRaises(ValueError) as raised:
                ai.generate(self._context(), self._generation_request())
        self.assertNotIn(secret, str(raised.exception))
        self.assertIn("HTTP 401", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

