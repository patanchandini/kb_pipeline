# KB Pipeline — Production Knowledge-Base Update & Monitoring System

A production-grade pipeline that ingests documents into a chatbot's knowledge base,
detects duplicates, quarantines invalid files, gates updates behind quality tests,
activates them only inside a maintenance window, and auto-rolls back on health-check
failure. Serves retrieval-augmented chat with access control, prompt-injection
protection, sensitive-data masking, and Prometheus metrics.

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
12. [Security Model](#security-model)
13. [Troubleshooting](#troubleshooting)
14. [License](#license)

---

## Features

### Ingestion
- **Incremental updates** — only new or modified documents are processed (SHA-256 content hash).
- **Duplicate detection** — near-duplicate detection via cosine similarity of embeddings.
- **Invalid-file quarantine** — files failing size/encoding/JSON validation are moved to `data/quarantine/` with a `.reason` sidecar.
- **Chunking with overlap** — words-based chunker with configurable size and stride.
- **Deterministic hash embeddings** — swap for sentence-transformers / OpenAI embeddings in production.

### Versioning & Rollback
- Every approved stage creates a **snapshot** (`data/snapshots/snapshot_<timestamp>.json`).
- `rollback_to(version)` restores DB from a snapshot.
- Version statuses: `staging` → `activating` → `active` / `rolled_back` / `rejected`.

### Quality Gate
- Runs an evaluation set (`data/eval_set.jsonl`) against the staging index.
- Computes **accuracy** and **grounding** metrics.
- Rejects updates below configured thresholds.

### Scheduler & Retries
- Daily cron builds a staging snapshot.
- Failed activations retry at **15 / 30 / 60 minutes**.
- Retries exhausted → job marked `failed`.

### Maintenance Window
- Activation only proceeds inside `maintenance_window` (default `03:00–03:30` UTC).
- Outside the window, activation is deferred to retries.

### Health Checks & Auto-Rollback
- After activation begins, runs DB and retrieval probes for `health_check_seconds` (default 300 s).
- If any probe fails, the previously-active version is restored automatically.

### Runtime Security
- **API-key authentication** with role hierarchy: `viewer` < `editor` < `admin`.
- **Prompt-injection guard** — regex blocklist applied to every chat input.
- **PII masking** — SSN, credit cards, emails, phone numbers redacted with `[REDACTED]`.

### Observability
- Prometheus metrics on port `9100`: request counts, latency histograms, confidence, escalations, injection blocks, masked PII, active KB version.

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
├── config.yaml
├── requirements.txt
├── main.py
├── conftest.py
├── check_db.py
├── README.md
├── LICENSE
├── kb/
│ ├── init.py
│ ├── config.py
│ ├── logging_setup.py
│ ├── storage.py
│ ├── ingest.py
│ ├── dedup.py
│ ├── validate.py
│ ├── index.py
│ ├── versions.py
│ ├── quality.py
│ ├── scheduler.py
│ ├── health.py
│ ├── activation.py
│ ├── security.py
│ ├── masking.py
│ ├── metrics.py
│ └── runtime.py
├── data/
│ ├── docs/
│ ├── quarantine/
│ ├── snapshots/
│ ├── eval_set.jsonl
│ └── kb.db
└── tests/
├── test_pipeline.py
└── test_api.py

text

---

## Requirements

- **Python 3.10+** (tested on 3.11.9)
- Windows, macOS, or Linux
- No external services required (SQLite, in-process embeddings)

---

## Setup

### 1. Create the project

```bash
cd kb_pipeline
2. Create a virtual environment
Windows:

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
4. Create folders
cmd
mkdir data\docs
mkdir data\quarantine
mkdir data\snapshots
mkdir tests
5. Add sample documents
Place .md, .txt, or .json files under data/docs/.

6. Add the eval set
Create data/eval_set.jsonl:

jsonl
{"question": "What is the refund policy?", "answer_contains": "refund"}
{"question": "How do I reset my password?", "answer_contains": "password"}
{"question": "What are your business hours?", "answer_contains": "hours"}
Configuration
All configuration lives in config.yaml. See comments in the file for each field.
⚠️ Move api_keys to environment variables before production.

Running the Pipeline
Initialize DB
bash
python -c "from kb.storage import init_db; init_db(); print('DB ready')"
Ingest
bash
python -c "from kb.ingest import run_ingest; import json; print(json.dumps(run_ingest(), indent=2))"
Quality gate
bash
python -c "from kb.quality import run_quality_tests; import json; print(json.dumps(run_quality_tests(), indent=2))"
Check DB
bash
python check_db.py
Running the Server
bash
python main.py
Swagger UI: http://localhost:8000/docs

Prometheus: http://localhost:9100/metrics

API Reference
Method	Endpoint	Role	Purpose
GET	/healthz	none	Health probe
POST	/chat	none	Query KB
POST	/admin/ingest	editor	Trigger ingestion
POST	/admin/activate	admin	Activate staged version
POST	/admin/rollback/{version}	admin	Rollback to prior version
Auth header: x-api-key: <KEY>

Running Tests
bash
pytest tests\ -v
Expected: 11 passed

Monitoring
bash
curl http://localhost:9100/metrics | grep ^kb_
Security Model
Threat	Mitigation
Unauthorised API access	API key + role hierarchy
Prompt injection	Regex blocklist → 400
PII leakage	Regex masking on responses
Rollback of failed update	Health-check + auto-rollback
Duplicate documents	Cosine similarity check
Invalid input	Validation + quarantine
Silent KB corruption	Snapshot on every staging
Update outside window	Maintenance window enforcement
Troubleshooting
Symptom	Fix
ModuleNotFoundError: No module named 'kb'	cd to project root
unable to open database file	Create data\ folder
[Errno 10048] port in use	taskkill /F /PID <pid> on port 8000
curl: (7) Failed to connect	Start server with python main.py
TypeError: ndarray is not JSON serializable	Use embed(ch).tolist() in kb/ingest.py
AttributeError: '_NS' object has no attribute 'items'	Keep nested dicts plain in kb/config.py
Activation → outside_maintenance_window	Adjust maintenance_window in config.yaml
