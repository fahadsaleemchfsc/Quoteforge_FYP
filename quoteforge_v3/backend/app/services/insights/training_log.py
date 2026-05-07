"""
Visible training log — append-only text file the defense demo can `tail -f`.

Every major training step writes a timestamped line both to the tenant's
training_log.txt and via the Python logger at INFO level so uvicorn console
shows the same events. The log file lives alongside the model pickles at
storage/insights_models/{tenant_id}/training_log.txt.

Usage:
    with TrainingLogger(tenant_id) as log:
        log.info("dataset loaded: 5000 rows")
        log.info("train/test split: 4000/1000")
        log.info("  [boost 50] train_loss=0.421  val_loss=0.467")
        ...

On exception inside the `with` block, the full traceback is written to the
log and re-raised so the API caller still sees it.
"""
from __future__ import annotations

import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

logger = logging.getLogger(__name__)

LOG_FILENAME = "training_log.txt"
LOG_RUN_SEPARATOR = "─" * 70


class TrainingLogger:
    """Context manager that appends to the tenant's training_log.txt."""

    def __init__(self, tenant_id: str, *, model_root: str | None = None) -> None:
        from app.services.insights.trainer import MODEL_STORAGE_ROOT
        root = model_root or MODEL_STORAGE_ROOT
        self.tenant_dir = Path(root) / tenant_id
        self.tenant_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.tenant_dir / LOG_FILENAME
        self._fh: TextIO | None = None
        self._run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    def __enter__(self) -> "TrainingLogger":
        self._fh = open(self.path, "a", buffering=1, encoding="utf-8")
        self._write_header()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None and self._fh is not None:
            self._write_line("ERROR  " + str(exc))
            self._fh.write(traceback.format_exc())
            self._fh.flush()
        if self._fh is not None:
            self._write_line("--- run end ---")
            self._fh.close()
            self._fh = None

    def info(self, msg: str) -> None:
        self._write_line(msg)
        logger.info("insights.train: %s", msg)

    def error(self, msg: str) -> None:
        self._write_line("ERROR  " + msg)
        logger.error("insights.train: %s", msg)

    def kv(self, **kwargs: Any) -> None:
        """Write key=value pairs on one line."""
        self.info("  " + "  ".join(f"{k}={v}" for k, v in kwargs.items()))

    def _write_header(self) -> None:
        if self._fh is None:
            return
        self._fh.write("\n" + LOG_RUN_SEPARATOR + "\n")
        self._fh.write(f"RUN {self._run_id}  tenant={self.tenant_dir.name}\n")
        self._fh.write(LOG_RUN_SEPARATOR + "\n")
        self._fh.flush()

    def _write_line(self, msg: str) -> None:
        if self._fh is None:
            return
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._fh.write(f"[{ts}] {msg}\n")
        self._fh.flush()
