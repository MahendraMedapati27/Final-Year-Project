"""Process memory logging for pipeline steps."""

from __future__ import annotations

import json
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

from rainfall.config import project_root


def rss_mb() -> float:
    if psutil is None:
        return float("nan")
    return psutil.Process().memory_info().rss / (1024 * 1024)


def log_step(step: str, extra: dict | None = None) -> None:
    log_dir = project_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    rec = {
        "step": step,
        "rss_mb": rss_mb(),
        "ts": time.time(),
    }
    if extra:
        rec.update(extra)
    line = json.dumps(rec)
    with (log_dir / "clean_memory.jsonl").open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(f"[mem] {step}: RSS={rec['rss_mb']:.1f} MB")
