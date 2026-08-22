from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine, select

from .config import DATA_DIR, DATABASE_URL


DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

DEFAULT_ADMIN_PASSWORD = "P@ssword!"


def get_session():
    with Session(engine) as session:
        yield session


def _migrate_db() -> None:
    """Add new columns to existing tables without losing data (idempotent)."""
    new_cols = [
        ("auditlog", "query_hash",     "VARCHAR"),
        ("auditlog", "chunk_hashes",   "VARCHAR"),
        ("auditlog", "answer_hash",    "VARCHAR"),
        ("auditlog", "provenance_sig", "VARCHAR"),
        ("auditlog", "skill_name",     "VARCHAR"),
        ("auditlog", "document_id",    "VARCHAR"),
        ("team", "llm_provider",       "VARCHAR"),
        ("team", "llm_model",          "VARCHAR"),
        ("team", "embed_provider",     "VARCHAR"),
        ("team", "embed_model",        "VARCHAR"),
        ("team", "skills_enabled",     "BOOLEAN DEFAULT 1"),
        ("user", "failed_login_count", "INTEGER DEFAULT 0"),
        ("user", "locked_until",       "VARCHAR"),
    ]
    with engine.connect() as conn:
        for table, col, typ in new_cols:
            try:
                conn.execute(
                    __import__("sqlalchemy").text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                )
                conn.commit()
            except Exception:
                pass


def init_db() -> bool:
    """Create tables, run migrations, and seed a default admin. Returns True if first run."""
    from .models import (  # noqa: F401 — import so SQLModel registers tables
        AuditLog, GeneratedDocument, ModelRequest, SystemConfig, Team, TeamMember, User,
    )
    from .auth import hash_password
    from .models import SystemRole

    SQLModel.metadata.create_all(engine)
    _migrate_db()

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.system_role == SystemRole.admin)).first()
        if existing:
            return False

        admin = User(
            username             = "admin",
            email                = "admin@zettabrain.local",
            hashed_pw            = hash_password(DEFAULT_ADMIN_PASSWORD),
            system_role          = SystemRole.admin,
            must_change_password = True,
        )
        session.add(admin)
        session.commit()
        return True
