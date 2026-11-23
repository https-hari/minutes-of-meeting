from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (add it to .env)")

# SQLAlchemy 2.1 defaults "postgresql://" to psycopg 3; this project ships psycopg2
_url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1) \
    if DATABASE_URL.startswith("postgresql://") else DATABASE_URL

engine = create_engine(_url, pool_pre_ping=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
