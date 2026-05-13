# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

# ✅ Direct env read to avoid circular imports with app/config.py
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./pashumitra_dev.db")

# ✅ Build engine — SQLite and PostgreSQL need different pool settings
#    BUG FIXED: SQLite does NOT support pool_size / max_overflow (raises ArgumentError).
#               It also requires check_same_thread=False for use with FastAPI threads.
#    FIX: detect driver and apply correct engine kwargs.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},  # Required for FastAPI/threading
        poolclass=StaticPool,                        # Single connection pool for SQLite
        pool_pre_ping=True,                          # Auto-reconnect on stale connections
    )
else:
    # PostgreSQL / MySQL — pool_size and max_overflow are valid here
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

# ✅ Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ✅ Declarative base for ORM models
Base = declarative_base()


# ✅ FastAPI dependency — use with Depends(get_db)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()