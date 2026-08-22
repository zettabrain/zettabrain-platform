"""FastAPI application — unified ZettaBrain Platform server."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import CHROMA_DIR, DATA_DIR, SKILLS_DIR
from .database import init_db
from .provenance import init_signing_key
from .routers import auth, chat, generate, ingest, settings, teams

app = FastAPI(
    title="ZettaBrain Platform",
    description="Unified conversational + generative AI with multi-tenant access control",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)


@app.get("/api/docs", include_in_schema=False)
async def swagger_docs():
    return HTMLResponse("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><title>ZettaBrain Platform - API Docs</title>
<link rel="stylesheet" href="/static/vendor/swagger-ui.css">
<style>body{margin:0} .topbar{display:none}</style>
</head>
<body>
<div id="swagger-ui"></div>
<script src="/static/vendor/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({url:"/openapi.json",dom_id:"#swagger-ui",presets:[SwaggerUIBundle.presets.apis,SwaggerUIBundle.SwaggerUIStandalonePreset],layout:"BaseLayout"})
</script>
</body>
</html>""")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(teams.router)
app.include_router(chat.router)
app.include_router(ingest.router)
app.include_router(generate.router)
app.include_router(settings.router)

# Static files
_STATIC = Path(__file__).parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/", include_in_schema=False)
def index():
    index_file = _STATIC / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"service": "zettabrain-platform", "version": "0.1.0", "docs": "/api/docs"}


@app.get("/api/status")
def status():
    return {
        "service": "zettabrain-platform",
        "version": "0.1.0",
        "data_dir": str(DATA_DIR),
        "chroma_dir": str(CHROMA_DIR),
        "skills_dir": str(SKILLS_DIR),
        "db_exists": (DATA_DIR / "platform.db").exists(),
    }


@app.on_event("startup")
def on_startup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
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
    print(f"  ZettaBrain Verified — server public key: {pub_key[:16]}...")
