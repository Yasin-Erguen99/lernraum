"""Lernraum: local HTTP application. Run python app.py --open."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
MAX_BODY = 57 * 1024 * 1024


def load_env(path: Path) -> None:
    """Load local configuration without overriding the user's environment."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith(("LERNRAUM_", "OPENAI_")):
            os.environ.setdefault(key, value.strip().strip("\"'"))


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store):
        self.store = store
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "Lernraum/1.0"

    def log_message(self, fmt, *args):
        # Log method and route only, never request bodies or material contents.
        if os.environ.get("LERNRAUM_VERBOSE") == "1":
            print(f"[{self.log_date_time_string()}] {self.command} {urlsplit(self.path).path}", flush=True)

    def _headers(self, status, content_type, length, disposition=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()

    def _json(self, obj, status=200):
        content = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(content))
        self.wfile.write(content)

    def _body(self):
        if self.headers.get("X-Lernraum-Client") != "local":
            raise PermissionError("Dieser Zugriff benötigt den lokalen Lernraum-Client.")
        origin = self.headers.get("Origin")
        port = self.server.server_port
        if origin and origin not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            raise PermissionError("Anfragen von anderen Webseiten sind nicht erlaubt.")
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            raise ValueError("Bitte JSON senden (Content-Type: application/json).")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Ungültige Größe der Anfrage.") from None
        if not 0 < length <= MAX_BODY:
            raise ValueError("Die Anfrage ist leer oder zu groß. Dateien dürfen höchstens 40 MB groß sein.")
        try:
            value = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("Die Anfrage enthält kein gültiges JSON.") from None
        if not isinstance(value, dict):
            raise ValueError("Die Anfrage muss ein JSON-Objekt sein.")
        return value

    def _guard(self):
        host = self.headers.get("Host", "")
        port = self.server.server_port
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            raise PermissionError("Lernraum ist nur über die lokale Adresse erreichbar.")

    def _run(self):
        try:
            self._guard()
            self._dispatch()
        except PermissionError as exc:
            self._json({"error": str(exc)}, 403)
        except KeyError:
            self._json({"error": "Dieser Eintrag wurde nicht gefunden."}, 404)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            self._json({"error": "Die Aktion konnte nicht abgeschlossen werden. Bitte versuche es erneut."}, 500)

    do_GET = do_POST = do_PATCH = do_DELETE = _run

    def _dispatch(self):
        import ai

        store = self.server.store
        url = urlsplit(self.path)
        path = unquote(url.path)
        parts = path.strip("/").split("/")
        params = parse_qs(url.query)
        method = self.command

        if method == "GET":
            if path == "/api/health":
                return self._json({"ok": True, "app": "Lernraum"})
            if path == "/api/state":
                return self._json(store.snapshot())
            if path == "/api/stats":
                return self._json(store.stats())
            if path == "/api/ai/status":
                return self._json(ai.status())
            if path == "/api/answers":
                return self._json({"answers": store.list_answers(
                    module_id=params.get("module_id", [None])[0],
                    unit_id=params.get("unit_id", [None])[0],
                    status=params.get("status", ["pending"])[0],
                )})
            if len(parts) == 3 and parts[:2] == ["api", "answers"]:
                return self._json(store.get_answer(parts[2]))
            if path == "/api/context":
                module_id = params.get("module_id", [None])[0]
                if not module_id:
                    raise ValueError("Bitte eine Modul-ID angeben.")
                return self._json(store.context(module_id, params.get("unit_id", [None])[0]))
            if path == "/api/questions/export":
                module_id = params.get("module_id", [None])[0]
                if module_id:
                    store.get_module(module_id)
                questions = store.snapshot()["questions"]
                if module_id:
                    questions = [q for q in questions if q["module_id"] == module_id]
                return self._json({"questions": questions})
            if path == "/api/backup":
                content = store.backup()
                self._headers(200, "application/zip", len(content), 'attachment; filename="lernraum-backup.zip"')
                return self.wfile.write(content)
            if len(parts) in (3, 4) and parts[:2] == ["api", "materials"]:
                material = store.get_material(parts[2])
                if len(parts) == 3:
                    return self._json(material)
                if parts[3] == "file":
                    file = store.material_path(parts[2])
                    safe_inline = material["mime"] in {"application/pdf", "image/png", "image/jpeg", "image/webp", "image/gif"}
                    mode = "inline" if safe_inline else "attachment"
                    self._headers(200, material["mime"] if safe_inline else "application/octet-stream", file.stat().st_size, f"{mode}; filename*=UTF-8''{quote(material['name'], safe='')}")
                    with file.open("rb") as handle:
                        while chunk := handle.read(1024 * 1024):
                            self.wfile.write(chunk)
                    return
            if not path.startswith("/api/"):
                if path == "/":
                    file = WEB / "index.html"
                else:
                    file = (WEB / path.lstrip("/")).resolve()
                    if not file.is_relative_to(WEB.resolve()):
                        raise KeyError(path)
                if not file.is_file():
                    raise KeyError(path)
                content = file.read_bytes()
                mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                if mime.startswith("text/") or file.suffix == ".js":
                    mime += "; charset=utf-8"
                self._headers(200, mime, len(content))
                return self.wfile.write(content)

        if method in {"POST", "PATCH", "DELETE"}:
            data = self._body()
            if method == "POST":
                creators = {
                    "/api/modules": store.create_module,
                    "/api/units": store.create_unit,
                    "/api/materials": store.upload_material,
                    "/api/questions": store.create_question,
                    "/api/attempts": store.record_attempt,
                    "/api/answers": store.submit_answer,
                }
                if path in creators:
                    return self._json(creators[path](data), 201)
                if len(parts) == 4 and parts[:2] == ["api", "answers"] and parts[3] == "review":
                    return self._json(store.review_answer(parts[2], data))
                if len(parts) == 4 and parts[:2] == ["api", "attempts"] and parts[3] == "review":
                    return self._json(store.review_attempt(parts[2], data))
                if path == "/api/questions/import":
                    if not isinstance(data.get("questions"), list):
                        raise ValueError("Bitte eine Fragenliste angeben.")
                    questions = store.import_questions(data.get("module_id"), data["questions"], data.get("unit_id"))
                    return self._json({"questions": questions}, 201)
                if path == "/api/ai/generate":
                    context = store.context(data.get("module_id"), data.get("unit_id") or None)
                    return self._json({"questions": ai.generate(context, data)})
                if path == "/api/ai/evaluate":
                    answer = data.get("answer")
                    if not isinstance(answer, str) or not answer.strip() or len(answer) > 20000:
                        raise ValueError("Bitte eine Antwort mit höchstens 20.000 Zeichen eingeben.")
                    return self._json(ai.evaluate(store.get_question(data.get("question_id")), answer))
            if len(parts) == 3 and parts[0] == "api" and parts[1] in {"modules", "units", "materials", "questions"}:
                name = {"modules": "module", "units": "unit", "materials": "material", "questions": "question"}[parts[1]]
                if method == "PATCH":
                    return self._json(getattr(store, f"update_{name}")(parts[2], data))
                if method == "DELETE":
                    getattr(store, f"delete_{name}")(parts[2])
                    return self._json({"ok": True})
        raise KeyError(path)


def main():
    parser = argparse.ArgumentParser(description="Lernraum lokal starten")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data")
    parser.add_argument("--open", action="store_true", help="Browser automatisch öffnen")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Der Port muss zwischen 1024 und 65535 liegen.")
    load_env(ROOT / ".env")
    from storage import Store

    store = Store(args.data_dir)
    try:
        server = LocalServer(("127.0.0.1", args.port), store)
    except OSError as exc:
        print(f"Lernraum konnte Port {args.port} nicht öffnen: {exc}\nVersuche: python app.py --port 8766 --open", file=sys.stderr)
        return 1
    address = f"http://127.0.0.1:{args.port}"
    print(f"\n  Lernraum\n  Lokal: {address}\n  Daten: {args.data_dir.resolve()}\n  Beenden: Strg+C\n", flush=True)
    if args.open:
        threading.Timer(0.7, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nLernraum beendet. Deine Daten sind gespeichert.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
