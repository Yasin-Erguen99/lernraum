#!/usr/bin/env python3
"""Command-line client for the local Lernraum study app."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


DEFAULT_URL = "http://127.0.0.1:8765"
CLIENT_HEADER = "X-Lernraum-Client"


class LernraumError(Exception):
    """An actionable error safe to show on the command line."""


def _base_url(raw_url: str) -> str:
    try:
        parsed = urlsplit(raw_url)
        _ = parsed.port  # force validation of malformed or out-of-range ports
    except ValueError:
        raise LernraumError("Ungültige Serveradresse oder Portnummer.") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise LernraumError("Ungültige Serveradresse. Erwartet wird eine HTTP(S)-URL.")
    if parsed.username or parsed.password:
        raise LernraumError("Die Serveradresse darf keine Zugangsdaten enthalten.")
    if parsed.query or parsed.fragment:
        raise LernraumError("Die Serveradresse darf keinen Query-String oder Fragment enthalten.")
    return raw_url.rstrip("/")


def api_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    binary: bool = False,
) -> Any:
    """Make one request to the local API and turn failures into useful errors."""
    url = _base_url(base_url) + path
    headers = {"Accept": "application/octet-stream" if binary else "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if method in {"POST", "PATCH", "DELETE"}:
        headers[CLIENT_HEADER] = "local"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read()
            if binary:
                return body
    except HTTPError as exc:
        detail = ""
        try:
            error_body = exc.read(64 * 1024).decode("utf-8", errors="replace")
            error_json = json.loads(error_body)
            if isinstance(error_json, dict) and error_json.get("error"):
                detail = str(error_json["error"])
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        if not detail:
            detail = f"HTTP {exc.code} {exc.reason}"
        if exc.code == 404:
            detail += " Prüfe, ob Lernraum läuft und die angegebene ID stimmt."
        raise LernraumError(detail) from None
    except URLError as exc:
        reason = getattr(exc, "reason", "unbekannter Netzwerkfehler")
        raise LernraumError(
            f"Lernraum unter {_base_url(base_url)} ist nicht erreichbar ({reason}). "
            "Starte zuerst den App-Server."
        ) from None
    except TimeoutError:
        raise LernraumError("Zeitüberschreitung beim Aufruf des Lernraum-Servers.") from None

    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise LernraumError("Der Server hat keine gültige JSON-Antwort zurückgegeben.") from None


def print_json(value: Any, *, pretty: bool = False) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2 if pretty else None, sort_keys=pretty))


def write_json(value: Any, output: str | None, *, pretty: bool = False) -> None:
    if not output or output == "-":
        print_json(value, pretty=pretty)
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_json({"saved_to": str(path.resolve()), "bytes": path.stat().st_size})


def _add_optional_fields(args: argparse.Namespace, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(args, field) for field in fields if getattr(args, field) is not None}


def _state(base_url: str) -> dict[str, Any]:
    state = api_request(base_url, "/api/state")
    if not isinstance(state, dict):
        raise LernraumError("Der Serverzustand hat ein unerwartetes Format.")
    return state


def _matches_unit(record: dict[str, Any], unit_id: str | None) -> bool:
    if unit_id is None:
        return True
    if record.get("unit_id") == unit_id:
        return True
    return unit_id in record.get("unit_ids", [])


def _safe_filename(name: str) -> str:
    # A server-provided display name must not choose a directory for the download.
    filename = re.split(r"[/\\]", name)[-1]
    if filename in {"", ".", ".."}:
        return "material"
    return filename


def _write_download(path: Path, content: bytes, force: bool) -> None:
    if path.exists() and not force:
        raise LernraumError(f"{path} existiert bereits. Nutze --force, um sie zu überschreiben.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _read_utf8_file(path_value: str, label: str) -> str:
    path = Path(path_value)
    try:
        # utf-8-sig accepts ordinary UTF-8 as well as files saved with a BOM.
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise LernraumError(f"{label} {path} kann nicht gelesen werden: {exc}") from None
    except UnicodeError:
        raise LernraumError(f"{label} {path} ist keine gültige UTF-8-Datei.") from None


def _answer_text(args: argparse.Namespace, *, label: str) -> str:
    inline = getattr(args, "answer", getattr(args, "feedback", None))
    file_path = getattr(args, "answer_file", getattr(args, "feedback_file", None))
    value = inline if inline is not None else _read_utf8_file(file_path, label)
    if not value.strip():
        raise LernraumError(f"{label.capitalize()} darf nicht leer sein.")
    return value


def _question_answer_for_api(question: dict[str, Any], answer: str) -> str:
    if question.get("type") != "multiple_choice":
        return answer
    # An integer is treated as a zero-based option index. Text answers are preserved.
    if answer.isdecimal():
        index = int(answer)
        options = question.get("options") or []
        if index < 0 or index >= len(options):
            raise LernraumError(
                f"Optionsindex {index} liegt außerhalb der verfügbaren Optionen (0 bis {len(options) - 1})."
            )
        return str(index)
    return answer


def _is_due(due_at: Any, now: datetime) -> bool:
    if not due_at:
        return False
    try:
        parsed = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed <= now
    except ValueError:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lernraum",
        description="Lernraum über die lokale HTTP-API verwalten. Antworten sind standardmäßig JSON.",
        epilog=(
            "Beispiel: python cli.py --url http://127.0.0.1:8765 modules list\n"
            "Der Lernraum-Server muss laufen. Die URL kann auch über LERNRAUM_URL gesetzt werden."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", default=os.environ.get("LERNRAUM_URL", DEFAULT_URL), help="Server-URL (Standard: %(default)s)")
    parser.add_argument("--pretty", action="store_true", help="JSON lesbar mit Einrückungen ausgeben")
    roots = parser.add_subparsers(dest="command", required=True)

    modules = roots.add_parser("modules", help="Module verwalten")
    module_commands = modules.add_subparsers(dest="action", required=True)
    module_commands.add_parser("list", help="alle Module anzeigen")
    mod_add = module_commands.add_parser("add", help="Modulakte anlegen")
    mod_add.add_argument("--name", required=True)
    mod_add.add_argument("--code")
    mod_add.add_argument("--description")
    mod_add.add_argument("--color", choices=("violet", "blue", "green", "orange", "rose"))
    mod_add.add_argument("--semester")
    mod_update = module_commands.add_parser("update", help="Modulakte ändern")
    mod_update.add_argument("module_id")
    mod_update.add_argument("--name")
    mod_update.add_argument("--code")
    mod_update.add_argument("--description")
    mod_update.add_argument("--color", choices=("violet", "blue", "green", "orange", "rose"))
    mod_update.add_argument("--semester")

    units = roots.add_parser("units", help="Vorlesungen und Praktika verwalten")
    unit_commands = units.add_subparsers(dest="action", required=True)
    unit_list = unit_commands.add_parser("list", help="Einheiten anzeigen")
    unit_list.add_argument("--module", dest="module_id")
    unit_add = unit_commands.add_parser("add", help="Vorlesung, Praktikum oder andere Einheit anlegen")
    unit_add.add_argument("--module", dest="module_id", required=True)
    unit_add.add_argument("--title", required=True)
    unit_add.add_argument("--kind", choices=("lecture", "practical", "other"), default="lecture")
    unit_add.add_argument("--date", help="Datum/Zeit, bevorzugt ISO-Format")
    unit_add.add_argument("--notes")

    materials = roots.add_parser("materials", help="Materialien verwalten")
    material_commands = materials.add_subparsers(dest="action", required=True)
    mat_list = material_commands.add_parser("list", help="Materialien anzeigen")
    mat_list.add_argument("--module", dest="module_id")
    mat_list.add_argument("--unit", dest="unit_id")
    mat_upload = material_commands.add_parser("upload", help="Datei hochladen und für die KI-Auswertung bereitstellen")
    mat_upload.add_argument("--module", dest="module_id", required=True)
    mat_upload.add_argument("--unit", dest="unit_ids", action="append", default=[], help="Einheit-ID; mehrfach möglich")
    mat_upload.add_argument("--file", required=True, help="Pfad zur Originaldatei")
    mat_upload.add_argument("--name", help="Anzeigename; Standard ist der Dateiname")
    mat_upload.add_argument("--mime", help="MIME-Typ; wird sonst aus der Dateiendung abgeleitet")
    mat_show = material_commands.add_parser("show", help="Metadaten und extrahierten Text anzeigen")
    mat_show.add_argument("material_id")
    mat_download = material_commands.add_parser("download", help="Originaldatei herunterladen")
    mat_download.add_argument("material_id")
    mat_download.add_argument("--output", help="Zielpfad; Standard ist der Materialname")
    mat_download.add_argument("--force", action="store_true", help="vorhandene Zieldatei überschreiben")

    questions = roots.add_parser("questions", help="Fragen verwalten und übertragen")
    question_commands = questions.add_subparsers(dest="action", required=True)
    q_list = question_commands.add_parser("list", help="Fragen anzeigen")
    q_list.add_argument("--module", dest="module_id")
    q_list.add_argument("--unit", dest="unit_id")
    q_add = question_commands.add_parser("add", help="eine eigene Frage anlegen")
    q_add.add_argument("--module", dest="module_id", required=True)
    q_add.add_argument("--unit", dest="unit_id")
    q_add.add_argument("--type", dest="question_type", choices=("multiple_choice", "free_text", "image"), required=True)
    q_add.add_argument("--prompt", required=True)
    q_add.add_argument("--option", dest="options", action="append", default=[], help="Antwortoption; mehrfach für Multiple Choice")
    q_add.add_argument("--correct-index", type=int)
    q_add.add_argument("--answer", help="Musterlösung oder erwartete Antwort")
    q_add.add_argument("--explanation")
    q_add.add_argument("--topic")
    q_add.add_argument("--difficulty", type=int, choices=(1, 2, 3), default=2)
    q_add.add_argument("--source-material-id")
    q_add.add_argument("--source-page", type=int)
    q_add.add_argument("--image-material-id")
    q_add.add_argument("--ai-generated", action="store_true", help="Frage als KI-generiert kennzeichnen")
    q_add.add_argument("--reviewed", action=argparse.BooleanOptionalAction, default=None, help="Prüfstatus setzen")
    q_import = question_commands.add_parser("import", help="geprüfte JSON-Fragen importieren")
    q_import.add_argument("file", help="JSON-Datei mit einer Liste oder einem questions-Array")
    q_import.add_argument("--module", dest="module_id", required=True)
    q_import.add_argument("--unit", dest="unit_id")
    q_import.add_argument("--reviewed", action="store_true", help="bestätigt: Fragen, Lösungen und Quellen wurden geprüft")
    q_export = question_commands.add_parser("export", help="Fragen eines Moduls als JSON exportieren")
    q_export.add_argument("--module", dest="module_id", required=True)
    q_export.add_argument("--output", help="Dateipfad; ohne Angabe wird JSON ausgegeben")

    context = roots.add_parser("context", help="KI-lesbaren Kontext samt Quell-IDs exportieren")
    context.add_argument("--module", dest="module_id", required=True)
    context.add_argument("--unit", dest="unit_id")
    context.add_argument("--output", help="JSON-Datei; ohne Angabe wird JSON ausgegeben")

    progress = roots.add_parser("progress", help="Lernfortschritt aus Fragen und Antworten zusammenfassen")
    progress.add_argument("--module", dest="module_id")

    backups = roots.add_parser("backup", help="lokales Backup herunterladen")
    backup_commands = backups.add_subparsers(dest="action", required=True)
    backup_download = backup_commands.add_parser("download", help="Datenbank und Originalmaterialien als ZIP sichern")
    backup_download.add_argument("--output", default="lernraum-backup.zip", help="Zielpfad (Standard: %(default)s)")
    backup_download.add_argument("--force", action="store_true", help="vorhandene Zieldatei überschreiben")

    practice = roots.add_parser("practice", help="Lernversuche aufzeichnen")
    practice_commands = practice.add_subparsers(dest="action", required=True)
    record = practice_commands.add_parser("record", help="Antwort auf eine Frage speichern")
    record.add_argument("--question", dest="question_id", required=True)
    record.add_argument("--answer", required=True, help="bei Multiple Choice Optionsindex (ab 0) oder exakter Optionstext")
    record.add_argument("--rating", type=int, choices=(0, 1, 2), help="Selbsteinschätzung für Freitext/Bild: 0 falsch, 1 teilweise, 2 richtig")
    record.add_argument("--duration", type=int, dest="duration_seconds", help="Bearbeitungszeit in Sekunden")
    record.add_argument("--source", dest="evaluation_source", choices=("self", "automatic", "ai"), default="self")

    answers = roots.add_parser("answers", help="Freitext- und Bildantworten im Chat prüfen lassen")
    answer_commands = answers.add_subparsers(dest="action", required=True)
    answer_list = answer_commands.add_parser("list", help="Antworten zur Prüfung oder bereits geprüfte anzeigen")
    answer_list.add_argument("--module", dest="module_id")
    answer_list.add_argument("--unit", dest="unit_id")
    answer_list.add_argument("--status", choices=("pending", "reviewed", "all"), default="pending")
    answer_list.add_argument("--output", help="JSON-Datei; ohne Angabe wird JSON ausgegeben")
    answer_show = answer_commands.add_parser("show", help="Antwort, Frage und Quellenmaterial anzeigen")
    answer_show.add_argument("answer_id")
    answer_show.add_argument("--output", help="JSON-Datei; ohne Angabe wird JSON ausgegeben")
    answer_submit = answer_commands.add_parser("submit", help="Freitext- oder Bildantwort zur Prüfung vormerken")
    answer_submit.add_argument("--question", dest="question_id", required=True)
    answer_input = answer_submit.add_mutually_exclusive_group(required=True)
    answer_input.add_argument("--answer", help="Antworttext")
    answer_input.add_argument("--answer-file", help="Antworttext aus einer UTF-8-Datei lesen")
    answer_submit.add_argument("--duration", type=int, dest="duration_seconds", help="Bearbeitungszeit in Sekunden")
    for command, help_text, id_field in (
        ("review", "Chat-Prüfung mit Feedback speichern", "answer_id"),
        ("review-attempt", "Bereits selbstbewertete Freitextantwort nachprüfen, ohne einen neuen Versuch anzulegen", "attempt_id"),
    ):
        answer_review = answer_commands.add_parser(command, help=help_text)
        answer_review.add_argument(id_field)
        answer_review.add_argument("--rating", type=int, choices=(0, 1, 2), required=True, help="0 falsch, 1 teilweise richtig, 2 richtig")
        feedback_input = answer_review.add_mutually_exclusive_group(required=True)
        feedback_input.add_argument("--feedback", help="Begründendes Feedback")
        feedback_input.add_argument("--feedback-file", help="Feedback aus einer UTF-8-Datei lesen")
        answer_review.add_argument("--reviewer", default="ChatGPT (im Chat)", help="Prüfername (Standard: %(default)s)")

    return parser


def run(args: argparse.Namespace) -> Any:
    base_url = _base_url(args.url)

    if args.command == "modules":
        if args.action == "list":
            return _state(base_url).get("modules", [])
        if args.action == "add":
            payload = {"name": args.name}
            payload.update(_add_optional_fields(args, ("code", "description", "color", "semester")))
            return api_request(base_url, "/api/modules", method="POST", payload=payload)
        payload = _add_optional_fields(args, ("name", "code", "description", "color", "semester"))
        if not payload:
            raise LernraumError("Für modules update muss mindestens ein Feld gesetzt sein.")
        return api_request(base_url, f"/api/modules/{quote(args.module_id, safe='')}", method="PATCH", payload=payload)

    if args.command == "units":
        if args.action == "list":
            units_data = _state(base_url).get("units", [])
            if args.module_id:
                units_data = [unit for unit in units_data if unit.get("module_id") == args.module_id]
            return units_data
        payload = {"module_id": args.module_id, "title": args.title, "kind": args.kind}
        payload.update(_add_optional_fields(args, ("date", "notes")))
        return api_request(base_url, "/api/units", method="POST", payload=payload)

    if args.command == "materials":
        if args.action == "list":
            items = _state(base_url).get("materials", [])
            if args.module_id:
                items = [item for item in items if item.get("module_id") == args.module_id]
            if args.unit_id:
                items = [item for item in items if _matches_unit(item, args.unit_id)]
            return items
        if args.action == "upload":
            file_path = Path(args.file)
            try:
                file_bytes = file_path.read_bytes()
            except OSError as exc:
                raise LernraumError(f"Datei {file_path} kann nicht gelesen werden: {exc}") from None
            mime = args.mime or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            payload = {
                "module_id": args.module_id,
                "unit_ids": args.unit_ids,
                "name": args.name or file_path.name,
                "mime": mime,
                "content_base64": base64.b64encode(file_bytes).decode("ascii"),
            }
            return api_request(base_url, "/api/materials", method="POST", payload=payload)
        if args.action == "show":
            return api_request(base_url, f"/api/materials/{quote(args.material_id, safe='')}")
        material = api_request(base_url, f"/api/materials/{quote(args.material_id, safe='')}")
        name = _safe_filename(str(material.get("name") or "material"))
        output = Path(args.output) if args.output else Path(name)
        content = api_request(base_url, f"/api/materials/{quote(args.material_id, safe='')}/file", binary=True)
        _write_download(output, content, args.force)
        return {"saved_to": str(output.resolve()), "bytes": len(content), "name": name}

    if args.command == "questions":
        if args.action == "list":
            items = _state(base_url).get("questions", [])
            if args.module_id:
                items = [item for item in items if item.get("module_id") == args.module_id]
            if args.unit_id:
                items = [item for item in items if item.get("unit_id") == args.unit_id]
            return items
        if args.action == "add":
            payload: dict[str, Any] = {
                "module_id": args.module_id,
                "unit_id": args.unit_id,
                "type": args.question_type,
                "prompt": args.prompt,
                "options": args.options,
                "correct_index": args.correct_index,
                "answer": args.answer,
                "explanation": args.explanation,
                "topic": args.topic,
                "difficulty": args.difficulty,
                "source_material_id": args.source_material_id,
                "source_page": args.source_page,
                "image_material_id": args.image_material_id,
                "is_ai": args.ai_generated,
            }
            if args.reviewed is not None:
                payload["reviewed"] = args.reviewed
            return api_request(base_url, "/api/questions", method="POST", payload=payload)
        if args.action == "import":
            if not args.reviewed:
                raise LernraumError(
                    "Import abgebrochen. Prüfe jede Frage, Lösung und source_material_id/source_page und wiederhole mit --reviewed."
                )
            try:
                raw = Path(args.file).read_text(encoding="utf-8")
                document = json.loads(raw)
            except OSError as exc:
                raise LernraumError(f"JSON-Datei {args.file} kann nicht gelesen werden: {exc}") from None
            except json.JSONDecodeError as exc:
                raise LernraumError(f"Ungültiges JSON in {args.file}, Zeile {exc.lineno}, Spalte {exc.colno}.") from None
            questions_data = document.get("questions") if isinstance(document, dict) else document
            if not isinstance(questions_data, list):
                raise LernraumError("Die JSON-Datei muss eine Fragenliste oder ein Objekt mit 'questions' enthalten.")
            if not questions_data:
                raise LernraumError("Die JSON-Datei enthält keine Fragen.")
            if not all(isinstance(question, dict) for question in questions_data):
                raise LernraumError("Jeder Eintrag im questions-Array muss ein JSON-Objekt sein.")
            # The explicit CLI acknowledgment is also reflected in the saved records.
            questions_data = [dict(question, reviewed=True) for question in questions_data]
            return api_request(
                base_url,
                "/api/questions/import",
                method="POST",
                payload={"module_id": args.module_id, "unit_id": args.unit_id, "questions": questions_data},
            )
        query = urlencode({"module_id": args.module_id})
        result = api_request(base_url, f"/api/questions/export?{query}")
        write_json(result, args.output, pretty=args.pretty)
        return None

    if args.command == "context":
        query: dict[str, str] = {"module_id": args.module_id}
        if args.unit_id:
            query["unit_id"] = args.unit_id
        result = api_request(base_url, f"/api/context?{urlencode(query)}")
        write_json(result, args.output, pretty=args.pretty)
        return None

    if args.command == "progress":
        state = _state(base_url)
        modules_data = state.get("modules", [])
        questions_data = state.get("questions", [])
        attempts_data = state.get("attempts", [])
        if args.module_id:
            modules_data = [module for module in modules_data if module.get("id") == args.module_id]
            if not modules_data:
                raise LernraumError(f"Modul {args.module_id} wurde nicht gefunden.")
        now = datetime.now(timezone.utc)
        report = []
        for module in modules_data:
            module_questions = [q for q in questions_data if q.get("module_id") == module.get("id")]
            question_ids = {q.get("id") for q in module_questions}
            module_attempts = [a for a in attempts_data if a.get("question_id") in question_ids]
            mastery = [q.get("mastery") for q in module_questions if isinstance(q.get("mastery"), (int, float))]
            report.append(
                {
                    "module_id": module.get("id"),
                    "module": module.get("name"),
                    "question_count": len(module_questions),
                    "due_count": sum(1 for q in module_questions if _is_due(q.get("due_at"), now)),
                    "mastery_average": round(sum(mastery) / len(mastery), 1) if mastery else None,
                    "mastery_counts": {
                        str(level): sum(1 for q in module_questions if q.get("mastery") == level)
                        for level in (0, 50, 100)
                    },
                    "attempt_count": len(module_attempts),
                    "correct_attempt_count": sum(1 for attempt in module_attempts if attempt.get("correct") is True),
                }
            )
        return {"as_of": now.isoformat(), "modules": report, "server_stats": state.get("stats", {})}

    if args.command == "backup" and args.action == "download":
        content = api_request(base_url, "/api/backup", binary=True)
        output = Path(args.output)
        _write_download(output, content, args.force)
        return {"saved_to": str(output.resolve()), "bytes": len(content)}

    if args.command == "practice" and args.action == "record":
        state = _state(base_url)
        question = next((q for q in state.get("questions", []) if q.get("id") == args.question_id), None)
        if question is None:
            raise LernraumError(f"Frage {args.question_id} wurde nicht gefunden.")
        rating = args.rating
        if question.get("type") == "multiple_choice":
            # The server calculates MC correctness and rating from the selected option.
            answer = _question_answer_for_api(question, args.answer)
            if rating is None:
                rating = 2
        else:
            answer = args.answer
            if rating is None:
                raise LernraumError("Für Freitext- und Bildfragen ist --rating 0, 1 oder 2 erforderlich.")
        payload = {
            "question_id": args.question_id,
            "answer": answer,
            "rating": rating,
            "evaluation_source": args.evaluation_source,
        }
        if args.duration_seconds is not None:
            payload["duration_seconds"] = args.duration_seconds
        return api_request(base_url, "/api/attempts", method="POST", payload=payload)

    if args.command == "answers":
        if args.action == "list":
            query = {"status": args.status}
            if args.module_id:
                query["module_id"] = args.module_id
            if args.unit_id:
                query["unit_id"] = args.unit_id
            result = api_request(base_url, f"/api/answers?{urlencode(query)}")
            write_json(result, args.output, pretty=args.pretty)
            return None
        if args.action == "show":
            result = api_request(base_url, f"/api/answers/{quote(args.answer_id, safe='')}")
            write_json(result, args.output, pretty=args.pretty)
            return None
        if args.action == "submit":
            answer = _answer_text(args, label="Antwortdatei") if args.answer_file else _answer_text(args, label="Antwort")
            payload: dict[str, Any] = {"question_id": args.question_id, "answer": answer}
            if args.duration_seconds is not None:
                payload["duration_seconds"] = args.duration_seconds
            return api_request(base_url, "/api/answers", method="POST", payload=payload)
        feedback = _answer_text(args, label="Feedbackdatei") if args.feedback_file else _answer_text(args, label="Feedback")
        reviewer = args.reviewer.strip()
        if not reviewer:
            raise LernraumError("Der Prüfername darf nicht leer sein.")
        return api_request(
            base_url,
            f"/api/attempts/{quote(args.attempt_id, safe='')}/review" if args.action == "review-attempt" else f"/api/answers/{quote(args.answer_id, safe='')}/review",
            method="POST",
            payload={"rating": args.rating, "feedback": feedback, "reviewer": reviewer},
        )

    raise LernraumError("Unbekannter Befehl.")


def main(argv: list[str] | None = None) -> int:
    # Keep machine-readable output UTF-8 on Windows, including Greek/math symbols.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
        if result is not None:
            print_json(result, pretty=args.pretty)
        return 0
    except LernraumError as exc:
        print(f"lernraum: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"lernraum: Dateioperation fehlgeschlagen: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
