from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


def _normalise_database_url(url: str) -> str:
    """Force an async driver onto the configured DATABASE_URL.

    Render's managed Postgres exposes a plain `postgres://...` connection
    string. SQLAlchemy 2.x rejects that scheme and SQLAlchemy async needs
    the asyncpg driver explicitly. We rewrite both forms here so the rest
    of the app can stay scheme-agnostic.

    SQLite URLs are passed through unchanged — local dev still uses
    aiosqlite via the default in settings.DATABASE_URL.
    """
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalise_database_url(settings.DATABASE_URL)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# `timeout` forwards to aiosqlite → sqlite3.connect(timeout=...); sets the
# busy-wait interval (seconds) instead of failing immediately on a locked
# DB. Required for concurrent writers — our doc_id counter UPDATE RETURNING
# serializes across connections, and a 20-request burst trivially queues
# past any default timeout.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30} if IS_SQLITE else {},
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Enable WAL journal mode on every SQLite connection — readers don't block
# writers and vice versa, which cuts SQLITE_BUSY under bursty load.
if IS_SQLITE:
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
