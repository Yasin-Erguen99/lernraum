from __future__ import annotations

import base64
import binascii
import struct
import tempfile
import unittest
import zipfile
import zlib
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from lernraum.storage import Store


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.module = self.store.snapshot()["modules"][0]
        self.other_module = self.store.snapshot()["modules"][1]

    def upload(self, module_id: str, name: str = "lecture.txt", content: bytes = b"Alpha\nBeta", **extra):
        payload = {
            "module_id": module_id,
            "unit_ids": extra.pop("unit_ids", []),
            "name": name,
            "mime": extra.pop("mime", "text/plain"),
            "content_base64": base64.b64encode(content).decode("ascii"),
            **extra,
        }
        return self.store.upload_material(payload)

    @staticmethod
    def png_1x1() -> bytes:
        def chunk(kind: bytes, data: bytes) -> bytes:
            body = kind + data
            return struct.pack(">I", len(data)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)

        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff\xff"))
            + chunk(b"IEND", b"")
        )

    def test_seed_modules_are_empty_editable_and_not_recreated_after_deletion(self) -> None:
        state = self.store.snapshot()
        self.assertEqual([module["name"] for module in state["modules"]], ["Modul 1", "Modul 2"])
        self.assertEqual(state["units"], [])
        self.assertEqual(state["materials"], [])
        changed = self.store.update_module(self.module["id"], {"name": "Analysis"})
        self.assertEqual(changed["name"], "Analysis")
        self.store.delete_module(self.other_module["id"])
        reopened = Store(self.temp.name)
        self.assertEqual([module["name"] for module in reopened.snapshot()["modules"]], ["Analysis"])

    def test_upload_extracts_text_and_rejects_cross_module_unit_links(self) -> None:
        unit = self.store.create_unit({"module_id": self.module["id"], "title": "Vorlesung 1", "kind": "lecture"})
        other_unit = self.store.create_unit({"module_id": self.other_module["id"], "title": "Praktikum", "kind": "practical"})
        material = self.upload(self.module["id"], unit_ids=[unit["id"]])
        detail = self.store.get_material(material["id"])
        self.assertEqual(detail["text"], "Alpha\nBeta")
        self.assertEqual(detail["pages"], [{"page": 1, "text": "Alpha\nBeta"}])
        self.assertEqual(detail["extraction_status"], "ready")
        with self.assertRaises(ValueError):
            self.upload(self.module["id"], unit_ids=[other_unit["id"]])

    def test_docx_and_pptx_extract_text_by_document_page(self) -> None:
        docx_bytes = BytesIO()
        with zipfile.ZipFile(docx_bytes, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="urn:w"><w:body><w:p><w:r><w:t>Begriff</w:t></w:r></w:p></w:body></w:document>',
            )
        docx = self.upload(
            self.module["id"], "skript.docx", docx_bytes.getvalue(),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(self.store.get_material(docx["id"])["text"], "Begriff")

        pptx_bytes = BytesIO()
        with zipfile.ZipFile(pptx_bytes, "w") as archive:
            archive.writestr("ppt/slides/slide2.xml", '<p:sld xmlns:p="urn:p"><p:t>Zweite</p:t></p:sld>')
            archive.writestr("ppt/slides/slide1.xml", '<p:sld xmlns:p="urn:p"><p:t>Erste</p:t></p:sld>')
        pptx = self.upload(
            self.module["id"], "folien.pptx", pptx_bytes.getvalue(),
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        detail = self.store.get_material(pptx["id"])
        self.assertEqual([page["text"] for page in detail["pages"]], ["Erste", "Zweite"])

    def test_question_sources_and_image_materials_are_validated(self) -> None:
        unit = self.store.create_unit({"module_id": self.module["id"], "title": "VL 1", "kind": "lecture"})
        source = self.upload(self.module["id"], unit_ids=[unit["id"]])
        question = self.store.create_question({
            "module_id": self.module["id"], "unit_id": unit["id"], "type": "multiple_choice",
            "prompt": "Was steht auf Seite 1?", "options": ["Alpha", "Gamma"], "correct_index": 0,
            "source_material_id": source["id"], "source_page": 1,
        })
        self.assertEqual(question["source_page"], 1)
        with self.assertRaises(ValueError):
            self.store.create_question({
                "module_id": self.module["id"], "type": "multiple_choice", "prompt": "Ungültige Seite?",
                "options": ["A", "B"], "correct_index": 0,
                "source_material_id": source["id"], "source_page": 2,
            })
        with self.assertRaises(ValueError):
            self.store.create_question({
                "module_id": self.module["id"], "type": "free_text", "prompt": "Fremde Quelle?",
                "source_material_id": self.upload(self.other_module["id"])["id"],
            })
        png_bytes = self.png_1x1()
        image = self.upload(self.module["id"], "skizze.png", png_bytes, mime="image/png")
        self.assertEqual(image["extraction_status"], "needs_ocr")
        self.assertEqual(self.store.material_path(image["id"]).read_bytes(), png_bytes)
        image_question = self.store.create_question({
            "module_id": self.module["id"], "type": "image", "prompt": "Beschreibe die Skizze.",
            "image_material_id": image["id"], "answer": "Eine Skizze.",
        })
        self.assertEqual(image_question["image_material_id"], image["id"])
        with self.assertRaises(ValueError):
            self.store.create_question({"module_id": self.module["id"], "type": "image", "prompt": "Ohne Bild"})

        svg = self.upload(self.module["id"], "grafik.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", mime="image/svg+xml")
        self.assertTrue(self.store.material_path(svg["id"]).is_file())
        with self.assertRaisesRegex(ValueError, "PNG, JPEG, WebP oder GIF"):
            self.store.create_question({
                "module_id": self.module["id"], "type": "image", "prompt": "SVG-Frage",
                "image_material_id": svg["id"],
            })

    def test_transcript_edit_invalidates_reviews_and_stale_source_pages(self) -> None:
        pptx_bytes = BytesIO()
        with zipfile.ZipFile(pptx_bytes, "w") as archive:
            archive.writestr("ppt/slides/slide1.xml", '<p:sld xmlns:p="urn:p"><p:t>Seite eins</p:t></p:sld>')
            archive.writestr("ppt/slides/slide2.xml", '<p:sld xmlns:p="urn:p"><p:t>Seite zwei</p:t></p:sld>')
        original_bytes = pptx_bytes.getvalue()
        material = self.upload(
            self.module["id"], "folien.pptx", original_bytes,
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        question = self.store.create_question({
            "module_id": self.module["id"], "type": "free_text", "prompt": "Was zeigt Seite zwei?",
            "source_material_id": material["id"], "source_page": 2, "reviewed": True,
        })

        self.store.update_material(material["id"], {"name": "Vorlesungsfolien.pptx", "unit_ids": []})
        unchanged = self.store.get_question(question["id"])
        self.assertTrue(unchanged["reviewed"])
        self.assertEqual(unchanged["source_page"], 2)

        edited = self.store.update_material(material["id"], {"text": "Neues manuelles Transkript"})
        updated_question = self.store.get_question(question["id"])
        self.assertEqual(edited["id"], material["id"])
        self.assertEqual(edited["page_count"], 1)
        self.assertFalse(updated_question["reviewed"])
        self.assertIsNone(updated_question["source_page"])
        self.assertEqual(updated_question["source_material_id"], material["id"])
        self.assertEqual(self.store.material_path(material["id"]).read_bytes(), original_bytes)

    def test_import_is_all_or_nothing(self) -> None:
        valid = {"type": "multiple_choice", "prompt": "2+2?", "options": ["4", "5"], "correct_index": 0}
        invalid = {"type": "multiple_choice", "prompt": "Fehler?", "options": ["Nur eins"], "correct_index": 0}
        before = len(self.store.snapshot()["questions"])
        with self.assertRaises(ValueError):
            self.store.import_questions(self.module["id"], [valid, invalid])
        self.assertEqual(len(self.store.snapshot()["questions"]), before)
        with self.assertRaises(ValueError):
            self.store.import_questions(self.module["id"], [{**valid, "module_id": self.other_module["id"]}])
        self.assertEqual(len(self.store.snapshot()["questions"]), before)
        inserted = self.store.import_questions(self.module["id"], [valid])
        self.assertEqual(len(inserted), 1)
        self.assertTrue(inserted[0]["reviewed"])

    def test_attempts_calculate_mc_result_and_persist_review_schedule(self) -> None:
        question = self.store.create_question({
            "module_id": self.module["id"], "type": "multiple_choice", "prompt": "Richtig?",
            "options": ["Ja", "Nein"], "correct_index": 0, "topic": "Grundlagen",
        })
        wrong = self.store.record_attempt({
            "question_id": question["id"], "answer": 1, "rating": 2, "duration_seconds": 75,
        })
        self.assertFalse(wrong["correct"])
        self.assertEqual(wrong["rating"], 0)
        after_wrong = self.store.get_question(question["id"])
        self.assertEqual(after_wrong["mastery"], 0)
        self.assertEqual(after_wrong["attempt_count"], 1)
        self.assertGreater(datetime.fromisoformat(after_wrong["due_at"].replace("Z", "+00:00")), datetime.now(timezone.utc))

        right = self.store.record_attempt({
            "question_id": question["id"], "answer": "0", "rating": 0, "duration_seconds": 45,
        })
        self.assertTrue(right["correct"])
        self.assertEqual(right["rating"], 2)
        final = self.store.get_question(question["id"])
        self.assertEqual(final["mastery"], 100)
        self.assertEqual(final["attempt_count"], 2)
        self.assertEqual(right["evaluation_source"], "automatic")
        stats = self.store.stats()
        self.assertEqual(stats["totals"]["attempts"], 2)
        self.assertEqual(stats["topics"][0]["topic"], "Grundlagen")
        self.assertEqual(stats["topics"][0]["secure"], 1)
        self.assertEqual(stats["study_minutes"], 2)
        self.assertEqual(sum(day["attempts"] for day in stats["week"]), 2)

    def test_free_text_attempt_uses_self_rating_and_one_day_review(self) -> None:
        question = self.store.create_question({
            "module_id": self.module["id"], "type": "free_text", "prompt": "Erkläre die Idee.",
            "answer": "Ein kurzer Erwartungshorizont.",
        })
        attempt = self.store.record_attempt({"question_id": question["id"], "answer": "Meine Antwort", "rating": 1})
        self.assertIsNone(attempt["correct"])
        self.assertEqual(self.store.get_question(question["id"])["mastery"], 50)
        due = datetime.fromisoformat(self.store.get_question(question["id"])["due_at"].replace("Z", "+00:00"))
        self.assertGreater(due, datetime.now(timezone.utc) + __import__("datetime").timedelta(hours=23))

    def test_ai_context_includes_actual_attempts_scoped_to_module_and_unit(self) -> None:
        unit_one = self.store.create_unit({"module_id": self.module["id"], "title": "Vorlesung 1", "kind": "lecture"})
        unit_two = self.store.create_unit({"module_id": self.module["id"], "title": "Vorlesung 2", "kind": "lecture"})
        foreign_unit = self.store.create_unit({"module_id": self.other_module["id"], "title": "Fremdmodul", "kind": "lecture"})
        questions = []
        for module_id, unit_id, prompt in (
            (self.module["id"], unit_one["id"], "Q1"),
            (self.module["id"], unit_two["id"], "Q2"),
            (self.other_module["id"], foreign_unit["id"], "Fremde Frage"),
        ):
            question = self.store.create_question({
                "module_id": module_id, "unit_id": unit_id, "type": "free_text", "prompt": prompt,
            })
            questions.append(question)
        first = self.store.record_attempt({
            "question_id": questions[0]["id"], "answer": "Antwort aus Vorlesung 1", "rating": 1,
        })
        second = self.store.record_attempt({
            "question_id": questions[1]["id"], "answer": "Antwort aus Vorlesung 2", "rating": 2,
        })
        self.store.record_attempt({
            "question_id": questions[2]["id"], "answer": "Fremde Antwort", "rating": 0,
        })

        unit_context = self.store.context(self.module["id"], unit_one["id"])
        self.assertEqual([attempt["id"] for attempt in unit_context["attempts"]], [first["id"]])
        self.assertEqual(unit_context["attempts"][0]["answer"], "Antwort aus Vorlesung 1")
        self.assertEqual(unit_context["attempts"][0]["evaluation_source"], "self")

        module_context = self.store.context(self.module["id"])
        self.assertEqual({attempt["id"] for attempt in module_context["attempts"]}, {first["id"], second["id"]})
        self.assertNotIn("Fremde Antwort", {attempt["answer"] for attempt in module_context["attempts"]})

    def test_module_delete_cascades_rows_and_original_files(self) -> None:
        unit = self.store.create_unit({"module_id": self.module["id"], "title": "VL", "kind": "lecture"})
        material = self.upload(self.module["id"], unit_ids=[unit["id"]])
        question = self.store.create_question({
            "module_id": self.module["id"], "unit_id": unit["id"], "type": "free_text", "prompt": "Frage",
        })
        self.store.record_attempt({"question_id": question["id"], "answer": "x", "rating": 2})
        file_path = self.store.material_path(material["id"])
        self.assertTrue(file_path.exists())
        self.store.delete_module(self.module["id"])
        self.assertFalse(file_path.exists())
        self.assertEqual(self.store.snapshot()["units"], [])
        self.assertEqual(self.store.snapshot()["materials"], [])
        self.assertEqual(self.store.snapshot()["questions"], [])
        self.assertEqual(self.store.snapshot()["attempts"], [])

    def test_delete_material_guards_image_questions_and_invalidates_source_questions(self) -> None:
        png_bytes = self.png_1x1()
        image = self.upload(self.module["id"], "bild.png", png_bytes, mime="image/png")
        image_question = self.store.create_question({
            "module_id": self.module["id"], "type": "image", "prompt": "Was ist abgebildet?",
            "image_material_id": image["id"],
        })
        with self.assertRaisesRegex(ValueError, "Lösche zuerst die Bildfragen oder ordne ihnen ein anderes Bild zu"):
            self.store.delete_material(image["id"])
        self.assertTrue(self.store.material_path(image["id"]).is_file())
        self.assertEqual(self.store.get_question(image_question["id"])["image_material_id"], image["id"])

        source = self.upload(self.module["id"], "quelle.txt", b"Text mit einer Seite")
        source_question = self.store.create_question({
            "module_id": self.module["id"], "type": "free_text", "prompt": "Erkläre den Inhalt.",
            "source_material_id": source["id"], "source_page": 1, "reviewed": True,
        })
        source_path = self.store.material_path(source["id"])
        self.store.delete_material(source["id"])
        after_delete = self.store.get_question(source_question["id"])
        self.assertIsNone(after_delete["source_material_id"])
        self.assertIsNone(after_delete["source_page"])
        self.assertFalse(after_delete["reviewed"])
        self.assertFalse(source_path.exists())

    def test_backup_contains_database_and_original_material(self) -> None:
        material = self.upload(self.module["id"], "notizen.txt", "Grüße aus Köln".encode("utf-8"))
        question = self.store.create_question({
            "module_id": self.module["id"], "type": "free_text", "prompt": "Was bedeutet der Text?",
            "answer": "Eine Begrüßung.", "source_material_id": material["id"], "source_page": 1,
        })
        attempt = self.store.record_attempt({"question_id": question["id"], "answer": "Eine Begrüßung.", "rating": 2, "duration_seconds": 90})
        archive_bytes = self.store.backup()
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            names = archive.namelist()
            self.assertIn("lernraum.sqlite3", names)
            material_name = f"materials/{Path(self.store.material_path(material['id'])).name}"
            self.assertIn(material_name, names)
            self.assertEqual(archive.read(material_name), "Grüße aus Köln".encode("utf-8"))
            restored_dir = Path(self.temp.name) / "restored"
            restored_dir.mkdir()
            archive.extractall(restored_dir)

        restored = Store(restored_dir, seed=False)
        restored_state = restored.snapshot()
        self.assertEqual([row["id"] for row in restored_state["modules"]], [row["id"] for row in self.store.snapshot()["modules"]])
        self.assertEqual(restored.get_material(material["id"])["text"], "Grüße aus Köln")
        self.assertEqual(restored.material_path(material["id"]).read_bytes(), "Grüße aus Köln".encode("utf-8"))
        self.assertEqual(restored.get_question(question["id"])["attempt_count"], 1)
        self.assertEqual(restored_state["attempts"][0]["id"], attempt["id"])


if __name__ == "__main__":
    unittest.main()
