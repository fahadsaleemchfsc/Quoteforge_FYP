"""
Atomic document-ID generation.

Concurrent request_quote calls previously computed `DOC-{count+1}` via a
read-then-write race and collided on document_logs.doc_id UNIQUE. This
replaces that with a single UPDATE ... RETURNING against a per-tenant
counter row, plus a lazy bootstrap that is safe under first-call racing.

Contract:
  next_doc_id(session, tenant_id) -> "DOC-N"

  - Never reads the counter before writing it.
  - Lazy-bootstraps the row via INSERT ... ON CONFLICT DO NOTHING on first
    use for a tenant; concurrent first-callers converge rather than collide.
  - Callers hold their own transaction. SQLite's writer-serialization + the
    UPDATE RETURNING atomicity together guarantee each concurrent caller
    sees a distinct returned value.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import func, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_id_counter import DocumentIdCounter
from app.models.document_log import DocumentLog

logger = logging.getLogger(__name__)

# First emitted id is DOC-(DEFAULT_BOOTSTRAP_LAST_NUMBER + 1) = DOC-2457.
DEFAULT_BOOTSTRAP_LAST_NUMBER = 2456

_DOC_SUFFIX = re.compile(r"^DOC-(\d+)$")


async def _global_max_doc_number(session: AsyncSession) -> int:
    """Max numeric suffix across every DocumentLog row. Used for bootstrap
    to guarantee we never issue a doc_id below an already-existing one."""
    rows = (await session.execute(select(DocumentLog.doc_id))).all()
    best = 0
    for (doc_id,) in rows:
        if not doc_id:
            continue
        m = _DOC_SUFFIX.match(doc_id)
        if not m:
            continue
        try:
            n = int(m.group(1))
        except ValueError:
            continue
        if n > best:
            best = n
    return best


async def _bootstrap_value(session: AsyncSession) -> int:
    """Value to store as last_number on first bootstrap of a counter row.

    max(global max doc number, DEFAULT_BOOTSTRAP_LAST_NUMBER). Stored as the
    last-issued number, so the next UPDATE-RETURNING returns that + 1.
    """
    global_max = await _global_max_doc_number(session)
    return max(global_max, DEFAULT_BOOTSTRAP_LAST_NUMBER)


async def next_doc_id(session: AsyncSession, tenant_id: str) -> str:
    """
    Atomically increment and return the next DOC-N for this tenant.

    Single-statement UPDATE ... RETURNING. Under concurrency SQLite serializes
    the writes, and each caller receives a unique incremented value.

    If the counter row does not yet exist, lazy-bootstraps it via
    INSERT ON CONFLICT DO NOTHING, then retries the UPDATE. The bootstrap
    value is max(global doc_id suffix, DEFAULT_BOOTSTRAP_LAST_NUMBER), so
    the first emitted id is strictly greater than any existing DocumentLog.doc_id.

    Callers hold the session / transaction. This function does not commit.
    """
    # Fast path — row already exists, single UPDATE RETURNING.
    result = await session.execute(
        text(
            "UPDATE document_id_counters "
            "SET last_number = last_number + 1 "
            "WHERE tenant_id = :tid "
            "RETURNING last_number"
        ),
        {"tid": tenant_id},
    )
    row = result.first()
    if row is not None:
        return f"DOC-{row[0]}"

    # Slow path — counter doesn't exist yet. Bootstrap atomically.
    bootstrap = await _bootstrap_value(session)
    insert_stmt = (
        sqlite_insert(DocumentIdCounter)
        .values(tenant_id=tenant_id, last_number=bootstrap)
        .on_conflict_do_nothing(index_elements=["tenant_id"])
    )
    await session.execute(insert_stmt)

    # Retry the atomic UPDATE; at this point the row definitely exists
    # (either we inserted it, or a concurrent bootstrapper did).
    retry = await session.execute(
        text(
            "UPDATE document_id_counters "
            "SET last_number = last_number + 1 "
            "WHERE tenant_id = :tid "
            "RETURNING last_number"
        ),
        {"tid": tenant_id},
    )
    row = retry.first()
    if row is None:
        # Genuinely impossible given we just inserted-or-observed-the-row,
        # but surface a clear error rather than silently return the wrong value.
        raise RuntimeError(f"counter row missing after bootstrap for tenant={tenant_id}")
    return f"DOC-{row[0]}"
