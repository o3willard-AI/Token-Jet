#!/usr/bin/env bash
# Token-Jet installer — deploy everything to a Jetson Orin Nano.
#
# Usage:
#   ./scripts/install.sh [options] [jetson-ip]
#   ./scripts/install.sh --upgrade [jetson-ip]
#   ./scripts/install.sh --uninstall [jetson-ip]
#
# Options:
#   --upgrade     Replace source files and reinstall; preserves user config
#   --uninstall   Remove TUI, jetson-infer, and systemd service
#   --user USER   Jetson username (default: sblanken)
#   --pass PASS   SSH password for sshpass (default: 101abn)
#   --no-pass     Use key-based SSH instead of password
#   -h, --help    Show this help

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
JETSON_IP="${INSTALL_JETSON_IP:-192.168.101.10}"
JETSON_USER="${INSTALL_JETSON_USER:-sblanken}"
JETSON_PASS="${INSTALL_JETSON_PASS:-101abn}"
MODE="install"
USE_SSHPASS=true
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --upgrade)   MODE="upgrade";   shift ;;
        --uninstall) MODE="uninstall"; shift ;;
        --user)      JETSON_USER="$2"; shift 2 ;;
        --pass)      JETSON_PASS="$2"; shift 2 ;;
        --no-pass)   USE_SSHPASS=false; shift ;;
        -h|--help)
            sed -n '2,20p' "$0" | sed 's/^# //'
            exit 0 ;;
        -*)
            echo "Unknown option: $1" >&2; exit 1 ;;
        *)
            JETSON_IP="$1"; shift ;;
    esac
done

JETSON="${JETSON_USER}@${JETSON_IP}"
INSTALL_BASE="/home/${JETSON_USER}/.local/share/token-jet"
BIN_DIR="/home/${JETSON_USER}/.local/bin"
CONFIG_DIR="/home/${JETSON_USER}/.config/token-jet"

# ── SSH helpers ───────────────────────────────────────────────────────────────
_ssh() {
    if $USE_SSHPASS && command -v sshpass &>/dev/null; then
        sshpass -p "$JETSON_PASS" ssh -o StrictHostKeyChecking=no "$JETSON" "$@"
    else
        ssh -o StrictHostKeyChecking=no "$JETSON" "$@"
    fi
}

_scp_to() {
    # _scp_to <local> <remote-path>
    local src="$1" dst="$2"
    if $USE_SSHPASS && command -v sshpass &>/dev/null; then
        sshpass -p "$JETSON_PASS" scp -o StrictHostKeyChecking=no -r "$src" "$JETSON:$dst"
    else
        scp -o StrictHostKeyChecking=no -r "$src" "$JETSON:$dst"
    fi
}

_pipe_to() {
    # Pipe stdin to a remote file (path must not contain spaces)
    local remote_path="$1"
    if $USE_SSHPASS && command -v sshpass &>/dev/null; then
        sshpass -p "$JETSON_PASS" ssh -o StrictHostKeyChecking=no "$JETSON" "cat > $remote_path"
    else
        ssh -o StrictHostKeyChecking=no "$JETSON" "cat > $remote_path"
    fi
}

# ── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Token-Jet Installer ==="
echo "Mode:   $MODE"
echo "Target: ${JETSON}"
echo ""

# ── Connectivity check ────────────────────────────────────────────────────────
echo "Checking SSH access..."
if ! _ssh 'echo OK' &>/dev/null; then
    echo "ERROR: Cannot reach ${JETSON} via SSH."
    echo "  Check the IP, username, and that the Jetson is online."
    if ! $USE_SSHPASS; then
        echo "  (Key-based auth — make sure your SSH key is installed)"
    fi
    exit 1
fi
echo "SSH: OK"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# UNINSTALL
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "uninstall" ]]; then
    echo "Uninstalling Token-Jet from ${JETSON}..."
    _ssh "
        set -e
        # Stop service if running
        systemctl --user stop jetson-infer 2>/dev/null || true
        systemctl --user disable jetson-infer 2>/dev/null || true
        rm -f ~/.config/systemd/user/jetson-infer.service
        systemctl --user daemon-reload 2>/dev/null || true

        # Remove TUI
        rm -rf '${INSTALL_BASE}'
        rm -f '${BIN_DIR}/token-jet-tui'

        # Remove jetson-infer
        rm -f ~/bin/jetson-infer ~/bin/jetson-infer.service

        echo 'Files removed.'
        echo ''
        echo 'Note: config preserved at ~/.config/token-jet/'
        echo 'Remove manually if desired: rm -rf ~/.config/token-jet/'
    "
    echo ""
    echo "Uninstall complete."

    # Remove workstation launcher
    WS_LAUNCHER="$HOME/bin/token-jet-tui"
    if [[ -f "$WS_LAUNCHER" ]]; then
        rm -f "$WS_LAUNCHER"
        echo "Removed workstation launcher: $WS_LAUNCHER"
    fi
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# PRE-FLIGHT: Python version check
# ─────────────────────────────────────────────────────────────────────────────
echo "Checking Python on Jetson..."
PY_VER=$(_ssh 'python3 -c "import sys; print(sys.version_info.major, sys.version_info.minor)"')
PY_MAJOR=$(echo "$PY_VER" | cut -d' ' -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d' ' -f2)
if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 9 ]]; }; then
    echo "ERROR: Python 3.9+ required on Jetson (found ${PY_MAJOR}.${PY_MINOR})"
    exit 1
fi
echo "Python: ${PY_MAJOR}.${PY_MINOR} OK"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# JETSON-INFER deployment
# ─────────────────────────────────────────────────────────────────────────────
echo "Deploying jetson-infer..."
_ssh "mkdir -p ~/bin"
cat "${REPO_ROOT}/jetson-infer" | _pipe_to "~/bin/jetson-infer"
_ssh "chmod +x ~/bin/jetson-infer"
echo "  jetson-infer: OK"

echo "Deploying jetson-infer.service..."
cat "${REPO_ROOT}/jetson-infer.service" | _pipe_to "~/bin/jetson-infer.service"
echo "  jetson-infer.service: OK"

# ─────────────────────────────────────────────────────────────────────────────
# TUI deployment
# ─────────────────────────────────────────────────────────────────────────────
echo "Setting up TUI environment..."

# On upgrade, remove old source first
if [[ "$MODE" == "upgrade" ]]; then
    _ssh "rm -rf '${INSTALL_BASE}/token_jet_tui'"
fi

# Create directory and venv
_ssh "mkdir -p '${INSTALL_BASE}' '${BIN_DIR}'"
_ssh "
    if [[ ! -d '${INSTALL_BASE}/venv' ]]; then
        python3 -m venv '${INSTALL_BASE}/venv'
        echo 'Created venv'
    else
        echo 'Venv exists'
    fi
"

echo "Installing Python dependencies..."
_ssh "'${INSTALL_BASE}/venv/bin/pip' install -q --upgrade pip"
_ssh "'${INSTALL_BASE}/venv/bin/pip' install -q 'textual>=0.50.0'"
echo "  textual: OK"

echo "Transferring TUI source..."
# Pack and send the token_jet_tui package directory
tar -czf - -C "${REPO_ROOT}/tui" token_jet_tui | \
    if $USE_SSHPASS && command -v sshpass &>/dev/null; then
        sshpass -p "$JETSON_PASS" ssh -o StrictHostKeyChecking=no "$JETSON" "tar -xzf - -C '${INSTALL_BASE}/'"
    else
        ssh -o StrictHostKeyChecking=no "$JETSON" "tar -xzf - -C '${INSTALL_BASE}/'"
    fi
echo "  source: OK"

# ─────────────────────────────────────────────────────────────────────────────
# Launcher script on Jetson
# ─────────────────────────────────────────────────────────────────────────────
echo "Creating Jetson launcher..."
_ssh "cat > '${BIN_DIR}/token-jet-tui' << 'LAUNCHER_EOF'
#!/usr/bin/env bash
export PYTHONPATH=\"\${HOME}/.local/share/token-jet\"
export LD_LIBRARY_PATH=\"/usr/local/cuda-13.2/targets/sbsa-linux/lib:\${LD_LIBRARY_PATH:-}\"
exec \"\${HOME}/.local/share/token-jet/venv/bin/python3\" -m token_jet_tui \"\$@\"
LAUNCHER_EOF
chmod +x '${BIN_DIR}/token-jet-tui'"
echo "  ${BIN_DIR}/token-jet-tui: OK"

# Ensure ~/.local/bin is in PATH
_ssh "
    if ! grep -q '.local/bin' ~/.bashrc 2>/dev/null; then
        echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc
        echo 'Added ~/.local/bin to PATH in .bashrc'
    fi
"

# ─────────────────────────────────────────────────────────────────────────────
# Default config
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "install" ]]; then
    echo "Writing default config..."
    _ssh "
        mkdir -p '${CONFIG_DIR}'
        if [[ ! -f '${CONFIG_DIR}/config.toml' ]]; then
            cat > '${CONFIG_DIR}/config.toml' << 'TOML_EOF'
# Token-Jet configuration
model_dir = \"/home/${JETSON_USER}/models\"
llama_cpp_bin = \"/home/${JETSON_USER}/llama.cpp/build/bin\"
server_host = \"127.0.0.1\"
server_port = 1234
ld_library_path = \"/usr/local/cuda-13.2/targets/sbsa-linux/lib\"
jetson_infer_bin = \"/home/${JETSON_USER}/bin/jetson-infer\"
hf_download_timeout = 300
TOML_EOF
            echo 'Config written'
        else
            echo 'Config preserved (already exists)'
        fi
    "
fi

# ─────────────────────────────────────────────────────────────────────────────
# Systemd service (install only, not upgrade)
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "install" ]]; then
    echo "Installing systemd service..."
    _ssh "
        mkdir -p ~/.config/systemd/user/
        cp ~/bin/jetson-infer.service ~/.config/systemd/user/jetson-infer.service
        systemctl --user daemon-reload
        systemctl --user enable jetson-infer 2>/dev/null || true
        echo 'systemd service: enabled'
    "
    # Enable linger so service starts at boot
    _ssh "sudo loginctl enable-linger '${JETSON_USER}' 2>/dev/null || true"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Workstation launcher
# ─────────────────────────────────────────────────────────────────────────────
WS_BIN_DIR="$HOME/bin"
WS_LAUNCHER="${WS_BIN_DIR}/token-jet-tui"
mkdir -p "$WS_BIN_DIR"
cat > "$WS_LAUNCHER" << WSLAUNCHER_EOF
#!/usr/bin/env bash
# Launch Token-Jet TUI on the Jetson via SSH.
exec ssh -t ${JETSON} "PATH=\$HOME/.local/bin:\$PATH token-jet-tui \$*"
WSLAUNCHER_EOF
chmod +x "$WS_LAUNCHER"
echo "Workstation launcher: ${WS_LAUNCHER}"

# Remind about PATH
if ! echo "$PATH" | tr ':' '\n' | grep -q "^${WS_BIN_DIR}$"; then
    echo ""
    echo "  NOTE: Add ~/bin to your PATH to run 'token-jet-tui' directly:"
    echo "    echo 'export PATH=\"\$HOME/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Eval scripts
# ─────────────────────────────────────────────────────────────────────────────
echo "Deploying eval scripts..."
_ssh "mkdir -p ~/token-jet/eval"
cat "${REPO_ROOT}/eval/coding-eval.py" | _pipe_to "~/token-jet/eval/coding-eval.py"
cat "${REPO_ROOT}/eval/it-eval.py"     | _pipe_to "~/token-jet/eval/it-eval.py"
echo "  eval scripts: OK"

# ─────────────────────────────────────────────────────────────────────────────
# Verify
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Verifying installation..."
_ssh "
    echo -n 'jetson-infer: '
    ~/bin/jetson-infer --help 2>&1 | head -1 || echo 'OK (help not shown)'
    echo -n 'token-jet-tui: '
    PYTHONPATH=~/.local/share/token-jet \
        ~/.local/share/token-jet/venv/bin/python3 -c \
        'import token_jet_tui; print(\"OK\")' 2>&1
"

# ─────────────────────────────────────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────────────────────────────────────
echo ""
if [[ "$MODE" == "upgrade" ]]; then
    echo "=== Upgrade Complete ==="
else
    echo "=== Install Complete ==="
fi
echo ""
echo "On the Jetson:"
echo "  jetson-infer start         # Start inference server"
echo "  jetson-infer status        # Check server status"
echo "  token-jet-tui              # Launch TUI"
echo ""
echo "From this workstation:"
echo "  token-jet-tui              # SSH to Jetson and launch TUI"
echo ""
echo "To uninstall later:"
echo "  ./scripts/install.sh --uninstall ${JETSON_IP}"
