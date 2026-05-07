"""
Atomicity tests for doc_id.next_doc_id.

Two tests:

  test_sequential          — 5 sequential calls are monotonic + contiguous.
  test_concurrent_burst    — 20 parallel calls (each in its own session) are
                             all unique and form a contiguous range.

The burst test is the one that would have failed against the previous
read-then-write implementation. Each coroutine owns its own AsyncSession so
they really race at the DB layer; SQLite serializes writes and each
UPDATE ... RETURNING returns a distinct value.

Run with:
  ./venv/bin/pytest tests/test_doc_id_counter.py -v
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from app.core.database import Base
from app.gateway.adapters.doc_id import next_doc_id
# Import the models so Base.metadata knows about them for create_all.
# Tenant must be imported because the User model (loaded transitively by
# pytest module discovery) declares a FK to tenants.id — without Tenant
# registered on Base.metadata, create_all raises NoReferencedTableError.
from app.models.document_id_counter import DocumentIdCounter  # noqa: F401
from app.models.document_log import DocumentLog  # noqa: F401
from app.models.tenant import Tenant  # noqa: F401
from app.models.user import User  # noqa: F401


TENANT_A = "tenant-a-uuid"


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    """Per-test in-memory SQLite. Shared cache so multiple sessions in the
    same test see the same database; the file-URI trick is the standard way
    to make aiosqlite :memory: visible across connections."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///file:doc_id_tests?mode=memory&cache=shared&uri=true",
        connect_args={"uri": True},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await eng.dispose()


@pytest.mark.asyncio
async def test_sequential(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)

    ids: list[str] = []
    async with Session() as s:
        for _ in range(5):
            ids.append(await next_doc_id(s, TENANT_A))
        await s.commit()

    nums = [int(d.split("-", 1)[1]) for d in ids]
    # Must be strictly monotonic and contiguous.
    assert nums == list(range(nums[0], nums[0] + 5))
    # And must be above the default bootstrap floor (2457+).
    assert nums[0] >= 2457


@pytest.mark.asyncio
async def test_concurrent_burst(engine: AsyncEngine) -> None:
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def one_caller() -> str:
        # Each coroutine owns its own session so they genuinely compete
        # at the DB layer, not on a shared session object.
        async with Session() as s:
            result = await next_doc_id(s, TENANT_A)
            await s.commit()
            return result

    results = await asyncio.gather(*(one_caller() for _ in range(20)))
    assert len(results) == 20

    nums = sorted(int(d.split("-", 1)[1]) for d in results)
    assert len(set(nums)) == 20, f"duplicates present: {nums}"
    # Contiguous range — no gaps, no repeats.
    assert nums == list(range(nums[0], nums[0] + 20)), f"non-contiguous: {nums}"
    assert nums[0] >= 2457
