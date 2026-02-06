"""Simple local memory store that reuses past rewrites."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import re
from typing import Dict, List, Tuple

from .settings import MEMORY_PATH, SEED_MEMORY_PATH


TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


@dataclass
class MemoryExample:
    sql: str
    suggested_sql: str
    note: str = ""
    created_at: str = ""
    source: str = "memory"


def _tokenize(sql: str) -> set[str]:
    """Split SQL into basic word tokens."""
    return {token.lower() for token in TOKEN_RE.findall(sql)}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Measure how similar two token sets are (0 to 1)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _load_jsonl(path: Path, source: str) -> List[MemoryExample]:
    """Load rewrite examples from a JSONL file."""
    if not path.exists():
        return []
    examples: List[MemoryExample] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not payload.get("sql") or not payload.get("suggested_sql"):
            continue
        examples.append(
            MemoryExample(
                sql=payload["sql"],
                suggested_sql=payload["suggested_sql"],
                note=payload.get("note", ""),
                created_at=payload.get("created_at", ""),
                source=source,
            )
        )
    return examples


def load_examples() -> List[MemoryExample]:
    """Load seed examples and learned examples together."""
    examples: List[MemoryExample] = []
    examples.extend(_load_jsonl(Path(SEED_MEMORY_PATH), source="seed"))
    examples.extend(_load_jsonl(Path(MEMORY_PATH), source="memory"))
    return examples


def find_similar(sql: str, limit: int = 3) -> List[Dict[str, str | float]]:
    """Find the most similar past rewrites for a new query."""
    tokens = _tokenize(sql)
    scored: List[Tuple[float, MemoryExample]] = []
    for example in load_examples():
        similarity = _jaccard(tokens, _tokenize(example.sql))
        if similarity <= 0:
            continue
        scored.append((similarity, example))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for similarity, example in scored[:limit]:
        results.append(
            {
                "sql": example.sql,
                "suggested_sql": example.suggested_sql,
                "note": example.note,
                "similarity": round(similarity, 3),
                "source": example.source,
            }
        )
    return results


def append_example(sql: str, suggested_sql: str, note: str = "") -> None:
    """Save a new rewrite example so we can reuse it later."""
    if not sql or not suggested_sql:
        return

    path = Path(MEMORY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "sql": sql,
        "suggested_sql": suggested_sql,
        "note": note,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
