"""CLI entry point for ZettaBrain Platform."""

from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="ZettaBrain Platform")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "setup"])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    if args.command == "setup":
        from .config import DATA_DIR, CHROMA_DIR, SKILLS_DIR
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        from .database import init_db
        first_run = init_db()
        if first_run:
            print("Database initialized with default admin (admin / P@ssword!)")
        else:
            print("Database already exists, migrations applied.")
        return

    # serve
    import uvicorn
    from .config import PORT, TLS_CERT, TLS_ENABLED, TLS_KEY

    port = args.port or PORT
    ssl_kwargs = {}
    if TLS_ENABLED:
        ssl_kwargs = {"ssl_certfile": TLS_CERT, "ssl_keyfile": TLS_KEY}
        print(f"  TLS enabled — https://0.0.0.0:{port}")

    uvicorn.run(
        "zettabrain_platform.server:app",
        host=args.host,
        port=port,
        reload=False,
        **ssl_kwargs,
    )


if __name__ == "__main__":
    main()
