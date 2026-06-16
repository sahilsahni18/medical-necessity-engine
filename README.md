# Medical Necessity Assistant

A clinical coding compliance assistant for healthcare providers in the UAE. It
answers E/M coding and JAWDA-audit questions **only** from a fixed set of
guideline documents, always citing the exact source, and it analyses a patient
encounter to judge whether the documentation supports the billed CPT code.

The design splits the work in two:

- **A hardcoded, deterministic rules engine** (`app/rules/`) encodes the fixed
  lookup tables from the documents — the AMA 2021 MDM grid, the time
  thresholds, and the JAWDA penalty table. This part *decides*. It never calls
  an LLM, so it can never invent a threshold (assignment Rule 6).
- **A retrieval + LLM layer** handles the language work only: finding the right
  passage to cite, and reading messy free-text notes to classify them into MDM
  tiers. Gemini sits at the two language edges; the accurate middle is code.

## Source documents (the only source of truth)

| File | Tag | Role |
|---|---|---|
| `AMA_Guidelines.pdf` | `AMA_2021` | Office/outpatient E/M 99202–99215: MDM grid, time, definitions |
| `97_Doc_guidelines.pdf` | `CMS_1997` | 1997 history/exam/MDM bullet counting (other settings) |
| `JAWDA_..._Part_IX.pdf` | `JAWDA` | Audit methodology, scoring weights, penalty tables |
| `clinical_coding_process_review.pdf` | `JAWDA` | Clinical coding process review domain |
| `HAAD_CodingManual_V7.txt` | `HAAD` | Abu Dhabi coding manual (converted from the supplied `.doc`) |

---

## 1. Setup and run from scratch

Prerequisites: Docker + Docker Compose, and a free Gemini API key from Google
AI Studio (no credit card).

```bash
# 1. Configure
cp .env.example .env
#    edit .env and paste your key:  GEMINI_API_KEY=AIza...

# 2. Start Postgres (with pgvector) and the API
docker compose up --build -d

# 3. Build the search index from the guideline documents (run once)
docker compose exec api python -m scripts.ingest

# 4. Open the app
#    UI:        http://localhost:8000/
#    API docs:  http://localhost:8000/docs
#    Health:    curl http://localhost:8000/health
```

Run the test suite (deterministic core — no key or database required):

```bash
pip install -r requirements.txt
pytest -q
```

### Local (no Docker)

```bash
pip install -r requirements.txt
# point DATABASE_URL at a Postgres that has the pgvector extension
python -m scripts.ingest
uvicorn app.main:app --reload
```

---

## 2. Sample API requests and responses

### Ask a question

```bash
curl -s http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "Is hypertension a stable chronic illness under AMA 2021?"}'
```

```json
{
  "answer": "Under AMA 2021, well-controlled hypertension is given as an example of a stable chronic illness. However, a patient who is not at their treatment goal is not considered stable even if the condition is unchanged.",
  "citations": [
    {"guideline_set": "AMA_2021", "source_document": "AMA_Guidelines.pdf",
     "location": "page 5", "snippet": "Stable, chronic illness... Examples may include well-controlled hypertension..."}
  ],
  "governing_guideline": "AMA_2021",
  "insufficient_evidence": false
}
```

### Analyze an encounter

```bash
curl -s http://localhost:8000/analyze-encounter -H 'Content-Type: application/json' \
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

```json
{
  "billed_code": "99214",
  "governing_guideline": "AMA_2021 (E/M Guidelines effective Jan 1 2021 for codes 99202-99215 (p. 1))",
  "supports_billed_code": "supported",
  "code_assessment": "Documentation supports moderate MDM, while 99214 requires moderate MDM, so the billed code is supported.",
  "documentation_gaps": [],
  "denial_risk": "low",
  "denial_risk_rationale": "The documentation supports the billed code with no major gaps, so denial risk on medical-necessity grounds is low.",
  "mdm_breakdown": {"problems": "moderate", "data": "low", "risk": "moderate",
                    "achieved_level": "moderate", "required_level": "moderate"},
  "citations": [
    {"guideline_set": "AMA_2021", "source_document": "AMA_Guidelines.pdf", "location": "Table 2 - Levels of Medical Decision Making (pp. 11-14)"}
  ],
  "insufficient_evidence": false
}
```

*(LLM-written fields will vary in wording; the rules-driven fields — verdict,
levels, risk tier — are deterministic.)*

---

## 3. Document processing and retrieval

**Processing.** Each document is parsed (`pypdf` for PDFs; plain text for the
converted HAAD manual) and split into overlapping, paragraph-aware chunks
(`app/ingestion.py`). Every chunk is stored with rich metadata — `guideline_set`,
`source_document`, and `location` (page) — which is what makes exact-location
citation possible. The HAAD `.doc` is a legacy binary, so it was converted to
text once (via LibreOffice) and shipped as `HAAD_CodingManual_V7.txt`.

**Storage.** A single datastore: **PostgreSQL with the `pgvector` extension**
(`app/db.py`). One table holds the chunk text, its embedding, and metadata,
plus a generated `tsvector` for keyword search. No separate vector database is
used — the mandated Postgres does both jobs.

**Retrieval (`app/retrieval.py`).** Hybrid search: vector similarity (`pgvector`
cosine) for meaning, blended with full-text keyword ranking for exact tokens
like `99214` or `LAMA`. Embeddings are produced by Gemini by default; set
`EMBEDDING_PROVIDER=local` to use a small `sentence-transformers` model instead
(documented fallback — no quota, uses RAM).

**Why retrieval is built by hand, not with a framework.** The answer-quality
rules demand tight retrieval and exact citations. Hand-rolling the loop keeps
full control over both, keeps the dependency surface small, and makes the
supersession routing (below) trivial to enforce.

---

## 4. Handling the 1997 vs 2021 supersession (Rule 5)

The 1997 and 2021 guidelines disagree, and AMA 2021 supersedes the 1997 rules
**for office/outpatient codes 99202–99215**. This is enforced in two places so
it cannot leak:

1. **At retrieval** (`determine_excluded_sets`): when a query references an
   office/outpatient code, the `CMS_1997` chunks are excluded from search, so a
   1997 passage can never be retrieved or cited for those codes. This is covered
   by `tests/test_supersession.py`.
2. **In the rules engine** (`em_rules.governing_guideline`): leveling for
   99202–99215 uses the hardcoded AMA 2021 MDM grid; other E/M settings map to
   the 1997 source. The encounter analyser refuses to apply the AMA grid to
   non-outpatient codes rather than guess.

Treating supersession as a routing/filtering decision (not something the model
must "remember") is what makes it reliable.

---

## 5. What I would improve with more time

- **Table-aware ingestion.** The AMA MDM grid and JAWDA penalty tables extract
  poorly as flat text. A table-structure parser would improve the *cited
  snippets* (the rules engine already encodes the table logic, so verdicts are
  unaffected — only the displayed quote).
- **Reranking.** Add a cross-encoder reranker over the hybrid candidates for
  sharper top-k precision.
- **Golden-answer evaluation harness.** A small labelled set of question →
  expected-source-document pairs, run in CI, to catch retrieval regressions.
- **Confidence + abstention tuning.** Calibrate when `insufficient_evidence`
  fires, and surface a confidence score.
- **Auth, rate limiting, and observability** on the public endpoints, plus
  caching of repeated questions to protect the free Gemini quota.
- **HAAD code-set validation.** Cross-check submitted diagnosis/procedure codes
  against the HAAD manual's conventions.

---

## Deploying a shareable link

The app is built to deploy as a single hosted link where **the end user needs
no key** — you set one Gemini key server-side.

1. Push this repo to GitHub.
2. On a host with managed Postgres + pgvector (Render, Railway, or Fly.io):
   create a Postgres instance, enable the `vector` extension, deploy the
   `Dockerfile`, and set `DATABASE_URL`, `GEMINI_API_KEY`, and `ADMIN_TOKEN` as
   environment variables (never in the repo).
3. After first deploy, build the index once:
   `curl -X POST https://<your-app>/admin/ingest -H "x-admin-token: <ADMIN_TOKEN>"`.
4. Share the URL. Visitors use it directly; your key stays private on the host.

Keep the Gemini project on the **free tier** (do not enable billing on it) and
use `gemini-2.5-flash` for generous daily limits.

## Project layout

```
app/
  rules/            # hardcoded, deterministic engine (cited)
    em_rules.py     #   AMA 2021 MDM grid, time, supersession
    jawda_rules.py  #   JAWDA penalty table + weights
    citations.py    #   source registry
  retrieval.py      # hybrid search + supersession routing
  ingestion.py      # parse -> chunk -> embed -> store
  gemini_client.py  # embeddings + JSON generation (+ local fallback)
  db.py             # Postgres + pgvector
  services/         # ask + encounter orchestration
  schemas.py        # typed, bounded API contracts
  prompts.py        # prompts encoding the 6 answer-quality rules
  main.py           # FastAPI endpoints
frontend/index.html # basic UI
scripts/ingest.py   # one-time ingestion CLI
tests/              # deterministic-core tests (no key/db needed)
data/guidelines/    # the five source documents
```
