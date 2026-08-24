from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent / "scripts"


def _deploy_setup_script() -> Path:
    """Copy bundled setup.sh to /opt/zettabrain-platform/setup.sh if newer."""
    dest_dir = Path("/opt/zettabrain-platform")
    dest = dest_dir / "setup.sh"
    src  = _SCRIPTS_DIR / "setup.sh"
    if src.exists():
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        dest.chmod(0o755)
    return dest


def setup():
    """Entry point for zettabrain-platform-setup."""
    parser = argparse.ArgumentParser(
        prog="zettabrain-platform-setup",
        description="ZettaBrain Platform — one-command server setup (run as root)",
    )
    parser.add_argument("--port",       default="7861",            help="Port to serve on (default 7861)")
    parser.add_argument("--llm",        default="llama3.1:8b",     help="Ollama LLM model")
    parser.add_argument("--embed",      default="nomic-embed-text", help="Ollama embedding model")
    parser.add_argument("--no-systemd", action="store_true",        help="Skip systemd service setup")
    args = parser.parse_args()

    src = _SCRIPTS_DIR / "setup.sh"
    if not src.exists():
        print("ERROR: setup.sh not found in package — reinstall zettabrain-platform")
        sys.exit(1)

    cmd = ["bash", str(src), "--port", args.port, "--llm", args.llm, "--embed", args.embed]
    if args.no_systemd:
        cmd.append("--no-systemd")

    env = {**os.environ, "ZETTABRAIN_LLM_MODEL": args.llm, "ZETTABRAIN_EMBED_MODEL": args.embed}
    try:
        subprocess.run(cmd, check=True, env=env)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nSetup interrupted.")
        sys.exit(1)


def main():
    """Entry point for zettabrain-platform (server)."""
    parser = argparse.ArgumentParser(
        prog="zettabrain-platform",
        description="ZettaBrain Platform — multi-user RAG server",
    )
    parser.add_argument("--port",   type=int, default=None,    help="Override port (default 7861)")
    parser.add_argument("--host",   default="0.0.0.0",         help="Bind host")
    parser.add_argument("--reload", action="store_true",        help="Enable uvicorn auto-reload (dev only)")
    args = parser.parse_args()

    from .config import PORT, TLS_CERT, TLS_ENABLED, TLS_KEY

    port = args.port or PORT

    try:
        import uvicorn
    except ImportError:
        print("uvicorn not found — install zettabrain-platform with all dependencies")
        sys.exit(1)

    kwargs: dict = {
        "app":    "zettabrain_platform.server:app",
        "host":   args.host,
        "port":   port,
        "reload": args.reload,
    }
    if TLS_ENABLED:
        kwargs["ssl_certfile"] = TLS_CERT
        kwargs["ssl_keyfile"]  = TLS_KEY
        print(f"Starting ZettaBrain Platform on https://{args.host}:{port}")
    else:
        print(f"Starting ZettaBrain Platform on http://{args.host}:{port}")

    uvicorn.run(**kwargs)


if __name__ == "__main__":
    main()
