"""HTTP and CLI integration tests using isolated local storage."""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PACKAGE_DIR = Path(__file__).resolve().parents[1]
if str(PACKAGE_DIR) not in sys.path:
    # app.py supports direct execution from this directory and imports ai by name.
    sys.path.insert(0, str(PACKAGE_DIR))

from lernraum import cli  # noqa: E402
from lernraum.app import LocalServer  # noqa: E402
from lernraum.storage import Store  # noqa: E402


class ServerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="lernraum-server-", dir=PACKAGE_DIR / "tests")
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name, seed=False)
        self.server = LocalServer(("127.0.0.1", 0), self.store)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=3)

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

    def test_cli_http_workflow_preserves_unicode_sources_attempt_and_backup(self) -> None:
        module = cli.api_request(
            self.base_url,
            "/api/modules",
            method="POST",
            payload={"name": "Lineare Algebra – Übungsmodul", "code": "LA-Ü"},
        )
        self.assertEqual(module["name"], "Lineare Algebra – Übungsmodul")

        unit = cli.api_request(
            self.base_url,
            "/api/units",
            method="POST",
            payload={"module_id": module["id"], "title": "Vorlesung 1: Vektorräume", "kind": "lecture"},
        )
        source_text = "Ein Vektorraum über ℂ besitzt eine Addition und eine Skalarmultiplikation."
        material = cli.api_request(
            self.base_url,
            "/api/materials",
            method="POST",
            payload={
                "module_id": module["id"],
                "unit_ids": [unit["id"]],
                "name": "Skript – Vektorräume.txt",
                "mime": "text/plain",
                "content_base64": base64.b64encode(source_text.encode("utf-8")).decode("ascii"),
            },
        )

        imported = cli.api_request(
            self.base_url,
            "/api/questions/import",
            method="POST",
            payload={
                "module_id": module["id"],
                "unit_id": unit["id"],
                "questions": [
                    {
                        "type": "multiple_choice",
                        "prompt": "Über welchem Körper ist der Vektorraum im Skript definiert?",
                        "options": ["ℝ", "ℂ", "ℚ"],
                        "correct_index": 1,
                        "answer": "ℂ",
                        "explanation": "Das Skript nennt ausdrücklich ℂ.",
                        "topic": "Vektorräume",
                        "difficulty": 1,
                        "source_material_id": material["id"],
                        "source_page": 1,
                    }
                ],
            },
        )["questions"]
        question = imported[0]
        self.assertTrue(question["reviewed"])
        self.assertEqual(question["source_material_id"], material["id"])
        self.assertEqual(question["source_page"], 1)

        attempt = cli.api_request(
            self.base_url,
            "/api/attempts",
            method="POST",
            payload={"question_id": question["id"], "answer": "1", "rating": 0},
        )
        self.assertIs(attempt["correct"], True)
        self.assertEqual(attempt["rating"], 2)
        self.assertEqual(attempt["evaluation_source"], "automatic")

        snapshot = cli.api_request(self.base_url, "/api/state")
        self.assertEqual([item["name"] for item in snapshot["modules"]], [module["name"]])
        self.assertEqual(snapshot["attempts"][0]["question_id"], question["id"])
        self.assertEqual(snapshot["questions"][0]["attempt_count"], 1)

        query = urlencode({"module_id": module["id"], "unit_id": unit["id"]})
        context = cli.api_request(self.base_url, f"/api/context?{query}")
        self.assertEqual(context["materials"][0]["text"], source_text)
        self.assertEqual(context["questions"][0]["source_material_id"], material["id"])
        self.assertIn("ℂ", context["materials"][0]["pages"][0]["text"])

        original = cli.api_request(
            self.base_url, f"/api/materials/{material['id']}/file", binary=True
        )
        self.assertEqual(original, source_text.encode("utf-8"))

        archive_bytes = cli.api_request(self.base_url, "/api/backup", binary=True)
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            members = set(archive.namelist())
            self.assertIn("lernraum.sqlite3", members)
            stored_material = self.store.material_path(material["id"]).name
            self.assertIn(f"materials/{stored_material}", members)
            self.assertEqual(archive.read(f"materials/{stored_material}"), original)

    def test_mutations_reject_foreign_origin_host_and_missing_client_header(self) -> None:
        payload = {"name": "Darf nicht angelegt werden"}
        client = {"X-Lernraum-Client": "local"}

        status, _, body = self._raw_request(
            "/api/modules",
            method="POST",
            payload=payload,
            headers={**client, "Origin": "https://example.org"},
        )
        self.assertEqual(status, 403, body)

        status, _, body = self._raw_request(
            "/api/modules",
            method="POST",
            payload=payload,
            headers={**client, "Host": "example.org"},
        )
        self.assertEqual(status, 403, body)

        status, _, body = self._raw_request("/api/modules", method="POST", payload=payload)
        self.assertEqual(status, 403, body)
        self.assertEqual(self.store.snapshot()["modules"], [])

    def test_cross_module_source_import_is_400_and_atomic(self) -> None:
        local_module = self.store.create_module({"name": "Lokales Modul"})
        remote_module = self.store.create_module({"name": "Fremdes Modul"})
        local_material = self.store.upload_material(
            {
                "module_id": local_module["id"],
                "name": "lokal.txt",
                "mime": "text/plain",
                "content_base64": base64.b64encode(b"Lokale Quelle").decode("ascii"),
            }
        )
        remote_material = self.store.upload_material(
            {
                "module_id": remote_module["id"],
                "name": "fremd.txt",
                "mime": "text/plain",
                "content_base64": base64.b64encode(b"Fremde Quelle").decode("ascii"),
            }
        )
        before = len(self.store.snapshot()["questions"])
        status, _, body = self._raw_request(
            "/api/questions/import",
            method="POST",
            payload={
                "module_id": local_module["id"],
                "questions": [
                    {
                        "type": "multiple_choice",
                        "prompt": "Gültige Frage?",
                        "options": ["Ja", "Nein"],
                        "correct_index": 0,
                        "source_material_id": local_material["id"],
                        "source_page": 1,
                    },
                    {
                        "type": "multiple_choice",
                        "prompt": "Ungültige Frage?",
                        "options": ["Ja", "Nein"],
                        "correct_index": 0,
                        "source_material_id": remote_material["id"],
                        "source_page": 1,
                    },
                ],
            },
            headers={"X-Lernraum-Client": "local"},
        )
        self.assertEqual(status, 400, body)
        self.assertEqual(len(self.store.snapshot()["questions"]), before)

    def test_image_questions_require_image_mime(self) -> None:
        module = self.store.create_module({"name": "Bildfragen"})
        image = self.store.upload_material(
            {
                "module_id": module["id"],
                "name": "diagramm.png",
                "mime": "image/png",
                "content_base64": base64.b64encode(b"png bytes").decode("ascii"),
            }
        )
        text = self.store.upload_material(
            {
                "module_id": module["id"],
                "name": "notizen.txt",
                "mime": "text/plain",
                "content_base64": base64.b64encode(b"ordinary text").decode("ascii"),
            }
        )
        question = {
            "module_id": module["id"],
            "type": "image",
            "prompt": "Was ist auf dem Bild zu sehen?",
            "answer": "Ein Diagramm.",
        }

        status, _, body = self._raw_request(
            "/api/questions",
            method="POST",
            payload={**question, "image_material_id": text["id"]},
            headers={"X-Lernraum-Client": "local"},
        )
        self.assertEqual(status, 400, body)

        status, _, body = self._raw_request(
            "/api/questions",
            method="POST",
            payload={**question, "image_material_id": image["id"]},
            headers={"X-Lernraum-Client": "local"},
        )
        self.assertEqual(status, 201, body)
        self.assertEqual(json.loads(body)["image_material_id"], image["id"])

    def test_unreviewed_question_cannot_be_attempted(self) -> None:
        module = self.store.create_module({"name": "Ungeprüfte Frage"})
        status, _, body = self._raw_request(
            "/api/questions",
            method="POST",
            payload={
                "module_id": module["id"],
                "type": "free_text",
                "prompt": "Was steht im Vorschlag?",
                "answer": "Eine Musterantwort.",
                "reviewed": False,
            },
            headers={"X-Lernraum-Client": "local"},
        )
        self.assertEqual(status, 201, body)
        question = json.loads(body)
        self.assertFalse(question["reviewed"])

        status, _, body = self._raw_request(
            "/api/attempts",
            method="POST",
            payload={"question_id": question["id"], "answer": "Mein Versuch", "rating": 1},
            headers={"X-Lernraum-Client": "local"},
        )
        self.assertEqual(status, 400, body)
        state = self.store.snapshot()
        self.assertEqual(state["attempts"], [])
        self.assertEqual(state["questions"][0]["attempt_count"], 0)

    def test_unknown_routes_and_static_path_traversal_return_404(self) -> None:
        status, _, _ = self._raw_request("/api/not-a-route")
        self.assertEqual(status, 404)

        status, _, _ = self._raw_request("/..%2fCONTRACT.md")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
