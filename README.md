# QuerySense (Local MVP)

A Dockerized, open-source SQL performance assistant that analyzes SQL structure and PostgreSQL execution plans, then produces explainable optimization recommendations. LLM usage is strictly for explanation and safe rewrites, never for executing queries.

## MVP Features
- Chat-like UI for running and analyzing SQL
- Live agent that analyzes queries as you type (debounced)
- PostgreSQL execution plan capture (`EXPLAIN` / `EXPLAIN ANALYZE`)
- Rule-based findings and recommendations
- LLM explanations from a local Ollama model
- Optimization score, “Why Slow”, and index recommendations
- Training data stored locally in Postgres for future fine-tuning
- Training dashboard with export + Good/Bad labels
- Training filters, trend chart, and review queue
- Fully local, Dockerized stack

## Quickstart
1. Start the stack:
   ```bash
   docker compose up --build
   ```
2. Pull a local model (first run only):
   ```bash
   docker compose exec ollama ollama pull qwen2.5:7b
   ```
   Optional (larger model):
   ```bash
   docker compose exec ollama ollama pull qwen2.5:14b
   ```
3. Open the UI at `http://localhost:5173`.

## Notes
- MVP supports read-only `SELECT` queries only.
- `EXPLAIN ANALYZE` executes the query. Use with care for heavy queries.
- Result preview is capped by `PREVIEW_LIMIT` (default 100 rows).
- Sample data is large (1M orders). First startup may take several minutes.

## Configuration
Edit `docker-compose.yml` for environment variables:
- `OLLAMA_MODEL`: model to use (default `qwen2.5:7b`, optional `qwen2.5:14b`)
- `ANALYZE_STATEMENT_TIMEOUT_MS`: query timeout for analysis
- `PREVIEW_LIMIT`: max preview rows
- `LLM_ONLY_REWRITE`: if `true`, only the LLM provides rewrites
- `MEMORY_REWRITE_ENABLED`: enable JSONL memory fallback rewrites
- `TRAINING_STORE_ENABLED`: save training data in Postgres
- `LLM_TIMEOUT_LIVE` / `LLM_TIMEOUT_MANUAL`: LLM timeouts for live vs manual
- `LLM_MAX_PREDICT_LIVE` / `LLM_MAX_PREDICT_MANUAL`: output length caps
- `LLM_MAX_FINDINGS_LIVE` / `LLM_MAX_FINDINGS_MANUAL`: prompt trimming
- `LLM_MAX_INDEX_LIVE` / `LLM_MAX_INDEX_MANUAL`: prompt trimming
- `LLM_MAX_MEMORY_LIVE` / `LLM_MAX_MEMORY_MANUAL`: prompt trimming

## Documentation
- Architecture and system flow: `docs/ARCHITECTURE.md`
- Rule engine details: `docs/RULES.md`
- Function flow (plain-English): `docs/FUNCTION_FLOW.md`
- Training data storage: `docs/TRAINING_DATA.md`
- OpenShift deployment guide: `docs/OPENSHIFT.md`
