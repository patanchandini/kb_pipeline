# KB Pipeline — Production Knowledge-Base Update & Monitoring System

A production-grade pipeline that ingests documents into a chatbot's knowledge base,
detects duplicates, quarantines invalid files, gates updates behind quality tests,
activates them only inside a maintenance window, and auto-rolls back on health-check
failure. Serves retrieval-augmented chat with access control, prompt-injection
protection, sensitive-data masking, and Prometheus metrics.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Project Layout](#project-layout)
4. [Requirements](#requirements)
5. [Setup](#setup)
6. [Configuration](#configuration)
7. [Running the Pipeline](#running-the-pipeline)
8. [Running the Server](#running-the-server)
9. [API Reference](#api-reference)
10. [Running Tests](#running-tests)
11. [Monitoring](#monitoring)
12. [Deployment](#deployment)
13. [Security Model](#security-model)
14. [Troubleshooting](#troubleshooting)
15. [License](#license)

---

## Features

### Ingestion
- **Incremental updates** — only new or modified documents are processed (SHA-256 content hash).
- **Duplicate detection** — near-duplicate detection via cosine similarity of embeddings (threshold configurable).
- **Invalid-file quarantine** — files failing size/encoding/JSON validation are moved to `data/quarantine/` with a `.reason` sidecar.
- **Chunking with overlap** — word-based chunker with configurable size and stride.
- **Deterministic hash embeddings** — swap for sentence-transformers / OpenAI embeddings in production.

### Versioning & Rollback
- Every approved stage creates a **snapshot** (`data/snapshots/snapshot_<timestamp>.json`) containing the full documents + chunks state.
- `rollback_to(version)` restores DB from a snapshot.
- Version statuses: `staging` → `activating` → `active` / `rolled_back` / `rejected`.

### Quality Gate
- Runs an evaluation set (`data/eval_set.jsonl`) against the staging index.
- Computes **accuracy** (answer_contains present in retrieved chunks) and **grounding** (top retrieval score above floor).
- Rejects the update if either metric falls below configured thresholds.

### Scheduler & Retries
- Daily cron builds a staging snapshot (`daily_update_cron`).
- Failed activations enqueue retries at **15 / 30 / 60 minutes** (`retry.delays_minutes`).
- Retries exhausted → job marked `failed` in the `retries` table.

### Maintenance Window
- Activation only proceeds inside `maintenance_window` (default `03:00–03:30` UTC).
- Outside the window, activation returns `outside_maintenance_window` and is deferred to retries.

### Health Checks & Auto-Rollback
- After activation begins, the pipeline runs DB and retrieval probes for `health_check_seconds` (default 300 s).
- If any probe fails, the previously-active version is restored automatically.

### Runtime Security
- **API-key authentication** with role hierarchy: `viewer` < `editor` < `admin`.
- **Prompt-injection guard** — regex blocklist applied to every chat input before retrieval.
- **PII masking** — SSN, credit cards, emails, phone numbers redacted with `[REDACTED]` in responses.

### Observability
- Prometheus metrics on port `9100`:
  - `kb_requests_total{endpoint,status}`
  - `kb_request_latency_seconds{endpoint}`
  - `kb_failures_total{stage}`
  - `kb_confidence` (histogram)
  - `kb_escalations_total`
  - `kb_injection_blocked_total`
  - `kb_masked_pii_total`
  - `kb_active_version`

---

## Architecture
┌─────────────────────────────────────────────────────────────┐
│ INGESTION PIPELINE │
│ Discover → Change-Detect → Dedup → Validate → Quarantine │
│ ↓ │
│ Parse → Chunk → Embed → Index (staging) │
│ ↓ │
│ Quality Tests (accuracy / grounding) → Approve / Reject │
│ ↓ │
│ Version Snapshot (SQLite + JSON) │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ SCHEDULER + ACTIVATION GATE │
│ Retry queue (15 / 30 / 60 min) → Maintenance Window check │
│ → Activate → Health-check (5 min) → Auto-rollback on fail │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ RUNTIME (serving) │
│ Auth → Injection Guard → Retrieval → PII Mask → Response │
│ → Prometheus Metrics │
└─────────────────────────────────────────────────────────────┘

text

---

## Project Layout
kb_pipeline/
├── config.yaml # main configuration
├── requirements.txt
├── main.py # entry point (server + scheduler + retries)
├── conftest.py # pytest path setup
├── check_db.py # quick DB inspection script
├── render.yaml # Render deployment config
├── README.md
├── LICENSE
├── .gitignore
├── kb/ # package
│ ├── init.py
│ ├── config.py # YAML loader → attribute-access namespace
│ ├── logging_setup.py
│ ├── storage.py # SQLite schema + connection helper
│ ├── ingest.py # discovery → dedup → validate → register
│ ├── dedup.py # near-duplicate detection
│ ├── validate.py # file validation + quarantine
│ ├── index.py # embedding + vector search
│ ├── versions.py # snapshots + rollback
│ ├── quality.py # accuracy + grounding gate
│ ├── scheduler.py # retry queue + maintenance window
│ ├── health.py # DB + retrieval probes
│ ├── activation.py # staging build + activation + rollback
│ ├── security.py # API-key auth + injection patterns
│ ├── masking.py # PII regex masking
│ ├── metrics.py # Prometheus counters/histograms
│ └── runtime.py # FastAPI app
├── data/
│ ├── docs/ # source documents (.md, .txt, .json)
│ ├── quarantine/ # invalid files + .reason sidecars
│ ├── snapshots/ # version snapshots
│ ├── eval_set.jsonl # quality-gate evaluation set
│ └── kb.db # SQLite database (gitignored)
└── tests/
├── test_pipeline.py # ingestion, dedup, quality, security
└── test_api.py # FastAPI endpoint tests

text

---

## Requirements

- **Python 3.10+** (tested on 3.11.9)
- Windows, macOS, or Linux
- No external services required (SQLite, in-process embeddings)

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/patanchandini/kb_pipeline.git
cd kb_pipeline
2. Create a virtual environment
Windows (cmd):

cmd
python -m venv .venv
.venv\Scripts\activate
macOS / Linux:

bash
python3 -m venv .venv
source .venv/bin/activate
3. Install dependencies
bash
pip install --upgrade pip
pip install -r requirements.txt
pip install pytest httpx
4. Create required folders (if not present)
cmd
mkdir data\docs
mkdir data\quarantine
mkdir data\snapshots
mkdir tests
5. Add sample documents
Place .md, .txt, or .json files under data/docs/. Example:

data/docs/refund.md

data/docs/password.md

data/docs/hours.md

data/docs/payment.md

data/docs/refund_copy.md ← duplicate for testing

data/docs/broken.json ← invalid for testing quarantine

6. Add the evaluation set
Create data/eval_set.jsonl — one JSON object per line:

jsonl
{"question": "What is the refund policy?", "answer_contains": "refund"}
{"question": "How do I reset my password?", "answer_contains": "password"}
{"question": "What are your business hours?", "answer_contains": "hours"}
{"question": "How do I contact support?", "answer_contains": "support"}
{"question": "What payment methods are accepted?", "answer_contains": "payment"}
Configuration
All configuration lives in config.yaml.

yaml
paths:
  docs_dir: data/docs
  quarantine_dir: data/quarantine
  db_path: data/kb.db

embedding:
  dim: 384

chunk:
  size: 400
  overlap: 60

dedup:
  exact: true
  near_threshold: 0.93

quality:
  min_accuracy: 0.75
  min_grounding: 0.80
  eval_set: data/eval_set.jsonl

schedule:
  daily_update_cron: "0 2 * * *"
  maintenance_window: "03:00-03:30"    # UTC

retry:
  delays_minutes: [15, 30, 60]

activation:
  health_check_seconds: 300
  auto_rollback: true

security:
  api_keys:
    admin: "ADMIN_KEY_CHANGE_ME"
    editor: "EDITOR_KEY_CHANGE_ME"
    viewer: "VIEWER_KEY_CHANGE_ME"
  injection_patterns:
    - "ignore previous instructions"
    - "ignore all previous"
    - "disregard the above"
    - "system prompt"
    - "you are now"
    - "jailbreak"
    - "reveal your instructions"
  masking_patterns:
    - '(?i)\b\d{3}-\d{2}-\d{4}\b'
    - '\b(?:\d[ -]*?){13,16}\b'
    - '(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}'
    - '(?i)\+?\d[\d\s\-()]{8,}\d'

metrics:
  port: 9100
⚠️ Before shipping to production, move api_keys to environment variables.

Running the Pipeline
One-time DB initialization
bash
python -c "from kb.storage import init_db; init_db(); print('DB ready')"
Run ingestion
bash
python -c "from kb.ingest import run_ingest; import json; print(json.dumps(run_ingest(), indent=2))"
Example output:

json
{
  "new": [
    {"path": "data/docs/hours.md", "version": 1, "chunks": 1},
    {"path": "data/docs/password.md", "version": 1, "chunks": 1},
    {"path": "data/docs/payment.md", "version": 1, "chunks": 1},
    {"path": "data/docs/refund.md", "version": 1, "chunks": 1}
  ],
  "modified": [],
  "duplicates": [
    {"path": "data/docs/refund_copy.md", "score": 1.0}
  ],
  "quarantined": [
    {"path": "data/docs/broken.json", "reason": "bad_json: ..."}
  ]
}
Run the quality gate
bash
python -c "from kb.quality import run_quality_tests; import json; print(json.dumps(run_quality_tests(), indent=2))"
Expected:

json
{"passed": true, "accuracy": 1.0, "grounding": 1.0, "details": [...]}
Check DB state
bash
python check_db.py
Running the Server
bash
python main.py
Expected startup:

text
INFO | main | Scheduler started (cron=0 2 * * *)
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
The terminal blocks — the server is live. Open a second terminal for testing.

Swagger UI: http://localhost:8000/docs

Prometheus: http://localhost:9100/metrics

Manual server start (bypasses main.py)
If you only want the API without the scheduler:

bash
python -m uvicorn kb.runtime:app --host 0.0.0.0 --port 8000
API Reference
Base URL: http://localhost:8000

GET /healthz
Public health probe.

Response:

json
{"ok": true, "version": 0}
POST /chat
Query the knowledge base.

Request:

json
{"message": "What is the refund policy?"}
Response (200):

json
{
  "answer": "# Refund Policy Customers may request a refund within 30 days...",
  "confidence": 0.42,
  "escalated": false
}
Response (400) — prompt injection detected:

json
{"detail": "unsafe_input"}
POST /admin/ingest
Trigger an ingestion run. Role required: editor.

Headers: x-api-key: EDITOR_KEY_CHANGE_ME

Response (200):

json
{"new": [...], "modified": [...], "duplicates": [...], "quarantined": [...]}
Response (403): {"detail": "forbidden"}

POST /admin/activate
Activate the latest staged version. Only succeeds inside the maintenance window. Role required: admin.

Headers: x-api-key: ADMIN_KEY_CHANGE_ME

Response (200):

json
{"activated": true, "version": 1}
or

json
{"activated": false, "reason": "outside_maintenance_window"}
POST /admin/rollback/{version}
Restore KB state to a prior version. Role required: admin.

Response:

json
{"rolled_back_to": 1}
Running Tests
bash
pytest tests\ -v
Expected:

text
tests/test_pipeline.py::test_ingest_new_docs PASSED
tests/test_pipeline.py::test_duplicate_detection PASSED
tests/test_pipeline.py::test_quarantine_invalid PASSED
tests/test_pipeline.py::test_incremental_skip PASSED
tests/test_pipeline.py::test_quality_gate_passes_on_good_kb PASSED
tests/test_pipeline.py::test_version_snapshot_and_rollback PASSED
tests/test_pipeline.py::test_prompt_injection_blocked PASSED
tests/test_pipeline.py::test_sensitive_masking PASSED
tests/test_pipeline.py::test_access_control_roles PASSED
tests/test_pipeline.py::test_retry_backoff_schedule PASSED
tests/test_pipeline.py::test_maintenance_window_logic PASSED

11 passed
Monitoring
Prometheus metrics
bash
curl http://localhost:9100/metrics | grep ^kb_
Sample output:

text
kb_active_version 1.0
kb_confidence_bucket{le="0.5"} 3.0
kb_injection_blocked_total 2.0
kb_masked_pii_total 1.0
kb_requests_total{endpoint="chat",status="ok"} 5.0
kb_requests_total{endpoint="chat",status="rejected"} 2.0
kb_failures_total{stage="chat"} 0.0
Audit log
Every privileged action is written to the audit table in data/kb.db:

bash
python -c "from kb.storage import connect; \
  [print(dict(r)) for r in connect().__enter__().execute('SELECT * FROM audit ORDER BY id DESC LIMIT 10')]
