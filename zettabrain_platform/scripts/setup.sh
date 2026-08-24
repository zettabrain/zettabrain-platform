#!/usr/bin/env bash
# ZettaBrain Platform — server setup
# Usage: sudo bash setup.sh [--port PORT] [--llm MODEL] [--embed MODEL] [--no-systemd]
set -euo pipefail

# ── defaults (empty = prompt interactively) ───────────────────────────────────
ZBP_PORT="${ZBP_PORT:-7861}"
LLM_MODEL="${ZETTABRAIN_LLM_MODEL:-}"
EMBED_MODEL="${ZETTABRAIN_EMBED_MODEL:-}"
INSTALL_SYSTEMD=true
BASE_DIR="/opt/zettabrain-platform"
ENV_FILE="$BASE_DIR/platform.env"

# ── arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --port)       ZBP_PORT="$2";    shift 2 ;;
    --llm)        LLM_MODEL="$2";   shift 2 ;;
    --embed)      EMBED_MODEL="$2"; shift 2 ;;
    --no-systemd) INSTALL_SYSTEMD=false; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
info() { echo -e "${YELLOW}  → $*${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}"; exit 1; }
hdr()  { echo -e "${CYAN}$*${NC}"; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║      ZettaBrain Platform — Setup         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── root check ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  err "Run as root: sudo bash setup.sh"
fi

# ── detect OS ─────────────────────────────────────────────────────────────────
if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  OS_ID="${ID:-linux}"
else
  OS_ID="linux"
fi
info "OS: $OS_ID"

# ── 1. Python 3 ───────────────────────────────────────────────────────────────
echo "[1/6] Checking Python..."
if ! command -v python3 &>/dev/null; then
  info "Installing python3..."
  apt-get update -qq && apt-get install -y -qq python3 python3-pip
fi
PYTHON_VER=$(python3 --version)
ok "Python: $PYTHON_VER"

# ── 2. pipx ───────────────────────────────────────────────────────────────────
echo "[2/6] Checking pipx..."
if ! command -v pipx &>/dev/null; then
  info "Installing pipx..."
  python3 -m pip install --quiet pipx
  python3 -m pipx ensurepath
fi
ok "pipx ready"

# ── 3. zettabrain-rag + zettabrain-platform ──────────────────────────────────
echo "[3/6] Installing zettabrain-rag + zettabrain-platform..."

if pipx list 2>/dev/null | grep -q zettabrain-rag; then
  info "zettabrain-rag already installed — upgrading..."
  pipx upgrade zettabrain-rag 2>/dev/null || true
else
  pipx install zettabrain-rag
fi
ok "zettabrain-rag CLI installed"

if pipx list 2>/dev/null | grep -q zettabrain-platform; then
  info "zettabrain-platform already installed — upgrading..."
  pipx upgrade zettabrain-platform 2>/dev/null || pipx reinstall zettabrain-platform
else
  pipx install zettabrain-platform
fi

ZBP_BIN=$(command -v zettabrain-platform 2>/dev/null || true)
if [[ -z "$ZBP_BIN" ]]; then
  for p in /root/.local/bin/zettabrain-platform /home/ubuntu/.local/bin/zettabrain-platform; do
    [[ -f "$p" ]] && ZBP_BIN="$p" && break
  done
fi
[[ -z "$ZBP_BIN" ]] && err "Could not locate zettabrain-platform binary after install"
ok "zettabrain-platform installed at $ZBP_BIN"

# ── 4. Ollama ─────────────────────────────────────────────────────────────────
echo "[4/6] Checking Ollama..."
if ! command -v ollama &>/dev/null; then
  info "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
fi

if ! systemctl is-active --quiet ollama 2>/dev/null; then
  info "Starting Ollama service..."
  systemctl enable ollama --now 2>/dev/null || ollama serve &>/var/log/ollama.log &
  sleep 3
fi
ok "Ollama running"

# ── Model selection ────────────────────────────────────────────────────────────
echo ""
hdr "── Model Selection ──────────────────────────────────────────────────────"

# LLM model
if [[ -z "$LLM_MODEL" ]]; then
  echo ""
  echo "  Select LLM model:"
  echo "    1) llama3.1:8b     (recommended — balanced quality, ~8 GB RAM)"
  echo "    2) llama3.2:3b     (fastest, ~4 GB RAM, less capable)"
  echo "    3) mistral:7b      (strong for structured / legal documents)"
  echo "    4) gemma2:9b       (Google model, good reasoning)"
  echo "    5) qwen2.5:7b      (multilingual)"
  echo "    6) llama3.1:70b    (best quality, needs ~40 GB RAM)"
  echo "    7) Custom          (enter any Ollama model name)"
  echo ""
  read -rp "  LLM choice [1]: " _LLM_CHOICE
  case "${_LLM_CHOICE:-1}" in
    1|"") LLM_MODEL="llama3.1:8b" ;;
    2)    LLM_MODEL="llama3.2:3b" ;;
    3)    LLM_MODEL="mistral:7b" ;;
    4)    LLM_MODEL="gemma2:9b" ;;
    5)    LLM_MODEL="qwen2.5:7b" ;;
    6)    LLM_MODEL="llama3.1:70b" ;;
    7)    read -rp "  Enter model name (e.g. phi3:mini): " LLM_MODEL ;;
    *)    LLM_MODEL="${_LLM_CHOICE}" ;;
  esac
fi
ok "LLM model: $LLM_MODEL"

# Embedding model
if [[ -z "$EMBED_MODEL" ]]; then
  echo ""
  echo "  Select embedding model:"
  echo "    1) nomic-embed-text   (recommended — fast, great recall)"
  echo "    2) mxbai-embed-large  (higher quality, slower)"
  echo "    3) all-minilm         (smallest / fastest)"
  echo "    4) Custom             (enter any Ollama embedding model name)"
  echo ""
  read -rp "  Embed choice [1]: " _EMBED_CHOICE
  case "${_EMBED_CHOICE:-1}" in
    1|"") EMBED_MODEL="nomic-embed-text" ;;
    2)    EMBED_MODEL="mxbai-embed-large" ;;
    3)    EMBED_MODEL="all-minilm" ;;
    4)    read -rp "  Enter model name: " EMBED_MODEL ;;
    *)    EMBED_MODEL="${_EMBED_CHOICE}" ;;
  esac
fi
ok "Embed model: $EMBED_MODEL"

echo ""
info "Pulling embedding model: $EMBED_MODEL ..."
ollama pull "$EMBED_MODEL"
ok "Embed model ready"

info "Pulling LLM: $LLM_MODEL (may take a few minutes for large models)..."
ollama pull "$LLM_MODEL"
ok "LLM ready"

# ── 5. Directories & env ──────────────────────────────────────────────────────
echo "[5/6] Creating directories..."
mkdir -p "$BASE_DIR"/{data,chromadb,certs}
ok "Directories created at $BASE_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<EOF
ZBP_PORT=$ZBP_PORT
ZETTABRAIN_LLM_MODEL=$LLM_MODEL
ZETTABRAIN_EMBED_MODEL=$EMBED_MODEL
EOF
  ok "Config written to $ENV_FILE"
else
  sed -i "s|^ZETTABRAIN_LLM_MODEL=.*|ZETTABRAIN_LLM_MODEL=$LLM_MODEL|" "$ENV_FILE"
  sed -i "s|^ZETTABRAIN_EMBED_MODEL=.*|ZETTABRAIN_EMBED_MODEL=$EMBED_MODEL|" "$ENV_FILE"
  ok "Config updated at $ENV_FILE"
fi

# ── 6. Systemd service ────────────────────────────────────────────────────────
echo "[6/6] Setting up systemd service..."
if [[ "$INSTALL_SYSTEMD" == "true" ]]; then
  cat > /etc/systemd/system/zettabrain-platform.service <<EOF
[Unit]
Description=ZettaBrain Platform Server
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
EnvironmentFile=$ENV_FILE
ExecStart=$ZBP_BIN
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable zettabrain-platform
  systemctl restart zettabrain-platform
  sleep 4

  if systemctl is-active --quiet zettabrain-platform; then
    ok "Service running"
  else
    echo ""
    echo "Service failed to start. Logs:"
    journalctl -u zettabrain-platform -n 30 --no-pager
    exit 1
  fi
else
  info "Skipping systemd (--no-systemd). Start manually: $ZBP_BIN"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        ZettaBrain Platform — Setup Complete          ║"
echo "╠══════════════════════════════════════════════════════╣"
printf "║  %-52s║\n" "User portal  : http://$SERVER_IP:$ZBP_PORT"
printf "║  %-52s║\n" "Admin portal : http://$SERVER_IP:$ZBP_PORT/admin"
printf "║  %-52s║\n" "Credentials  : admin / P@ssword! (change on first login)"
printf "║  %-52s║\n" "Data         : $BASE_DIR"
printf "║  %-52s║\n" "Logs         : journalctl -u zettabrain-platform -f"
printf "║  %-52s║\n" "LLM          : $LLM_MODEL"
printf "║  %-52s║\n" "Embed        : $EMBED_MODEL"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Next steps:                                         ║"
printf "║    1. Open port %-37s║\n" "$ZBP_PORT in your firewall / security group"
echo "║    2. Go to /admin, change default password          ║"
echo "║    3. Create teams and add users                     ║"
echo "║    4. Set docs folder per team and click Ingest Docs ║"
echo "║    5. Upload skills for document generation          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
