from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator
from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Create database engine
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False
)

@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    # Simplify the SQL statement to look like a clean cyber-query
    stmt_str = str(statement)
    clean_stmt = stmt_str.replace('\n', ' ').strip()
    action = "READ" if "SELECT" in clean_stmt[:10].upper() else "WRITE" if any(x in clean_stmt[:10].upper() for x in ["INSERT", "UPDATE", "DELETE"]) else "AFFECT"
    
    # Try to extract table name for a cooler log
    table = "UNKNOWN_NODE"
    words = clean_stmt.split()
    for i, word in enumerate(words):
        if word.upper() in ["FROM", "INTO", "UPDATE"] and i + 1 < len(words):
            table = words[i+1].strip('"\'`[]')
            break
            
    logger.log_db_query(f"{action}_MATRIX", table, clean_stmt[:60] + "..." if len(clean_stmt) > 60 else clean_stmt)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function to get database session
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_db():
    """Add new columns to existing tables (idempotent — safe to run every startup)."""
    new_columns = [
        "ALTER TABLE profiles ADD COLUMN youtube_url TEXT",
        "ALTER TABLE profiles ADD COLUMN reddit_url TEXT",
        "ALTER TABLE profiles ADD COLUMN facebook_url TEXT",
    ]
    with engine.connect() as conn:
        for sql in new_columns:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # Column already exists — safe to ignore


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    _migrate_db()
