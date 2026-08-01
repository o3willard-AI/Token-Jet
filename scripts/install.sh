#!/usr/bin/env bash
# Token-Jet installer — deploy everything to a Jetson Orin Nano.
#
# Usage (from a cloned repo):
#   ./scripts/install.sh <jetson-ip> [options]
#   ./scripts/install.sh <jetson-ip> --upgrade
#   ./scripts/install.sh <jetson-ip> --self-update
#   ./scripts/install.sh <jetson-ip> --uninstall
#
# Options:
#   --upgrade         Replace source files and reinstall; preserves user config
#   --self-update     Pull latest from GitHub then run --upgrade automatically
#   --uninstall       Remove TUI, jetson-infer, and systemd service
#   --user USER       Jetson SSH username (default: ubuntu)
#   --pass PASS       SSH password; omit to be prompted, or use --no-pass
#   --no-pass         Use key-based SSH (no password required)
#   --no-prism-build  Skip building the PrismML llama.cpp fork (Bonsai GPU support)
#   -h, --help        Show this help
#
# The PrismML fork (https://github.com/PrismML-Eng/llama.cpp, branch pr/q2_0-cuda)
# is built automatically on fresh install to enable GPU inference for Bonsai ternary
# models (TYPE_42 quant). On --upgrade it is skipped if already built. Pass
# --no-prism-build to skip it entirely (e.g. for CI or disk-constrained installs).
# The build takes ~30 minutes. jetson-infer auto-routes any model with "bonsai"
# in the filename to ~/llama.cpp-prism/build/bin/llama-server.
#
# Environment variable overrides (useful for CI / scripting):
#   INSTALL_JETSON_IP    Jetson IP address
#   INSTALL_JETSON_USER  Jetson username
#   INSTALL_JETSON_PASS  SSH password

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
JETSON_IP="${INSTALL_JETSON_IP:-}"
JETSON_USER="${INSTALL_JETSON_USER:-ubuntu}"
JETSON_PASS="${INSTALL_JETSON_PASS:-}"
MODE="install"
USE_SSHPASS=true
BUILD_PRISM=true
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --upgrade)          MODE="upgrade";     shift ;;
        --self-update)      MODE="self-update"; shift ;;
        --uninstall)        MODE="uninstall";   shift ;;
        --user)             JETSON_USER="$2";   shift 2 ;;
        --pass)             JETSON_PASS="$2";   shift 2 ;;
        --no-pass)          USE_SSHPASS=false;  shift ;;
        --no-prism-build)   BUILD_PRISM=false;  shift ;;
        -h|--help)
            sed -n '2,22p' "$0" | sed 's/^# //'
            exit 0 ;;
        -*)
            echo "Unknown option: $1" >&2; exit 1 ;;
        *)
            JETSON_IP="$1"; shift ;;
    esac
done

# ── Validate required arguments ───────────────────────────────────────────────
if [[ -z "$JETSON_IP" ]]; then
    echo "ERROR: Jetson IP address is required." >&2
    echo "Usage: $0 <jetson-ip> [--upgrade|--self-update|--uninstall] [--user USER] [--pass PASS|--no-pass]" >&2
    exit 1
fi

# Prompt for password if needed and not provided
if $USE_SSHPASS && [[ -z "$JETSON_PASS" ]]; then
    read -s -p "SSH password for ${JETSON_USER}@${JETSON_IP}: " JETSON_PASS
    echo
fi

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
    local src="$1" dst="$2"
    if $USE_SSHPASS && command -v sshpass &>/dev/null; then
        sshpass -p "$JETSON_PASS" scp -o StrictHostKeyChecking=no -r "$src" "$JETSON:$dst"
    else
        scp -o StrictHostKeyChecking=no -r "$src" "$JETSON:$dst"
    fi
}

_pipe_to() {
    local remote_path="$1"
    if $USE_SSHPASS && command -v sshpass &>/dev/null; then
        sshpass -p "$JETSON_PASS" ssh -o StrictHostKeyChecking=no "$JETSON" "cat > $remote_path"
    else
        ssh -o StrictHostKeyChecking=no "$JETSON" "cat > $remote_path"
    fi
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "=== Token-Jet Installer ==="
echo "Mode:   $MODE"
echo "Target: ${JETSON}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# SELF-UPDATE: pull latest from GitHub, then re-exec as upgrade
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "self-update" ]]; then
    if [[ ! -d "${REPO_ROOT}/.git" ]]; then
        echo "ERROR: --self-update requires a git clone (no .git directory found)." >&2
        exit 1
    fi
    echo "Pulling latest from GitHub..."
    git -C "$REPO_ROOT" pull --ff-only
    echo ""
    echo "Re-running installer as --upgrade..."
    echo ""
    # Re-exec with same arguments but mode replaced with --upgrade
    ARGS=("$JETSON_IP" "--upgrade" "--user" "$JETSON_USER")
    if $USE_SSHPASS; then
        ARGS+=("--pass" "$JETSON_PASS")
    else
        ARGS+=("--no-pass")
    fi
    exec "$0" "${ARGS[@]}"
fi

# ── Connectivity check ────────────────────────────────────────────────────────
echo "Checking SSH access..."
if ! _ssh 'echo OK' &>/dev/null; then
    echo "ERROR: Cannot reach ${JETSON} via SSH."
    echo "  Check the IP, username, and that the Jetson is online."
    if ! $USE_SSHPASS; then
        echo "  (Key-based auth — make sure your SSH key is installed on the Jetson)"
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
        systemctl --user stop    jetson-infer 2>/dev/null || true
        systemctl --user disable jetson-infer 2>/dev/null || true
        rm -f ~/.config/systemd/user/jetson-infer.service
        systemctl --user stop    pi-web 2>/dev/null || true
        systemctl --user disable pi-web 2>/dev/null || true
        rm -f ~/.config/systemd/user/pi-web.service
        systemctl --user daemon-reload 2>/dev/null || true

        echo '${JETSON_PASS}' | sudo -S rm -f /etc/sudoers.d/token-jet-wifi
        rm -rf '${INSTALL_BASE}'
        rm -f '${BIN_DIR}/token-jet-tui'
        rm -f ~/bin/jetson-infer ~/bin/jetson-infer.service
        rm -f ~/.pi/agent/extensions/wifi-manager.ts

        echo 'Files removed.'
        echo ''
        echo 'Note: config preserved at ~/.config/token-jet/'
        echo 'Remove manually if desired: rm -rf ~/.config/token-jet/'
    "
    echo ""
    echo "Uninstall complete."

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
# System tools — fd and ripgrep needed by the pi coding agent.
# Without these, pi downloads its own ARM binaries on every fresh install.
# fd is packaged as 'fd-find' on Ubuntu with the binary named 'fdfind';
# we add a 'fd' symlink so pi finds it under the expected name.
# ─────────────────────────────────────────────────────────────────────────────
echo "Installing system tools (fd, ripgrep)..."
_ssh "
    MISSING=()
    command -v fdfind &>/dev/null || dpkg -l fd-find &>/dev/null || MISSING+=(fd-find)
    command -v rg     &>/dev/null || MISSING+=(ripgrep)
    if [[ \${#MISSING[@]} -gt 0 ]]; then
        echo '${JETSON_PASS}' | sudo -S apt-get install -y -q \"\${MISSING[@]}\"
    fi
    # Ensure 'fd' resolves — Ubuntu installs it as 'fdfind'
    if ! command -v fd &>/dev/null && command -v fdfind &>/dev/null; then
        echo '${JETSON_PASS}' | sudo -S ln -sf \$(which fdfind) /usr/local/bin/fd
    fi
"
echo "  fd, ripgrep: OK"
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

if [[ "$MODE" == "upgrade" ]]; then
    _ssh "rm -rf '${INSTALL_BASE}/token_jet_tui'"
fi

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

_ssh "
    if ! grep -q '.local/bin' ~/.bashrc 2>/dev/null; then
        echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc
        echo 'Added ~/.local/bin to PATH in .bashrc'
    fi
"

# ─────────────────────────────────────────────────────────────────────────────
# pi skill wrappers — install ddg-search and fetch-url to /usr/local/bin so
# they are available in non-interactive shells (where ~/bin isn't in PATH).
# Paths are generated dynamically so they work for any JETSON_USER.
# ─────────────────────────────────────────────────────────────────────────────
echo "Installing pi skill wrappers..."
_ssh "echo '${JETSON_PASS}' | sudo -S bash -c '
    printf \"#!/bin/bash\\nexec node /home/${JETSON_USER}/Token-Jet/pi/ddg-search/search.js \\\"\\\$@\\\"\\n\" \
        > /usr/local/bin/ddg-search
    printf \"#!/bin/bash\\nexec node /home/${JETSON_USER}/Token-Jet/pi/ddg-search/content.js \\\"\\\$@\\\"\\n\" \
        > /usr/local/bin/fetch-url
    chmod +x /usr/local/bin/ddg-search /usr/local/bin/fetch-url
'"
echo "  /usr/local/bin/ddg-search: OK"
echo "  /usr/local/bin/fetch-url:  OK"

# ─────────────────────────────────────────────────────────────────────────────
# Node.js 22 + pi-web
# Ubuntu 24.04's default apt repos ship Node 18; pi-web requires 22+.
# We install from NodeSource if needed, then install pi-web globally into a
# user-local npm prefix (avoids sudo for npm installs).
# pi-web is exposed on all interfaces so it's reachable from this workstation.
# ─────────────────────────────────────────────────────────────────────────────
echo "Installing Node.js 22, pi coding agent, extensions, and pi-web..."

# Deploy pi settings before 'pi install' runs — pi install creates settings.json
# as a side effect, so this must arrive first or the repo version is never used.
_ssh "mkdir -p ~/.pi/agent/"
if ! _ssh "[[ -f ~/.pi/agent/settings.json ]]"; then
    cat "${REPO_ROOT}/pi/settings.json" | _pipe_to "~/.pi/agent/settings.json"
    echo "  pi settings: ~/.pi/agent/settings.json"
else
    echo "  pi settings: preserved (already exists)"
fi

_ssh "
    NODE_OK=false
    if command -v node &>/dev/null; then
        NODE_MAJOR=\$(node --version 2>/dev/null | grep -oP '(?<=v)\d+' || echo 0)
        [[ \"\$NODE_MAJOR\" -ge 22 ]] && NODE_OK=true
    fi
    if ! \$NODE_OK; then
        echo '  Installing Node.js 22 (via NodeSource)...'
        curl -fsSL https://deb.nodesource.com/setup_22.x | echo '${JETSON_PASS}' | sudo -SE bash - 2>/dev/null
        echo '${JETSON_PASS}' | sudo -S apt-get install -y -qq nodejs
    fi
    echo \"  Node.js \$(node --version): OK\"

    NPM_GLOBAL=\"\${HOME}/.npm-global\"
    if [[ \"\$(npm config get prefix 2>/dev/null)\" != \"\$NPM_GLOBAL\" ]]; then
        mkdir -p \"\$NPM_GLOBAL\"
        npm config set prefix \"\$NPM_GLOBAL\"
    fi
    if ! grep -q '.npm-global/bin' ~/.bashrc 2>/dev/null; then
        echo 'export PATH=\"\$HOME/.npm-global/bin:\$PATH\"' >> ~/.bashrc
    fi
    export PATH=\"\${NPM_GLOBAL}/bin:\${PATH}\"

    npm install -g --ignore-scripts @earendil-works/pi-coding-agent 2>/dev/null \
        && echo '  pi coding agent: OK' \
        || echo '  WARNING: pi install failed'

    yes | pi install npm:pi-mcp-adapter 2>/dev/null \
        && echo '  pi-mcp-adapter: OK' \
        || echo '  WARNING: pi-mcp-adapter install failed'

    npm install -g @agegr/pi-web 2>/dev/null \
        && echo '  pi-web: OK' \
        || echo '  WARNING: pi-web install failed'
"

# Deploy pi provider extension and configure auth — both missing from this path
# before this fix; install-local.sh has had these since initial pi integration.
echo "Deploying pi provider extension..."
_ssh "mkdir -p ~/.pi/agent/extensions/"
cat "${REPO_ROOT}/pi/jetson-provider.ts" | _pipe_to "~/.pi/agent/extensions/jetson-provider.ts"
echo "  jetson-provider.ts: OK"
_ssh "mkdir -p ~/Token-Jet/pi/wifi-manager/"
cat "${REPO_ROOT}/pi/wifi-manager/wifi.py" | _pipe_to "~/Token-Jet/pi/wifi-manager/wifi.py"
_ssh "chmod +x ~/Token-Jet/pi/wifi-manager/wifi.py"
cat "${REPO_ROOT}/pi/wifi-manager.ts" | _pipe_to "~/.pi/agent/extensions/wifi-manager.ts"
echo "  wifi-manager.ts: OK"

echo "Installing Wi-Fi sudoers rule..."
_ssh "
    RULE='${JETSON_USER} ALL=(ALL) NOPASSWD: /usr/bin/nmcli'
    FILE='/etc/sudoers.d/token-jet-wifi'
    if echo '${JETSON_PASS}' | sudo -S grep -qF \"\$RULE\" \"\$FILE\" 2>/dev/null; then
        echo '  sudoers: already configured'
    else
        TMPF=\$(mktemp)
        printf '%s\n' \"\$RULE\" > \"\$TMPF\"
        echo '${JETSON_PASS}' | sudo -S cp \"\$TMPF\" \"\$FILE\"
        echo '${JETSON_PASS}' | sudo -S chmod 440 \"\$FILE\"
        rm -f \"\$TMPF\"
        echo '  sudoers: /etc/sudoers.d/token-jet-wifi installed'
    fi
"


_ssh "
    python3 - <<'PYEOF'
import json, os
path = os.path.expanduser('~/.pi/agent/auth.json')
try:
    d = json.loads(open(path).read()) if os.path.exists(path) else {}
except Exception:
    d = {}
if d.get('jetson-local', {}).get('key') != 'none':
    d['jetson-local'] = {'type': 'api_key', 'key': 'none'}
    open(path, 'w').write(json.dumps(d, indent=2) + '\n')
    print('  pi auth: jetson-local credential written')
else:
    print('  pi auth: already configured')
PYEOF
"

echo "  pi coding agent: configured"

echo "Installing pi-web service..."
cat "${REPO_ROOT}/pi-web.service" | _pipe_to "~/.config/systemd/user/pi-web.service"
_ssh "
    mkdir -p ~/.config/systemd/user/
    systemctl --user daemon-reload 2>/dev/null || true
    if [[ '$MODE' == 'upgrade' ]]; then
        systemctl --user restart pi-web 2>/dev/null || true
        echo '  pi-web service: restarted'
    else
        systemctl --user enable pi-web 2>/dev/null || true
        systemctl --user start  pi-web 2>/dev/null || true
        echo '  pi-web service: enabled + started'
    fi
"

# ─────────────────────────────────────────────────────────────────────────────
# dufs file server
# ─────────────────────────────────────────────────────────────────────────────
echo "Installing dufs file server..."
DUFS_VERSION="0.46.0"
DUFS_URL="https://github.com/sigoden/dufs/releases/download/v${DUFS_VERSION}/dufs-v${DUFS_VERSION}-aarch64-unknown-linux-musl.tar.gz"
_ssh "
    _current_dufs_ver=\$(~/bin/dufs --version 2>/dev/null | grep -oP '[\d.]+' | head -1 || echo 'none')
    if [[ ! -x ~/bin/dufs ]] || [[ \"\$_current_dufs_ver\" != '${DUFS_VERSION}' ]]; then
        echo '  Downloading dufs v${DUFS_VERSION}...'
        curl -fsSL '${DUFS_URL}' -o /tmp/dufs.tar.gz
        tar -xzf /tmp/dufs.tar.gz -C /tmp/ dufs
        mv /tmp/dufs ~/bin/dufs
        chmod +x ~/bin/dufs
        rm -f /tmp/dufs.tar.gz
        echo '  dufs v${DUFS_VERSION}: installed'
    else
        echo '  dufs v${DUFS_VERSION}: already current'
    fi
    mkdir -p ~/shared/uploads ~/shared/exports
    echo '  shared directory: ~/shared/ (uploads/ and exports/)'
"
cat "${REPO_ROOT}/dufs.service" | _pipe_to "~/.config/systemd/user/dufs.service"
_ssh "
    mkdir -p ~/.config/systemd/user/
    systemctl --user daemon-reload 2>/dev/null || true
    if [[ '${MODE}' == 'upgrade' ]]; then
        systemctl --user restart dufs 2>/dev/null || true
        echo '  dufs service: restarted'
    else
        systemctl --user enable dufs 2>/dev/null || true
        systemctl --user start  dufs 2>/dev/null || true
        echo '  dufs service: enabled + started at port 30140'
    fi
"

# ─────────────────────────────────────────────────────────────────────────────
# USB device mode (RNDIS-only)
# NVIDIA's default enables ACM + UMS + ECM alongside RNDIS. On Windows, ACM
# (USB serial) and UMS (16 MB FAT image) cause the host to loop-enumerate the
# composite gadget indefinitely. Fix: disable everything except RNDIS.
# bcdDevice 0x0003 forces Windows to flush its stale composite-device driver
# cache, picking up the new single-function RNDIS configuration cleanly.
# ─────────────────────────────────────────────────────────────────────────────
echo "Configuring USB device mode (RNDIS-only)..."
_ssh "
    USB_CFG='/opt/nvidia/l4t-usb-device-mode/nv-l4t-usb-device-mode-config.sh'
    USB_START='/opt/nvidia/l4t-usb-device-mode/nv-l4t-usb-device-mode-start.sh'
    USB_CHANGED=false
    if [[ -f \"\$USB_CFG\" ]]; then
        if grep -qE '^enable_(acm|ums|ecm)=1' \"\$USB_CFG\"; then
            echo '${JETSON_PASS}' | sudo -S sed -i \
                -e 's/^enable_acm=1/enable_acm=0/' \
                -e 's/^enable_ums=1/enable_ums=0/' \
                -e 's/^enable_ecm=1/enable_ecm=0/' \
                \"\$USB_CFG\"
            USB_CHANGED=true
            echo '  usb-mode config: ACM/UMS/ECM disabled (RNDIS-only)'
        else
            echo '  usb-mode config: already configured'
        fi
    else
        echo '  usb-mode config: not found, skipping (service not installed)'
    fi
    if [[ -f \"\$USB_START\" ]]; then
        if grep -q '0x0002' \"\$USB_START\"; then
            echo '${JETSON_PASS}' | sudo -S sed -i 's/0x0002/0x0003/' \"\$USB_START\"
            USB_CHANGED=true
            echo '  usb-mode start: bcdDevice bumped to 0x0003'
        else
            echo '  usb-mode start: bcdDevice already at 0x0003'
        fi
    fi
    if \$USB_CHANGED; then
        echo '${JETSON_PASS}' | sudo -S systemctl restart nv-l4t-usb-device-mode 2>/dev/null \
            && echo '  nv-l4t-usb-device-mode: restarted' \
            || echo '  nv-l4t-usb-device-mode: restart skipped (service not active)'
    fi
"

# ─────────────────────────────────────────────────────────────────────────────
# PrismML llama.cpp fork — required for GPU inference on Bonsai ternary models.
#
# Bonsai models use TYPE_41/TYPE_42 custom ternary quantization that has no
# CUDA kernels in mainline llama.cpp. The PrismML fork (branch pr/q2_0-cuda)
# adds those kernels, enabling 8+ t/s GPU inference vs ~3 t/s CPU fallback.
#
# jetson-infer auto-selects this binary for any model with "bonsai" in the
# filename. If binary already exists (upgrade), the build is skipped.
# Pass --no-prism-build to skip entirely.
# ─────────────────────────────────────────────────────────────────────────────
if $BUILD_PRISM; then
    echo "Checking PrismML llama.cpp fork (Bonsai GPU support)..."
    _ssh "
        if [ -f ~/llama.cpp-prism/build/bin/llama-server ]; then
            echo '  prism binary exists — skipping build'
        else
            echo '  Cloning PrismML fork (pr/q2_0-cuda branch)...'
            git clone --branch pr/q2_0-cuda --depth 1 \
                https://github.com/PrismML-Eng/llama.cpp \
                ~/llama.cpp-prism 2>&1
            echo '  Configuring with CUDA (SM 8.7 = Jetson Orin Ampere)...'
            CUDACXX=/usr/local/cuda-13.2/bin/nvcc cmake \
                -B ~/llama.cpp-prism/build \
                -S ~/llama.cpp-prism \
                -DGGML_CUDA=ON \
                -DCMAKE_CUDA_ARCHITECTURES=87 \
                -DCMAKE_BUILD_TYPE=Release \
                -DLLAMA_CURL=OFF \
                2>&1
            echo '  Building llama-server (~30 min on Jetson Orin Nano)...'
            cmake --build ~/llama.cpp-prism/build -j\$(nproc) --target llama-server 2>&1
            echo '  prism binary: built OK'
        fi
    "
else
    echo "PrismML fork build: skipped (--no-prism-build)"
    echo "  Bonsai models will fall back to CPU until built manually."
    echo "  To build later: cd ~/llama.cpp-prism && cmake --build build -j\$(nproc) --target llama-server"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Default config (install only)
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "install" ]]; then
    echo "Writing default config..."
    _ssh "
        mkdir -p '${CONFIG_DIR}'
        if [[ ! -f '${CONFIG_DIR}/config.toml' ]]; then
            cat > '${CONFIG_DIR}/config.toml' << 'TOML_EOF'
# Token-Jet configuration
model_dir          = \"/home/${JETSON_USER}/models\"
llama_cpp_bin      = \"/home/${JETSON_USER}/llama.cpp/build/bin\"
server_port        = 1234
ld_library_path    = \"/usr/local/cuda-13.2/targets/sbsa-linux/lib\"
jetson_infer_bin   = \"/home/${JETSON_USER}/bin/jetson-infer\"
hf_download_timeout = 300

# Model to load on startup. If unset, uses the project-recommended model
# (Qwen3.5-4B-Coder) if downloaded, then the first .gguf found in model_dir.
# startup_model = \"/home/${JETSON_USER}/models/qwen3.5-4B-super-coder.Q4_0.gguf\"

# Cap thinking tokens on reasoning models (0 = no cap).
# reasoning_budget = 1024
TOML_EOF
            echo 'Config written to ${CONFIG_DIR}/config.toml'
            echo 'Edit it to match your llama.cpp and model paths before first use.'
        else
            echo 'Config preserved (already exists)'
        fi
    "
fi

# ─────────────────────────────────────────────────────────────────────────────
# Systemd service (install only)
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
    _ssh "sudo loginctl enable-linger '${JETSON_USER}' 2>/dev/null || true"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Workstation launcher
# ─────────────────────────────────────────────────────────────────────────────
WS_BIN_DIR="$HOME/bin"
WS_LAUNCHER="${WS_BIN_DIR}/token-jet-tui"
mkdir -p "$WS_BIN_DIR"

if $USE_SSHPASS && command -v sshpass &>/dev/null && [[ -n "$JETSON_PASS" ]]; then
    # Embed sshpass so the launcher doesn't prompt for a password
    cat > "$WS_LAUNCHER" << WSLAUNCHER_EOF
#!/usr/bin/env bash
# Launch Token-Jet TUI on the Jetson via SSH (password auth).
exec sshpass -p '${JETSON_PASS}' ssh -o StrictHostKeyChecking=no -t ${JETSON} "PATH=\$HOME/.local/bin:\$PATH token-jet-tui \$*"
WSLAUNCHER_EOF
    chmod 700 "$WS_LAUNCHER"   # restrict read — contains password
else
    # Key-based auth — no password needed
    cat > "$WS_LAUNCHER" << WSLAUNCHER_EOF
#!/usr/bin/env bash
# Launch Token-Jet TUI on the Jetson via SSH (key-based auth).
# If you see a password prompt, run: ssh-copy-id ${JETSON}
exec ssh -o StrictHostKeyChecking=no -t ${JETSON} "PATH=\$HOME/.local/bin:\$PATH token-jet-tui \$*"
WSLAUNCHER_EOF
    chmod +x "$WS_LAUNCHER"
fi
echo "Workstation launcher: ${WS_LAUNCHER}"

if ! echo "$PATH" | tr ':' '\n' | grep -q "^${WS_BIN_DIR}$"; then
    echo ""
    echo "  NOTE: Add ~/bin to your PATH to run 'token-jet-tui' directly:"
    echo "    echo 'export PATH=\"\$HOME/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Eval scripts (optional — skipped if not present in repo)
# ─────────────────────────────────────────────────────────────────────────────
EVAL_DIR="${REPO_ROOT}/eval"
if [[ -d "$EVAL_DIR" ]] && compgen -G "${EVAL_DIR}/*.py" > /dev/null 2>&1; then
    echo "Deploying eval scripts..."
    _ssh "mkdir -p ~/token-jet/eval"
    for f in "${EVAL_DIR}"/*.py; do
        name="$(basename "$f")"
        cat "$f" | _pipe_to "~/token-jet/eval/${name}"
        echo "  ${name}: OK"
    done
else
    echo "Eval scripts: not found in repo, skipping."
fi

# ─────────────────────────────────────────────────────────────────────────────
# Verify
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Verifying installation..."
_ssh "
    echo -n 'jetson-infer: '
    ~/bin/jetson-infer --help 2>&1 | head -1 || echo 'OK'
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
echo "  http://${JETSON_IP}:30141  # pi-web browser UI"
echo "  http://${JETSON_IP}:30140  # dufs file share (browser + WebDAV)"
echo ""
echo "File sharing from Mac/Windows:"
echo "  Browser:  http://${JETSON_IP}:30140"
echo "  Mac:      Finder → Go → Connect to Server → http://${JETSON_IP}:30140"
echo "  Windows:  Map Network Drive → \\\\${JETSON_IP}@30140\\DavWWWRoot"
echo ""
echo "To upgrade later:"
echo "  ./scripts/install.sh ${JETSON_IP} --upgrade --user ${JETSON_USER}"
echo ""
echo "To pull latest from GitHub and upgrade in one step:"
echo "  ./scripts/install.sh ${JETSON_IP} --self-update --user ${JETSON_USER}"
echo ""
echo "To uninstall:"
echo "  ./scripts/install.sh ${JETSON_IP} --uninstall --user ${JETSON_USER}"
