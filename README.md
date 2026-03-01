## 💡 Project Status

This project is in early MVP stage.

👉 Join the discussion:  
https://github.com/akshayhudke/SQL_Analyst/discussions

We’re actively shaping the roadmap and welcoming feedback.

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
   docker compose exec ollama ollama pull qwen2.5:1.5b
   ```
3. Open the UI at `http://localhost:5173`.

## Notes
- Any single SQL statement can be analyzed statically.
- Query execution (`EXPLAIN`/preview) is only attempted for read-only `SELECT` on tables that exist in the local Postgres.
- Live mode is static-analysis-first by design to keep latency and memory stable.
- Deterministic correctness checks (for example invalid `GROUP BY`) run before LLM and can generate a safe fixed query even if LLM times out.
- `EXPLAIN ANALYZE` executes the query. Use with care for heavy queries.
- Result preview is capped by `PREVIEW_LIMIT` (default 100 rows).
- Sample data is large (1M orders). First startup may take several minutes.

## Agent Workflow
The optimization agent uses this Python-first flow:
1. Parse SQL into structured facts (`sqlglot` AST).
2. Collect diagnostics from Postgres.
Execution plan: `EXPLAIN`/`EXPLAIN ANALYZE` (manual mode only when safe).
Schema metadata: columns and indexes.
Table statistics: `pg_class` and `pg_stat_user_tables`.
3. Run deterministic red-flag checks:
Full scans, Cartesian join risk, implicit type conversion risk, non-sargable predicates, and GROUP BY correctness issues.
4. Ask LLM for explanation/rewrite using the structured diagnostics.
5. If LLM fails or times out, apply deterministic fallback rewrites when possible.

## Configuration
Edit `docker-compose.yml` for environment variables:
- `OLLAMA_MODEL`: global fallback model (default `qwen2.5:1.5b`)
- `OLLAMA_MODEL_LIVE`: preferred model for live typing analysis (default `qwen2.5:1.5b`)
- `OLLAMA_MODEL_MANUAL`: preferred model for manual analysis (default `qwen2.5:1.5b`)
- `OLLAMA_MODEL_FALLBACKS`: comma-separated fallback chain (example `qwen2.5:1.5b`)
- `ANALYZE_STATEMENT_TIMEOUT_MS`: query timeout for analysis
- `PREVIEW_LIMIT`: max preview rows
- `LLM_ONLY_REWRITE`: if `true`, only the LLM provides rewrites
- `RULE_FALLBACK_REWRITE`: use deterministic rewrites when LLM cannot produce one
- `MEMORY_REWRITE_ENABLED`: enable JSONL memory fallback rewrites
- `TRAINING_STORE_ENABLED`: save training data in Postgres
- `LLM_TIMEOUT_LIVE` / `LLM_TIMEOUT_MANUAL`: LLM timeouts for live vs manual
- `LLM_MAX_PREDICT_LIVE` / `LLM_MAX_PREDICT_MANUAL`: output length caps
- `LLM_NUM_CTX_LIVE` / `LLM_NUM_CTX_MANUAL`: context window caps to control memory
- `LLM_TEMPERATURE` / `LLM_TOP_P`: keep generation deterministic for SQL
- `LLM_STREAM`: stream Ollama responses to reduce response-memory spikes
- `LLM_KEEP_ALIVE`: keep model loaded for warm responses without reloading each request
- `LLM_CACHE_TTL_SECONDS`: cache identical LLM analyses to avoid repeated generation
- `LLM_LOCK_WAIT_SECONDS`: max wait while another LLM call is in progress
- `LLM_SKIP_IF_BUSY_LIVE`: skip live LLM when model is busy instead of queueing
- `LLM_MAX_FINDINGS_LIVE` / `LLM_MAX_FINDINGS_MANUAL`: prompt trimming
- `LLM_MAX_INDEX_LIVE` / `LLM_MAX_INDEX_MANUAL`: prompt trimming
- `LLM_MAX_MEMORY_LIVE` / `LLM_MAX_MEMORY_MANUAL`: prompt trimming
- `LLM_LIVE_ENABLED`: enable/disable LLM calls for live typing mode (default `false` for low-RAM stability)
- `LLM_LIVE_MAX_SQL_CHARS`: skip live LLM for very long SQL
- `LLM_COOLDOWN_SECONDS`: pause live LLM after repeated pressure errors

Ollama container knobs (in `docker-compose.yml`):
- `OLLAMA_NUM_PARALLEL=1`: process one request at a time for stability
- `OLLAMA_MAX_LOADED_MODELS=1`: prevent multiple models from occupying memory
- `cpus: 2.0`: hard-cap Ollama CPU usage on local machine
- `mem_limit: 4g`: cap Ollama memory usage

## Documentation
- Architecture and system flow: `docs/ARCHITECTURE.md`
- Rule engine details: `docs/RULES.md`
- Function flow (plain-English): `docs/FUNCTION_FLOW.md`
- Training data storage: `docs/TRAINING_DATA.md`
- OpenShift deployment guide: `docs/OPENSHIFT.md`
