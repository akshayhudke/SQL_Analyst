# Training Data (Local)

QuerySense stores every analysis in PostgreSQL so you can fine‑tune or evaluate later.

## Table
`llm_training_data`

## What Gets Stored
- Original SQL
- Normalized SQL
- Parsed SQL summary
- Plan summary
- Rule findings
- Index recommendations
- Optimization score
- Full LLM prompt payload
- Full LLM output
- Flags for `run_analyze` and `run_preview`
- Warnings
- Human labels (`good`, `bad`, `needs_review`)
- Notes from reviewers

## Why This Helps
- You can build a fine‑tuning dataset without re‑running queries.
- You can track how model outputs change over time.
- You can label good vs bad rewrites for evaluation.

## Safety Note
This data stays local in your Dockerized Postgres instance.

## API Endpoints
- `GET /api/training/stats` — summary counts and averages (supports filters)
- `GET /api/training/list?limit=20` — recent rows for the UI (supports filters)
- `GET /api/training/trends?days=30` — average score trend for charts
- `POST /api/training/label` — save `good`, `bad`, or `needs_review`
- `GET /api/training/export?format=jsonl|csv&limit=500` — export dataset (supports filters)

### Filter Query Params
You can pass these to `stats`, `list`, `trends`, and `export`:
- `label=good|bad|needs_review|unlabeled`
- `model=<model_name>`
- `date_from=YYYY-MM-DD`
- `date_to=YYYY-MM-DD`
