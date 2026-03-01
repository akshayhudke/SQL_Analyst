"""Read environment settings for the backend."""

import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sqluser:sqlpass@localhost:5432/sqllab")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_MODEL_LIVE = os.getenv("OLLAMA_MODEL_LIVE", "qwen2.5:1.5b")
OLLAMA_MODEL_MANUAL = os.getenv("OLLAMA_MODEL_MANUAL", "qwen2.5:1.5b")
OLLAMA_MODEL_FALLBACKS = [
    item.strip()
    for item in os.getenv("OLLAMA_MODEL_FALLBACKS", "qwen2.5:1.5b").split(",")
    if item.strip()
]
LLM_ENABLED = os.getenv("LLM_ENABLED", "true").lower() in {"1", "true", "yes"}
LLM_LIVE_ENABLED = os.getenv("LLM_LIVE_ENABLED", "false").lower() in {"1", "true", "yes"}
ANALYZE_STATEMENT_TIMEOUT_MS = int(os.getenv("ANALYZE_STATEMENT_TIMEOUT_MS", "8000"))
PREVIEW_LIMIT = int(os.getenv("PREVIEW_LIMIT", "100"))
MEMORY_PATH = os.getenv("MEMORY_PATH", "/app/data/memory.jsonl")
SEED_MEMORY_PATH = os.getenv("SEED_MEMORY_PATH", "/app/data/seed_examples.jsonl")
TRAINING_STORE_ENABLED = os.getenv("TRAINING_STORE_ENABLED", "true").lower() in {"1", "true", "yes"}
LLM_ONLY_REWRITE = os.getenv("LLM_ONLY_REWRITE", "true").lower() in {"1", "true", "yes"}
RULE_FALLBACK_REWRITE = os.getenv("RULE_FALLBACK_REWRITE", "true").lower() in {"1", "true", "yes"}
MEMORY_REWRITE_ENABLED = os.getenv("MEMORY_REWRITE_ENABLED", "false").lower() in {"1", "true", "yes"}
LLM_TIMEOUT_LIVE = int(os.getenv("LLM_TIMEOUT_LIVE", "20"))
LLM_TIMEOUT_MANUAL = int(os.getenv("LLM_TIMEOUT_MANUAL", "30"))
LLM_MAX_PREDICT_LIVE = int(os.getenv("LLM_MAX_PREDICT_LIVE", "180"))
LLM_MAX_PREDICT_MANUAL = int(os.getenv("LLM_MAX_PREDICT_MANUAL", "180"))
LLM_NUM_CTX_LIVE = int(os.getenv("LLM_NUM_CTX_LIVE", "1024"))
LLM_NUM_CTX_MANUAL = int(os.getenv("LLM_NUM_CTX_MANUAL", "1024"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.9"))
LLM_STREAM = os.getenv("LLM_STREAM", "true").lower() in {"1", "true", "yes"}
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "15m")
LLM_CACHE_TTL_SECONDS = int(os.getenv("LLM_CACHE_TTL_SECONDS", "180"))
LLM_LOCK_WAIT_SECONDS = int(os.getenv("LLM_LOCK_WAIT_SECONDS", "3"))
LLM_SKIP_IF_BUSY_LIVE = os.getenv("LLM_SKIP_IF_BUSY_LIVE", "true").lower() in {"1", "true", "yes"}
LLM_MAX_FINDINGS_LIVE = int(os.getenv("LLM_MAX_FINDINGS_LIVE", "6"))
LLM_MAX_FINDINGS_MANUAL = int(os.getenv("LLM_MAX_FINDINGS_MANUAL", "12"))
LLM_MAX_INDEX_LIVE = int(os.getenv("LLM_MAX_INDEX_LIVE", "6"))
LLM_MAX_INDEX_MANUAL = int(os.getenv("LLM_MAX_INDEX_MANUAL", "12"))
LLM_MAX_MEMORY_LIVE = int(os.getenv("LLM_MAX_MEMORY_LIVE", "1"))
LLM_MAX_MEMORY_MANUAL = int(os.getenv("LLM_MAX_MEMORY_MANUAL", "3"))
LLM_LIVE_MAX_SQL_CHARS = int(os.getenv("LLM_LIVE_MAX_SQL_CHARS", "1200"))
LLM_COOLDOWN_SECONDS = int(os.getenv("LLM_COOLDOWN_SECONDS", "25"))
