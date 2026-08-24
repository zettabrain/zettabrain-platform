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
        # Model delegation: team-level model configuration
        ("team", "llm_provider",   "VARCHAR"),
        ("team", "llm_model",      "VARCHAR"),
        ("team", "embed_provider", "VARCHAR"),
        ("team", "embed_model",    "VARCHAR"),
        # Multi-embedding storage
        ("team", "multi_embed_allowed", "BOOLEAN DEFAULT 0"),
        ("team", "multi_embed_enabled", "BOOLEAN DEFAULT 0"),
    ]
    with engine.connect() as conn:
        for table, col, typ in new_cols:
            try:
                conn.execute(  # type: ignore[arg-type]
                    __import__("sqlalchemy").text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
                )
                conn.commit()
            except Exception:
                pass  # column already exists — ignore


def init_db() -> bool:
    """Create tables, run migrations, and seed a default admin. Returns True if first run."""
    SQLModel.metadata.create_all(engine)
    _migrate_db()

    from .models import SystemRole, User
    from .auth import hash_password

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
