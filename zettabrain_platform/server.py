from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import state
from .config import CHROMA_DIR, DATA_DIR
from .database import init_db
from .provenance import init_signing_key
from .routers import admin, auth, chat, ingest, ldap as ldap_router, teams
from .routers import model_requests as model_requests_router
from .routers import notifications as notifications_router
from .routers import settings as settings_router
from .routers import generate as generate_router

app = FastAPI(title="ZettaBrain Platform", version="0.3.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(teams.router)
app.include_router(chat.router)
app.include_router(ingest.router)
app.include_router(admin.router)
app.include_router(settings_router.router)
app.include_router(ldap_router.router)
app.include_router(model_requests_router.router)
app.include_router(notifications_router.router)
app.include_router(generate_router.router)

_STATIC = Path(__file__).parent / "static"

# Serve static files (CSS, JS, images) at /static/...
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(str(_STATIC / "index.html"))


@app.get("/admin", include_in_schema=False)
def admin_portal():
    return FileResponse(str(_STATIC / "index.html"))


@app.get("/api/status")
def status():
    return {
        "service": "zettabrain-platform",
        "version": "0.3.0",
        "data_dir": str(DATA_DIR),
        "chroma_dir": str(CHROMA_DIR),
        "teams_db_exists": (DATA_DIR / "teams.db").exists(),
    }


@app.on_event("startup")
def on_startup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    pub_key   = init_signing_key(DATA_DIR)
    first_run = init_db()
    if first_run:
        print("\n" + "=" * 60)
        print("  ZettaBrain Platform — first-run setup")
        print("  Default admin credentials:")
        print("    Username : admin")
        print("    Password : P@ssword!")
        print("  You will be prompted to change this on first login.")
        print("=" * 60 + "\n")
    print(f"  ZettaBrain Verified — server public key: {pub_key[:16]}…")
    from .license import check_startup
    state.license_info = check_startup(DATA_DIR)
