#!/usr/bin/env bash
# Token-Jet local installer — run this directly on the Jetson.
#
# Bootstrap (from a fresh Jetson — no clone needed first):
#   curl -sL https://raw.githubusercontent.com/o3willard-AI/Token-Jet/main/scripts/install-local.sh | bash
#
# From a cloned repo:
#   ./scripts/install-local.sh
#   ./scripts/install-local.sh --upgrade
#   ./scripts/install-local.sh --uninstall
#
# Options:
#   --upgrade    Pull latest from GitHub, update TUI and jetson-infer; preserve config and models
#   --uninstall  Remove TUI, launcher, and systemd service (models and config are kept)
#   -h, --help   Show this help

set -euo pipefail

REPO_URL="https://github.com/o3willard-AI/Token-Jet.git"
CLONE_DIR="${HOME}/Token-Jet"
MODE="install"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --upgrade)   MODE="upgrade";   shift ;;
        --uninstall) MODE="uninstall"; shift ;;
        -h|--help)   sed -n '2,16p' "$0" | sed 's/^# //'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ── Detect repo root ──────────────────────────────────────────────────────────
# When piped from curl, $0 is "-" — we must clone.
# When run directly, derive root from the script path.
if [[ "$0" == "-" || "$0" == "/dev/stdin" ]]; then
    PIPED=true
else
    PIPED=false
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    if [[ -f "${SCRIPT_DIR}/../jetson-infer" ]]; then
        REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
    else
        PIPED=true   # Script was copied somewhere without the rest of the repo
    fi
fi

if $PIPED; then
    REPO_ROOT="$CLONE_DIR"
fi

# ── Clone or update repo ──────────────────────────────────────────────────────
if [[ ! -d "${REPO_ROOT}/.git" ]]; then
    echo "Cloning Token-Jet to ${REPO_ROOT}..."
    git clone "$REPO_URL" "$REPO_ROOT"
    echo "  cloned OK"
elif [[ "$MODE" == "upgrade" ]]; then
    echo "Updating Token-Jet repo..."
    git -C "$REPO_ROOT" pull --ff-only
    echo "  repo updated OK"
fi

# ── Paths ─────────────────────────────────────────────────────────────────────
INSTALL_BASE="${HOME}/.local/share/token-jet"
BIN_DIR="${HOME}/.local/bin"
CONFIG_DIR="${HOME}/.config/token-jet"
JETSON_USER="${USER:-$(id -un)}"

echo ""
echo "=== Token-Jet Installer ==="
echo "Mode:    $MODE"
echo "Repo:    $REPO_ROOT"
echo "Install: $INSTALL_BASE"
echo ""

# ── Uninstall ─────────────────────────────────────────────────────────────────
if [[ "$MODE" == "uninstall" ]]; then
    echo "Removing Token-Jet..."
    systemctl --user stop    jetson-infer 2>/dev/null || true
    systemctl --user disable jetson-infer 2>/dev/null || true
    rm -f ~/.config/systemd/user/jetson-infer.service
    systemctl --user daemon-reload 2>/dev/null || true
    rm -rf  "$INSTALL_BASE"
    rm -f   "$BIN_DIR/token-jet" "$BIN_DIR/token-jet-tui"
    rm -f   ~/bin/jetson-infer ~/bin/jetson-infer.service
    echo ""
    echo "Uninstalled."
    echo "  Config preserved at: $CONFIG_DIR"
    echo "  Models preserved at: ~/models/"
    echo "  Remove manually if desired: rm -rf $CONFIG_DIR ~/models/"
    exit 0
fi

# ── Prerequisite check ────────────────────────────────────────────────────────
echo "Checking Python..."
PY_VER=$(python3 -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2>/dev/null || echo "0 0")
PY_MAJOR=$(echo "$PY_VER" | cut -d' ' -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d' ' -f2)
if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 9 ]]; }; then
    echo "ERROR: Python 3.9+ required (found ${PY_MAJOR}.${PY_MINOR})" >&2
    exit 1
fi
echo "  Python ${PY_MAJOR}.${PY_MINOR}: OK"

# ── jetson-infer ──────────────────────────────────────────────────────────────
echo "Installing jetson-infer..."
mkdir -p ~/bin
cp "${REPO_ROOT}/jetson-infer"         ~/bin/jetson-infer
cp "${REPO_ROOT}/jetson-infer.service" ~/bin/jetson-infer.service
chmod +x ~/bin/jetson-infer
echo "  ~/bin/jetson-infer: OK"

if ! grep -q '"$HOME/bin"\|$HOME/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
fi

# ── TUI venv ──────────────────────────────────────────────────────────────────
echo "Setting up TUI environment..."
if [[ "$MODE" == "upgrade" ]]; then
    "$INSTALL_BASE/venv/bin/pip" install -q --upgrade "${REPO_ROOT}/tui/"
    echo "  TUI upgraded OK"
else
    mkdir -p "$INSTALL_BASE" "$BIN_DIR"
    if [[ ! -d "${INSTALL_BASE}/venv" ]]; then
        python3 -m venv "${INSTALL_BASE}/venv"
        echo "  Created venv"
    fi
    echo "  Installing dependencies (this takes a minute on first run)..."
    "${INSTALL_BASE}/venv/bin/pip" install -q --upgrade pip
    "${INSTALL_BASE}/venv/bin/pip" install -q "${REPO_ROOT}/tui/"
    echo "  token-jet-tui: OK"
fi

# ── Launcher ──────────────────────────────────────────────────────────────────
cat > "${BIN_DIR}/token-jet" << 'LAUNCHER_EOF'
#!/usr/bin/env bash
export LD_LIBRARY_PATH="/usr/local/cuda-13.2/targets/sbsa-linux/lib:${LD_LIBRARY_PATH:-}"
exec "${HOME}/.local/share/token-jet/venv/bin/token-jet-tui" "$@"
LAUNCHER_EOF
chmod +x "${BIN_DIR}/token-jet"
cp "${BIN_DIR}/token-jet" "${BIN_DIR}/token-jet-tui"
echo "  launcher: ~/.local/bin/token-jet"

if ! grep -q '.local/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

# ── Default config (install only) ────────────────────────────────────────────
if [[ "$MODE" == "install" ]]; then
    mkdir -p "$CONFIG_DIR"
    if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
        cat > "${CONFIG_DIR}/config.toml" << TOML_EOF
# Token-Jet configuration — edit paths to match your Jetson setup.
model_dir          = "/home/${JETSON_USER}/models"
llama_cpp_bin      = "/home/${JETSON_USER}/llama.cpp/build/bin"
server_host        = "127.0.0.1"
server_port        = 1234
ld_library_path    = "/usr/local/cuda-13.2/targets/sbsa-linux/lib"
jetson_infer_bin   = "/home/${JETSON_USER}/bin/jetson-infer"
hf_download_timeout = 300
TOML_EOF
        echo "  config: ${CONFIG_DIR}/config.toml"
        echo "  IMPORTANT: edit config.toml to match your llama.cpp and model paths."
    else
        echo "  config preserved (already exists)"
    fi
fi

# ── Systemd service (install only) ───────────────────────────────────────────
if [[ "$MODE" == "install" ]]; then
    echo "Installing systemd service..."
    mkdir -p ~/.config/systemd/user/
    cp ~/bin/jetson-infer.service ~/.config/systemd/user/jetson-infer.service
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable jetson-infer 2>/dev/null || true
    sudo loginctl enable-linger "$JETSON_USER" 2>/dev/null || true
    echo "  systemd service: enabled"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "=== Installation complete! ==="
echo ""
echo "  source ~/.bashrc      (or open a new terminal)"
echo "  token-jet             (launch the dashboard)"
echo ""
echo "First run:"
echo "  1. Press Ctrl+D → download a model (MiniCPM5-1B recommended)"
echo "  2. Press Ctrl+S → load it"
echo "  3. Type in the chat box and press Enter"
echo ""
if [[ "$MODE" == "install" ]]; then
    echo "Before first launch, verify your paths in:"
    echo "  ${CONFIG_DIR}/config.toml"
    echo ""
fi
