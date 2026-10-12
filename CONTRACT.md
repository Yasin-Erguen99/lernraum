# Lernraum: shared contract

Local browser application, Python 3.12+ standard-library HTTP server on `127.0.0.1:8765`, vanilla browser JS/CSS. All user content in `.data/` (SQLite and original uploads). No deployment. No changes under project `sources/`.

## HTTP API

Responses are JSON objects, errors `{ "error": "message" }` with appropriate HTTP status. Requests use JSON. Mutating browser requests send `X-Lernraum-Client: local`. CLI sends the same header. IDs are UUID strings. Dates UTC ISO strings.

- `GET /api/state` -> `{modules, units, materials, questions, attempts, answer_submissions, stats}`. Material bodies omitted. Pending answer submissions are separate from graded attempts and do not affect mastery, accuracy, or review scheduling. `GET /api/stats` -> stats, including `pending_answers`.
- `POST /api/modules` with `{name, code?, description?, color?, semester?}` -> module. `PATCH /api/modules/<id>` and `DELETE` supported.
- `POST /api/units` with `{module_id,title,kind:"lecture"|"practical"|"other",date?,notes?}` -> unit. PATCH/DELETE supported.
- `POST /api/materials` with `{module_id,unit_ids:[],name,mime?,content_base64}` -> metadata. `GET /api/materials/<id>` -> metadata plus `text`, `pages:[{page,text}]`, `extraction_status`, `extraction_message`. PATCH supports name, unit_ids and manually supplied text. DELETE supported. `GET /api/materials/<id>/file` returns original.
- `POST /api/questions` -> question. `PATCH /api/questions/<id>` and DELETE supported.
- `POST /api/questions/import` with `{module_id,unit_id?,questions:[]}` -> `{questions:[...]}`. All-or-nothing validation.
- `GET /api/questions/export?module_id=<id>` -> `{questions:[]}`.
- `POST /api/attempts` with `{question_id,answer,rating:0|1|2,duration_seconds?,evaluation_source?:"self"|"automatic"|"ai"}` -> attempt. MC correctness and rating are calculated by the server, free text requires self-rating. Review schedule updated.
- `GET /api/answers?module_id=<id>&unit_id=<id>&status=pending|reviewed|all` -> `{answers:[submission]}`. Filters are optional; `status` defaults to `pending`. `GET /api/answers/<id>` -> `{...submission,question,module,unit,source_material,image_material}` with source material detail (text/pages) and image metadata when present. A missing source is `null`.
- `POST /api/answers` with `{question_id,answer,duration_seconds?}` -> pending submission. Only reviewed `free_text` and `image` questions accept submissions. Pending answers are not graded attempts and do not change mastery or scheduling.
- `POST /api/answers/<id>/review` with `{rating:0|1|2,feedback,reviewer?}` -> reviewed submission and the resulting graded attempt. Feedback must be nonempty; reviewer defaults to `ChatGPT (im Chat)`. A submission can be reviewed only once; a repeat returns HTTP 400. Ratings mean incorrect, partially correct, and correct.
- Submission: `{id,qid,answer,submitted_at,duration_seconds,status:"pending"|"reviewed",rating:null|0|1|2,feedback,reviewed_at,reviewer,attempt_id}`. Pending submissions have no rating, feedback, review time, or attempt ID.
- `GET /api/context?module_id=<id>&unit_id=<id>` -> `{module,units,materials (including pages/text),questions,attempts,answer_submissions,stats,instructions}`. Includes actual stored learner answers within the selected module/unit. This is the AI-readable context. May be large, no secret credentials.
- `GET /api/ai/status` -> `{provider,configured,model,reason}`.
- `POST /api/ai/generate` with `{module_id,unit_id?,material_ids:[],count:1..20,types:["multiple_choice","free_text"],difficulty:1..3}` -> `{questions:[]}`. Proposals not saved until reviewed and imported.
- `POST /api/ai/evaluate` with `{question_id,answer}` -> `{rating:0|1|2,feedback:string}`. No attempt saved automatically.
- `GET /api/backup` -> ZIP with SQLite backup + original materials.
- `GET /api/health` -> `{ok:true,app:"Lernraum"}`.
- `POST /api/attempts/<id>/review` with `{rating:0|1|2,feedback,reviewer?}` -> reviewed answer submission referencing the original attempt. Only self-rated free-text/image attempts can be reviewed this way, once. Preserves attempt ID, answer, timestamp, duration and total counts; updates the original rating and evaluation_source to ai. The latest attempt's learning state is recomputed without counting an extra repetition. An older attempt never overwrites a newer attempt's learning state or schedule.

## Data

Module: `id,name,code,description,color,semester,created_at` (allowed colors violet, blue, green, orange, rose).
Unit: `id,module_id,title,kind,date,notes,created_at`.
Material: `id,module_id,unit_ids:[],name,mime,size,extraction_status,extraction_message,page_count,created_at,file_url`; detail includes text/pages. Status: ready, needs_ocr, unsupported, error. PDF text extraction via optional pypdf; images remain originals readable by external agents. No OCR claimed.
Question: `id,module_id,unit_id:null|string,type:"multiple_choice"|"free_text"|"image",prompt,options:[],correct_index:null|int,answer,explanation,topic,difficulty:1..3,source_material_id:null|string,source_page:null|int,image_material_id:null|string,is_ai:bool,reviewed:bool,created_at,due_at:null|string,mastery:0|50|100,attempt_count`.
Attempt: `id,question_id,answer,rating,correct,answered_at,duration_seconds,evaluation_source`.

## Store contract (storage.py)

`Store(data_dir, seed=True)`; `snapshot()`, `stats()`, `get_module(id)`, `create_module(data)`, `update_module(id,data)`, `delete_module(id)`, analogous create/update/delete_unit; `get_material(id)`, `upload_material(data)`, `update_material(id,data)`, `delete_material(id)`, `material_path(id) -> Path`; `get_question(id)`, `create_question(data)`, `update_question(id,data)`, `delete_question(id)`, `import_questions(module_id,questions,unit_id=None) -> list`; `record_attempt(data) -> attempt`; `context(module_id,unit_id=None) -> dict`; `backup() -> bytes` ZIP. Raise ValueError for validation, KeyError for missing IDs. Thread-safe per-operation sqlite connections and foreign keys. Atomic imports and correct module references required. Seed exactly two empty editable modules, named Modul 1 and Modul 2. No fake performance or lectures.

## AI adapter (ai.py)

`status() -> dict`; `generate(context, request) -> list[question dicts]`; `evaluate(question, answer) -> dict`.
Configuration server-side environment or `.env`: `LERNRAUM_AI_PROVIDER=openai|ollama`, `LERNRAUM_AI_MODEL`, `OPENAI_API_KEY`, `LERNRAUM_OLLAMA_URL=http://127.0.0.1:11434`. No default model inferred. Only source-grounded proposals; validate sources against supplied context. Provider failures become clean ValueErrors and do not save questions. Refusals/incomplete responses handled. OpenAI Responses API with structured outputs; Ollama generate endpoint with JSON schema and stream=false. No network calls when unconfigured. No secrets in status or output.
