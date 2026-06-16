# Medical Necessity Assistant

> A clinical AI platform for healthcare providers in the UAE to understand E/M coding levels, manage claim denials, and stay compliant with JAWDA audit requirements — answering only from the provided guideline documents, always with an exact citation.

**Live Application:** https://medical-necessity-engine-na1x.onrender.com/

**API Documentation:** https://medical-necessity-engine-na1x.onrender.com/docs

**Health Check:** https://medical-necessity-engine-na1x.onrender.com/health

**Repository:** https://github.com/sahilsahni18/medical-necessity-engine

> The UI and the API are served by a single FastAPI service on Render — the web page at `/` calls the same backend that exposes the API.

---

## Dashboard Preview

<img width="1542" height="865" alt="image" src="https://github.com/user-attachments/assets/21ae2392-d41d-444a-81e8-1836e285cf67" />
<img width="1436" height="862" alt="image" src="https://github.com/user-attachments/assets/06cf0f12-85d8-488a-810a-c9b0a3e8b13e" />


Width of both of them in same , small square

*The clinical interface: ask a coding/compliance question and get a grounded, cited answer, or paste a patient encounter to pre-check the billed code, documentation gaps, and denial risk.*

> _Add your own screenshot at `docs/dashboard.png` (or update this path)._

---

## Project Overview

> The Medical Necessity Assistant answers clinical coding questions using five guideline documents as the **only** source of truth, and analyses a patient encounter to judge whether the documentation supports the billed CPT code.

It supports questions like:

- Does this visit qualify for a 99214?
- Is hypertension a stable chronic illness under AMA 2021?
- What score is deducted if the LAMA form is missing in a JAWDA audit?
- What documentation gaps could cause a denial?

Every answer is built only from the guideline documents, cites the exact source, is capped at four sentences, and clearly says when the documents don't contain the answer — instead of inventing one.

### The core design idea

The system deliberately splits the work in two:

- **A hardcoded, deterministic rules engine** encodes the fixed lookup tables from the documents — the AMA 2021 MDM grid, the time thresholds, the supersession map, and the JAWDA penalty table. This part *decides*. It never calls a language model, so it can never invent a threshold.
- **A retrieval + LLM layer** handles the language work only: finding the right passage to cite, reading messy free-text notes into MDM tiers, and phrasing the final answer. The model sits at the two language edges; the accurate middle is code.

---

### Live Demo

**Access the live application:** https://medical-necessity-engine-na1x.onrender.com/

### Test it with these example questions:

- "What does a 99214 require under AMA 2021?"  *(deterministic — instant)*
- "Which version of the E/M guidelines is in effect for outpatient code 99212?"  *(supersession)*
- "What score is deducted if the LAMA form is missing?"  *(JAWDA penalty)*
- "Is hypertension a stable chronic illness under AMA 2021?"  *(retrieval)*
- "What is the reimbursement in AED for a 99214?"  *(correctly returns "not enough information")*

---

## Features

| Feature | Description |
|---------|-------------|
| **Question Answering** | Answers clinical coding questions with exact citations |
| **Multi-Authority Support** | Routes to AMA 2021, CMS 1997, HAAD, or JAWDA |
| **Encounter Analysis** | Evaluates MDM, documentation gaps, and CPT support |
| **Denial Risk Assessment** | Returns low, moderate, or high risk with a rationale |
| **Source Citations** | Includes guideline set, source document, and location |
| **JAWDA Checks** | Penalty lookups for LAMA, physician mismatch, and time documentation |

---

## Architecture

### System Architecture

```
                          ┌──────────────────────────────┐
                          │   Browser UI  (served at /)   │
                          └───────────────┬──────────────┘
                                          │
                          ┌───────────────▼──────────────┐
                          │          FastAPI API          │
                          └───────┬───────────────┬───────┘
                                  │               │
                         ┌────────▼──────┐  ┌─────▼─────────────┐
                         │     /ask      │  │ /analyze-encounter│
                         └───────┬───────┘  └─────────┬─────────┘
                                 │                    │
                    ┌────────────▼────────────┐       │
                    │  Deterministic Router   │       │
                    │  code? JAWDA? version?  │       │
                    └──────┬───────────┬──────┘       │
                  (matches)│           │(no match)    │
                           ▼           ▼              ▼
                 ┌──────────────┐  ┌────────────────────────────┐
                 │ Rules Engine │  │   Retrieval + LLM (RAG)     │
                 │ em_rules     │  │  hybrid search → ground →   │
                 │ jawda_rules  │  │  cite → write (≤4 sentences)│
                 └──────┬───────┘  └─────────────┬──────────────┘
                        │                        │
                        ▼                        ▼
                 ┌─────────────────────────────────────────────┐
                 │        PostgreSQL + pgvector  (index)        │
                 │  chunk text · embedding · guideline_set ·    │
                 │  source_document · location (page)           │
                 └─────────────────────────────────────────────┘

   Ingestion (one-time):  PDFs / text ──► chunk ──► embed (Gemini) ──► store with metadata
```

## Tech Stack

#### Backend

* **Python 3.11** — Core application language
* **FastAPI** — REST API framework
* **Pydantic / pydantic-settings** — Typed request/response validation and config
* **Uvicorn** — ASGI application server

#### Frontend

* **HTML5 / CSS3** — Responsive single-page UI
* **Vanilla JavaScript** — No framework, no build step
* **Fetch API** — Same-origin calls to the backend (served by FastAPI at `/`)

#### Data & Retrieval

* **PostgreSQL** — Single datastore for chunk text, embeddings, and metadata
* **pgvector** — Vector similarity search inside Postgres (no separate vector DB)
* **psycopg 3** — Direct Postgres access
* **Hybrid search** — Vector similarity + full-text keyword ranking

#### AI

* **Gemini (`google-genai`)** — Embeddings (`gemini-embedding-001`) and answer generation (`gemini-2.5-flash` / `flash-lite`)
* **Local fallback** — `sentence-transformers` (all-MiniLM-L6-v2) when `EMBEDDING_PROVIDER=local`

#### Rules Engine (deterministic, no LLM)

* **AMA 2021 MDM Engine** — Required MDM by code, 2-of-3 element rule
* **Time Validator** — Office/outpatient time ranges per code
* **Supersession Map** — 99202–99215 → AMA 2021 over CMS 1997
* **JAWDA Audit Engine** — Penalty table (Major / Moderate / Minor) and scoring weights

#### Testing & Deployment

* **pytest** — Deterministic-core and supersession tests
* **Docker / Docker Compose** — Containerized app + Postgres (pgvector)
* **Render** — Production hosting (single web service + managed Postgres)

---

### Encounter Analysis Flow (internal logic of `/analyze-encounter`)

```
                 Patient Encounter (JSON)
                          │
                          ▼
                 Extract Documentation
              (HPI, Exam, Assessment, Time)
                          │
                          ▼
                 LLM Tier Classification
            ┌────────────┼────────────┐
            ▼            ▼            ▼
        Problems       Data         Risk
       Complexity    Complexity   Complexity
            └────────────┼────────────┘
                         ▼
                 AMA 2021 MDM Engine
                  2-of-3 Element Rule        ◄── deterministic
                         │
                         ▼
              Does Documentation Support
                  the Billed Code?
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
     Gap Detection   Time Check     Audit Findings
        (CMS)          (AMA)          (JAWDA)
          └──────────────┼──────────────┘
                         ▼
                    Denial Risk
               (Low / Moderate / High)
                         │
                         ▼
            Structured JSON  +  Citations
```

### Question Answering Flow (internal logic of `/ask`)

```
                       User Question
                            │
                            ▼
                  Deterministic Router
        (E/M code requirement? · governing version? · JAWDA penalty?)
                            │
            ┌───────────────┴───────────────┐
            │ match                          │ no match
            ▼                                ▼
     Rules Engine answer            Hybrid Retrieval (pgvector + keyword)
     (fixed table + citation)       with supersession filtering
            │                                │
            │                                ▼
            │                       Grounded LLM Generation
            │                       (only from retrieved chunks)
            └───────────────┬───────────────┘
                            ▼
              Structured Answer (≤ 4 sentences)
              + Citation (authority · document · location)
              + insufficient_evidence flag if unsupported
                            │
                            ▼
                       JSON Response
```

---

## Key Differentiators

| Feature | How It Works |
|---------|--------------|
| **Source-Cited Answers** | Every response includes the guideline set, source document, and location (page / table) |
| **Deterministic Verdicts** | Code levels and JAWDA penalties come from hardcoded tables, never a model's guess |
| **Supersession Routing** | For codes 99202–99215, AMA 2021 is enforced over CMS 1997 — at retrieval *and* in the engine |
| **Hybrid Retrieval** | Vector similarity (pgvector) blended with keyword search for exact tokens like `99214` or `LAMA` |
| **Encounter Analysis** | Judges documentation support, MDM level, documentation gaps, and denial risk |
| **No Hallucination** | Returns a clear "insufficient evidence" when the documents don't cover the question |


---

## Answer Quality Guarantees

| Rule | How It's Enforced |
|------|-------------------|
| Answer only what was asked | Tight retrieval scoped to the question; structured response schema |
| Always cite the source | Every answer carries guideline set + document + location |
| Tight, precise retrieval | Hybrid vector + keyword search with metadata filtering |
| Max 4 sentences per answer | Enforced in code via `clamp_sentences` on every answer field |
| AMA 2021 supersedes CMS 1997 | Enforced at retrieval (1997 excluded for 99202–99215) and in the rules engine |
| Never invent rules | Deterministic tables for verdicts; `insufficient_evidence` flag when unsupported |

---

## Authorities & Compliance

#### AMA 2021

Used for office and outpatient E/M code selection (99202–99215).

* Medical Decision Making (MDM), 2-of-3 element rule
* Problem, data, and risk complexity
* Total-time-based code selection

#### CMS 1997

Used for general documentation principles (history, exam, and other settings).

* HPI / ROS / PFSH
* Examination documentation
* General principles of medical record documentation

#### HAAD (Abu Dhabi Coding Manual V7)

Used for UAE-specific coding and documentation guidance.

* Coding conventions and principal/secondary diagnosis rules
* Outpatient coding and documentation standards

#### JAWDA 2026 (Part IX)

Used for audit compliance and scoring.

* LAMA / required-form validation
* Physician-performer verification
* Penalty table (Major / Moderate / Minor) and domain weights

#### Supersession Rule

For office and outpatient E/M codes **99202–99215**, AMA 2021 supersedes CMS 1997 and is enforced as the primary authority — both in retrieval (1997 chunks are excluded) and in the deterministic engine.

---

## API Endpoints

#### `GET /health`

Returns service status and how many chunks are indexed.

```json
{ "status": "ok", "chunks_indexed": 665 }
```

#### `POST /ask`

Answers a clinical coding question using the appropriate guideline authority.

**Request**

```json
{ "question": "Is hypertension a stable chronic illness under AMA 2021?" }
```

**Response fields:** `answer`, `citations[]` (`guideline_set`, `source_document`, `location`, `snippet`), `governing_guideline`, `insufficient_evidence`

#### `POST /analyze-encounter`

Analyses a patient encounter for CPT support, documentation gaps, and denial risk.

**Response fields:** `billed_code`, `governing_guideline`, `supports_billed_code`, `code_assessment`, `documentation_gaps[]`, `denial_risk`, `denial_risk_rationale`, `mdm_breakdown`, `citations[]`, `insufficient_evidence`

#### `POST /admin/ingest`

Builds the search index from the guideline documents (one-time, token-protected via the `x-admin-token` header).

---

## Sample Requests

#### Clinical Question

```bash
curl -X POST https://medical-necessity-engine-na1x.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Is hypertension a stable chronic illness under AMA 2021?"}'
```

**Example Response**

```json
{
  "answer": "Under AMA 2021, well-controlled hypertension is given as an example of a stable chronic illness. A patient who is not at their treatment goal is not considered stable even if the condition is unchanged.",
  "citations": [
    { "guideline_set": "AMA_2021", "source_document": "AMA_Guidelines.pdf", "location": "page 5",
      "snippet": "Stable, chronic illness ... well-controlled hypertension ..." }
  ],
  "governing_guideline": "AMA_2021",
  "insufficient_evidence": false
}
```

#### Encounter Analysis

```bash
curl -X POST https://medical-necessity-engine-na1x.onrender.com/analyze-encounter \
  -H "Content-Type: application/json" \
  -d '{
    "visit_type": "outpatient",
    "chief_complaint": "Follow-up of diabetes and hypertension",
    "diagnoses": ["Type 2 diabetes, poorly controlled", "Essential hypertension, stable"],
    "procedures": [],
    "documentation": {
      "HPI": "55F, 3-month follow-up. Sugars rising despite metformin; HTN controlled.",
      "exam": "Vitals stable; CV and respiratory exam unremarkable.",
      "assessment": "Uncontrolled T2DM - increased metformin, added empagliflozin. Stable HTN - continue."
    },
    "billed_code": "99214"
  }'
```

**Example Response**

```json
{
  "billed_code": "99214",
  "governing_guideline": "AMA_2021",
  "supports_billed_code": "supported",
  "code_assessment": "Documentation supports moderate MDM, while 99214 requires moderate MDM, so the billed code is supported.",
  "documentation_gaps": [],
  "denial_risk": "low",
  "denial_risk_rationale": "The documentation supports the billed code with no major gaps, so denial risk is low.",
  "mdm_breakdown": { "problems": "moderate", "data": "low", "risk": "moderate", "achieved_level": "moderate", "required_level": "moderate" },
  "citations": [
    { "guideline_set": "AMA_2021", "source_document": "AMA_Guidelines.pdf", "location": "Table 2 (pp. 11-14)" }
  ],
  "insufficient_evidence": false
}
```

*(LLM-written fields vary in wording; the rules-driven fields — verdict, levels, risk tier — are deterministic.)*

---

## Local Setup

### Prerequisites

* Docker and Docker Compose
* A free Gemini API key from Google AI Studio (no credit card)

### Run with Docker (recommended)

```bash
git clone https://github.com/sahilsahni18/medical-necessity-engine.git
cd medical-necessity-engine

# 1. Configure
cp .env.example .env
#    edit .env and set:  GEMINI_API_KEY=your-key

# 2. Start the API + Postgres (with pgvector)
docker compose up --build -d

# 3. Build the search index (one-time)
docker compose exec api python -m scripts.ingest

# 4. Open
#    UI:    http://localhost:8000/
#    Docs:  http://localhost:8000/docs
#    Health: curl http://localhost:8000/health
```

### Run without Docker

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
# point DATABASE_URL at a Postgres that has the pgvector extension, then:
python -m scripts.ingest
uvicorn app.main:app --reload
```

### Environment variables

| Variable | Example | Notes |
|---|---|---|
| `GEMINI_API_KEY` | `your-key` | Required (Google AI Studio) |
| `GENERATION_MODEL` | `gemini-2.5-flash-lite` | Answer-writing model |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Must match `EMBEDDING_DIM` |
| `EMBEDDING_DIM` | `768` | 768 for Gemini; 384 for local |
| `EMBEDDING_PROVIDER` | `gemini` | or `local` (sentence-transformers) |
| `DATABASE_URL` | `postgresql://...` | Postgres with pgvector |
| `ADMIN_TOKEN` | `<random secret>` | Protects `/admin/ingest` |

---

## Docker

```bash
docker compose up --build -d
docker compose exec api python -m scripts.ingest
```

The image binds the platform port via `${PORT:-8000}`, so it runs locally on 8000 and on any host that injects `$PORT`.

---

## Deployment

The application is deployed as a **single Render web service** (Docker) backed by **Render managed Postgres with pgvector**. The same service serves the UI at `/` and the API — no separate frontend host is required.

1. Create a Postgres instance on Render (pgvector is auto-created on first ingest).
2. Create a Docker web service from this repo, in the same region.
3. Set environment variables (`DATABASE_URL`, `GEMINI_API_KEY`, model vars, `ADMIN_TOKEN`).
4. After it goes live, build the index once:
   `curl -X POST https://<app>.onrender.com/admin/ingest -H "x-admin-token: <ADMIN_TOKEN>"`
5. Verify `https://<app>.onrender.com/health` shows `chunks_indexed`.

**Live URL:** https://medical-necessity-engine-na1x.onrender.com/

---

## Testing

Current status:

```text
18 tests passed
0 failures
```

The deterministic core requires no API key or database.

Coverage includes:

* AMA 2021 MDM calculation and required levels
* Time-range validation
* JAWDA penalty lookups
* 1997 vs 2021 supersession routing
* Response schema validation (4-sentence cap, citation shape)

Run tests:

```bash
pip install -r requirements.txt
pytest -q
```

---

## Document Processing Approach

> The five guideline documents are the only source of truth. They are parsed, chunked, embedded, and stored in Postgres for retrieval — and their fixed scoring tables are additionally encoded as deterministic Python rules.

#### Processing

* PDFs are parsed with `pypdf`; the HAAD `.doc` was converted once to `HAAD_CodingManual_V7.txt`.
* Each document is split into paragraph-aware chunks.
* Every chunk is stored with metadata: `guideline_set`, `source_document`, and `location` (page) — which is what makes exact-location citations possible.

#### Storage Model

* **guideline_chunks** → chunk text + embedding + metadata + a generated `tsvector` for keyword search.
* A single datastore: PostgreSQL with the `pgvector` extension (no separate vector database).

#### Retrieval Flow

1. Route the question (deterministic rules engine handles code, version, and JAWDA-penalty questions directly).
2. For everything else, run hybrid search: vector similarity blended with keyword ranking.
3. Apply supersession filtering (exclude CMS 1997 for codes 99202–99215).
4. Generate a grounded answer from the retrieved chunks, with citation — or flag `insufficient_evidence`.

This keeps verdicts deterministic and answers exactly attributable to their source.

---

## Project Structure

```text
medical-necessity-engine/
├── app/
│   ├── rules/                  # hardcoded, deterministic engine (cited)
│   │   ├── em_rules.py         #   AMA 2021 MDM grid, time, supersession, governance
│   │   ├── jawda_rules.py      #   JAWDA penalty table + weights + matcher
│   │   └── citations.py        #   source registry
│   ├── services/
│   │   ├── ask_service.py      #   deterministic routing + grounded RAG
│   │   └── encounter_service.py#   encounter analysis orchestration
│   ├── retrieval.py            # hybrid search + supersession routing
│   ├── ingestion.py            # parse → chunk → embed → store
│   ├── gemini_client.py        # embeddings + JSON generation (+ local fallback)
│   ├── db.py                   # Postgres + pgvector data layer
│   ├── schemas.py              # typed, bounded API contracts
│   ├── prompts.py              # prompts encoding the answer-quality rules
│   ├── config.py               # settings
│   └── main.py                 # FastAPI endpoints
│
├── data/guidelines/            # the five source documents
│   ├── AMA_Guidelines.pdf
│   ├── 97_Doc_guidelines.pdf
│   ├── JAWDA_Data_Certification_for_Healthcare_Providers_2026-Part_IX.pdf
│   ├── clinical_coding_process_review.pdf
│   └── HAAD_CodingManual_V7.txt
│
├── frontend/
│   └── index.html              # single-page UI (served by FastAPI at /)
│
├── scripts/
│   └── ingest.py               # one-time ingestion CLI
│
├── tests/                      # deterministic-core + supersession tests
│   ├── test_em_rules.py
│   ├── test_jawda_rules.py
│   ├── test_schemas.py
│   └── test_supersession.py
│
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

---

## Future Improvements

* **Table-aware ingestion** - parse the AMA MDM grid and JAWDA penalty tables structurally so cited snippets are cleaner (verdicts are already deterministic).
* **Reranking** - add a cross-encoder reranker over hybrid candidates for sharper top-k precision.
* **Golden-answer evaluation harness** - a labelled set of question → expected-source pairs, run in CI to catch retrieval regressions.
* **Confidence and abstention tuning** - calibrate when `insufficient_evidence` fires and surface a confidence score.
* **Auth, rate limiting, and observability** on public endpoints, plus caching of repeated questions to protect quota.
* **HAAD code-set validation** - cross-check submitted diagnosis/procedure codes against the HAAD manual's conventions.
