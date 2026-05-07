from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# `timeout` forwards to aiosqlite → sqlite3.connect(timeout=...); sets the
# busy-wait interval (seconds) instead of failing immediately on a locked
# DB. Required for concurrent writers — our doc_id counter UPDATE RETURNING
# serializes across connections, and a 20-request burst trivially queues
# past any default timeout.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30} if settings.DATABASE_URL.startswith("sqlite") else {},
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Enable WAL journal mode on every SQLite connection — readers don't block
# writers and vice versa, which cuts SQLITE_BUSY under bursty load.
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_on_connect(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
