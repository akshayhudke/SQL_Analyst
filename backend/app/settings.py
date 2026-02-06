"""Read environment settings for the backend."""

import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sqluser:sqlpass@localhost:5432/sqllab")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
LLM_ENABLED = os.getenv("LLM_ENABLED", "true").lower() in {"1", "true", "yes"}
ANALYZE_STATEMENT_TIMEOUT_MS = int(os.getenv("ANALYZE_STATEMENT_TIMEOUT_MS", "8000"))
PREVIEW_LIMIT = int(os.getenv("PREVIEW_LIMIT", "100"))
MEMORY_PATH = os.getenv("MEMORY_PATH", "/app/data/memory.jsonl")
SEED_MEMORY_PATH = os.getenv("SEED_MEMORY_PATH", "/app/data/seed_examples.jsonl")
TRAINING_STORE_ENABLED = os.getenv("TRAINING_STORE_ENABLED", "true").lower() in {"1", "true", "yes"}
LLM_ONLY_REWRITE = os.getenv("LLM_ONLY_REWRITE", "true").lower() in {"1", "true", "yes"}
MEMORY_REWRITE_ENABLED = os.getenv("MEMORY_REWRITE_ENABLED", "false").lower() in {"1", "true", "yes"}
LLM_TIMEOUT_LIVE = int(os.getenv("LLM_TIMEOUT_LIVE", "45"))
LLM_TIMEOUT_MANUAL = int(os.getenv("LLM_TIMEOUT_MANUAL", "120"))
LLM_MAX_PREDICT_LIVE = int(os.getenv("LLM_MAX_PREDICT_LIVE", "400"))
LLM_MAX_PREDICT_MANUAL = int(os.getenv("LLM_MAX_PREDICT_MANUAL", "900"))
LLM_MAX_FINDINGS_LIVE = int(os.getenv("LLM_MAX_FINDINGS_LIVE", "6"))
LLM_MAX_FINDINGS_MANUAL = int(os.getenv("LLM_MAX_FINDINGS_MANUAL", "12"))
LLM_MAX_INDEX_LIVE = int(os.getenv("LLM_MAX_INDEX_LIVE", "6"))
LLM_MAX_INDEX_MANUAL = int(os.getenv("LLM_MAX_INDEX_MANUAL", "12"))
LLM_MAX_MEMORY_LIVE = int(os.getenv("LLM_MAX_MEMORY_LIVE", "1"))
LLM_MAX_MEMORY_MANUAL = int(os.getenv("LLM_MAX_MEMORY_MANUAL", "3"))
