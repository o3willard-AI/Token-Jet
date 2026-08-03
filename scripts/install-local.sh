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
#   --upgrade         Pull latest from GitHub, update TUI and jetson-infer; preserve config and models
#   --uninstall       Remove TUI, launcher, and systemd service (models and config are kept)
#   --no-prism-build  Skip building the PrismML llama.cpp fork (Bonsai GPU support)
#   -h, --help        Show this help

set -euo pipefail

REPO_URL="https://github.com/o3willard-AI/Token-Jet.git"
CLONE_DIR="${HOME}/Token-Jet"
MODE="install"
BUILD_PRISM=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --upgrade)        MODE="upgrade";    shift ;;
        --uninstall)      MODE="uninstall";  shift ;;
        --no-prism-build) BUILD_PRISM=false; shift ;;
        -h|--help)        sed -n '2,18p' "$0" | sed 's/^# //'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ── Detect repo root ──────────────────────────────────────────────────────────
# When piped from curl, $0 is "-" — we must clone.
if [[ "$0" == "-" || "$0" == "/dev/stdin" ]]; then
    PIPED=true
else
    PIPED=false
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    if [[ -f "${SCRIPT_DIR}/../jetson-infer" ]]; then
        REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
    else
        PIPED=true
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
    # Re-exec the updated script. git pull replaces the file on a new inode;
    # bash holds the old inode open and would silently skip any newly added
    # sections. The sentinel variable prevents an infinite re-exec loop.
    if [[ "${_TOKEN_JET_REEXECED:-}" != "1" ]] && [[ "$PIPED" == "false" ]]; then
        export _TOKEN_JET_REEXECED=1
        _reexec_args=(--upgrade)
        $BUILD_PRISM || _reexec_args+=(--no-prism-build)
        exec "$REPO_ROOT/scripts/install-local.sh" "${_reexec_args[@]}"
    fi
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
    systemctl --user stop    pi-web 2>/dev/null || true
    systemctl --user disable pi-web 2>/dev/null || true
    rm -f ~/.config/systemd/user/pi-web.service
    systemctl --user daemon-reload 2>/dev/null || true
    sudo systemctl stop    jetson-clocks-boot 2>/dev/null || true
    sudo systemctl disable jetson-clocks-boot 2>/dev/null || true
    sudo rm -f /etc/systemd/system/jetson-clocks-boot.service
    sudo rm -f /etc/sudoers.d/token-jet-wifi
    sudo systemctl daemon-reload 2>/dev/null || true
    rm -rf  "$INSTALL_BASE"
    rm -f   "$BIN_DIR/token-jet" "$BIN_DIR/token-jet-tui"
    rm -f   ~/bin/jetson-infer ~/bin/jetson-infer.service
    rm -f   ~/.pi/agent/extensions/wifi-manager.ts
    echo ""
    echo "Uninstalled."
    echo "  llama.cpp preserved at: ~/llama.cpp"
    echo "  Config preserved at:    $CONFIG_DIR"
    echo "  Models preserved at:    ~/models/"
    echo "  Remove manually if desired: rm -rf $CONFIG_DIR ~/models/ ~/llama.cpp"
    exit 0
fi

# ── OS upgrade ───────────────────────────────────────────────────────────────
echo "Upgrading Ubuntu packages..."
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq
echo "  apt upgrade: OK"
echo ""

# ── Prerequisite check ────────────────────────────────────────────────────────
echo "Checking prerequisites..."

# Python
PY_VER=$(python3 -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2>/dev/null || echo "0 0")
PY_MAJOR=$(echo "$PY_VER" | cut -d' ' -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d' ' -f2)
if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 9 ]]; }; then
    echo "  ERROR: Python 3.9+ required (found ${PY_MAJOR}.${PY_MINOR})" >&2
    exit 1
fi
echo "  Python ${PY_MAJOR}.${PY_MINOR}: OK"

# Build tools + python3-venv (Ubuntu strips ensurepip from system Python)
# cuda-nvcc + libcublas-dev: JetPack ships CUDA runtime but NOT the compiler
# or cuBLAS dev headers by default — both are required to build llama.cpp with
# GPU support. They are versioned packages in the L4T repo (e.g. -13-2).
MISSING_PKGS=()
command -v cmake &>/dev/null || MISSING_PKGS+=("cmake")
command -v gcc   &>/dev/null || MISSING_PKGS+=("build-essential")
# On Ubuntu 24.04, python3-venv alone doesn't provide ensurepip for Python 3.12.
# The version-specific package (e.g. python3.12-venv) is required.
PY_VENV_PKG="python${PY_MAJOR}.${PY_MINOR}-venv"
python3 -m ensurepip --version &>/dev/null || MISSING_PKGS+=("$PY_VENV_PKG")

# Detect versioned CUDA packages from the L4T repo
_latest_pkg() { apt-cache search "^${1}-" 2>/dev/null | awk '{print $1}' | sort -V | tail -1; }

if ! command -v nvcc &>/dev/null && ! compgen -G "/usr/local/cuda*/bin/nvcc" > /dev/null 2>&1; then
    PKG=$(_latest_pkg "cuda-nvcc")
    MISSING_PKGS+=("${PKG:-cuda-nvcc}")
fi
# Check for cuBLAS dev headers specifically — the runtime package may ship libcublas.so
# already, but CMake's CUDA::cublas target requires cublas_v2.h from the -dev package.
if ! find /usr/local/cuda*/include -name 'cublas_v2.h' 2>/dev/null | grep -q .; then
    PKG=$(_latest_pkg "libcublas-dev")
    MISSING_PKGS+=("${PKG:-libcublas-dev}")
fi

if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
    echo "  Installing build tools: ${MISSING_PKGS[*]}..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq "${MISSING_PKGS[@]}"
fi
echo "  cmake $(cmake --version | head -1 | awk '{print $3}'): OK"
echo "  python3-venv: OK"

# CUDA — JetPack puts nvcc at /usr/local/cuda-X.Y/bin/nvcc.
# Check known locations directly before falling back to a PATH search.
NVCC_BIN=""
for candidate in /usr/local/cuda/bin/nvcc /usr/local/cuda-*/bin/nvcc; do
    if [[ -x "$candidate" ]]; then
        NVCC_BIN="$candidate"
        break
    fi
done
command -v nvcc &>/dev/null && NVCC_BIN="$(command -v nvcc)"

if [[ -n "$NVCC_BIN" ]]; then
    CUDA_VER=$("$NVCC_BIN" --version 2>/dev/null | grep -oP 'release \K[0-9]+\.[0-9]+' || echo "?")
    echo "  CUDA ${CUDA_VER}: OK  (${NVCC_BIN})"
    CUDA_ARCH="87"   # Jetson Orin Nano (Ampere sm_87)
    CUDA_FLAGS="-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCH}"
    # Ensure nvcc is on PATH for cmake's CUDA detection
    NVCC_DIR="$(dirname "$NVCC_BIN")"
    export PATH="${NVCC_DIR}:${PATH}"
    # Persist CUDA bin in .bashrc so it's available after install
    if ! grep -q 'cuda/bin\|cuda-[0-9]' ~/.bashrc 2>/dev/null; then
        echo "export PATH=\"${NVCC_DIR}:\$PATH\"" >> ~/.bashrc
        echo "  Added ${NVCC_DIR} to ~/.bashrc"
    fi
else
    echo ""
    echo "  ERROR: nvcc not found — cannot build with GPU support." >&2
    echo "  Install the CUDA toolkit and re-run:" >&2
    echo "    sudo apt-get install cuda-nvcc" >&2
    echo "  Then re-run this installer." >&2
    exit 1
fi

# Detect CUDA library path for LD_LIBRARY_PATH in config/launcher
CUDA_LIB_PATH=$(find /usr/local -maxdepth 4 -name "libcudart.so*" -printf "%h\n" 2>/dev/null \
    | grep -v "stubs" | head -1 || echo "")
if [[ -z "$CUDA_LIB_PATH" ]]; then
    CUDA_LIB_PATH="/usr/local/cuda/targets/sbsa-linux/lib"
fi
echo "  CUDA libs: $CUDA_LIB_PATH"

# ── Performance mode ──────────────────────────────────────────────────────────
# nvpmodel -m 0 selects MAXN (full performance) and persists across reboots.
# jetson-clocks-boot.service locks CPU/GPU at max frequency on every boot.
# Both run now so the llama.cpp build and all subsequent inference benefit immediately.
echo "Setting performance mode..."
if command -v nvpmodel &>/dev/null; then
    # </dev/null: prevents nvpmodel's interactive reboot prompt from consuming
    # the script pipe when run via curl | bash. &>/dev/null: suppresses the
    # verbose WARNING/ERROR lines that nvpmodel writes to stdout.
    sudo nvpmodel -m 0 </dev/null &>/dev/null \
        && echo "  nvpmodel: MAXN (mode 0) set" \
        || echo "  nvpmodel: mode 0 will apply after reboot (non-fatal)"
else
    echo "  nvpmodel: not found, skipping"
fi
sudo cp "${REPO_ROOT}/jetson-clocks-boot.service" /etc/systemd/system/jetson-clocks-boot.service
sudo systemctl daemon-reload
sudo systemctl enable jetson-clocks-boot 2>/dev/null || true
sudo systemctl start  jetson-clocks-boot 2>/dev/null || true
echo "  jetson-clocks: enabled + active (locks clocks at max on every boot)"

# ── llama.cpp build helper ────────────────────────────────────────────────────
# Cap at 3 jobs: each nvcc invocation can spike to ~1.5 GB on Jetson's unified
# memory; 4 jobs × 1.5 GB = 6 GB which leaves the 8 GB system very tight.
BUILD_JOBS=$(( $(nproc) < 3 ? $(nproc) : 3 ))

_build_llama() {
    local label="$1"      # display label
    local repo_url="$2"   # git clone URL
    local dest_dir="$3"   # destination directory (e.g. ~/llama.cpp)
    local branch="$4"     # branch/tag to checkout, or "" for default
    local binary="${dest_dir}/build/bin/llama-server"

    echo ""
    echo "── ${label} ─────────────────────────────────────────────────────────────"

    if [[ -x "$binary" ]]; then
        echo "  Already built at ${binary} — skipping."
        echo "  (Delete ${dest_dir}/build to force a rebuild.)"
        return 0
    fi

    # Clone if needed
    if [[ ! -d "${dest_dir}/.git" ]]; then
        echo "  Cloning ${repo_url}..."
        git clone --depth 1 ${branch:+--branch "$branch"} "$repo_url" "$dest_dir"
    else
        echo "  Source already at ${dest_dir}"
        if [[ -n "$branch" ]]; then
            git -C "$dest_dir" checkout "$branch" 2>/dev/null || true
        fi
    fi

    # CMake configure
    echo "  Configuring (output → /tmp/token-jet-cmake-${label}.log)..."
    local cmake_log="/tmp/token-jet-cmake-${label}.log"
    # shellcheck disable=SC2086
    if ! cmake -S "$dest_dir" -B "${dest_dir}/build" \
            $CUDA_FLAGS \
            -DCMAKE_BUILD_TYPE=Release \
            -DLLAMA_BUILD_TESTS=OFF \
            > "$cmake_log" 2>&1; then
        echo "  ERROR: CMake configure failed." >&2
        tail -20 "$cmake_log" >&2
        exit 1
    fi
    echo "  Configure: OK"

    # Build — stream output so the user can see progress during the long compile
    echo "  Building llama-server with ${BUILD_JOBS} jobs (~15-25 min on Jetson Orin)..."
    echo "  Output is shown below and also logged to /tmp/token-jet-build-${label}.log"
    echo ""
    local build_log="/tmp/token-jet-build-${label}.log"
    cmake --build "${dest_dir}/build" \
        --config Release \
        --target llama-server \
        --parallel "$BUILD_JOBS" \
        2>&1 | tee "$build_log"
    local build_exit="${PIPESTATUS[0]}"
    echo ""
    if [[ "$build_exit" -ne 0 ]]; then
        echo "  ERROR: Build failed (exit ${build_exit})." >&2
        echo "  Full log: $build_log" >&2
        exit 1
    fi

    if [[ -x "$binary" ]]; then
        echo "  Build: OK  →  ${binary}"
    else
        echo "  ERROR: Build completed but binary not found at ${binary}" >&2
        exit 1
    fi

    # Clean intermediate files to recover disk space (~1-2 GB per build).
    # The binary and shared libs are preserved; source stays for future rebuilds.
    echo "  Cleaning build intermediates to free disk space..."
    find "${dest_dir}/build" -name "*.o"  -delete 2>/dev/null || true
    find "${dest_dir}/build" -name "*.a"  -delete 2>/dev/null || true
    rm -rf "${dest_dir}/build/CMakeFiles" 2>/dev/null || true
    echo "  Disk freed."
}

# ── Build llama.cpp (used by all models) ─────────────────────────────────────
_build_llama \
    "llama.cpp" \
    "https://github.com/ggml-org/llama.cpp" \
    "${HOME}/llama.cpp" \
    ""

echo ""

# ── Build PrismML llama.cpp fork (required for Bonsai GPU inference) ──────────
# The PrismML fork adds CUDA kernels for TYPE_41/TYPE_42 ternary weights used
# by Bonsai models. Without it, Bonsai falls back to CPU. Mainline llama.cpp
# can load Bonsai files but has no GPU path for ternary quantization.
if $BUILD_PRISM; then
    _build_llama \
        "llama.cpp-prism" \
        "https://github.com/PrismML-Eng/llama.cpp" \
        "${HOME}/llama.cpp-prism" \
        "pr/q2_0-cuda"
    echo ""
else
    echo "── PrismML fork ──────────────────────────────────────────────────────────────"
    echo "  Skipped (--no-prism-build). Bonsai models will run on CPU until built."
    echo "  To build later: ~/Token-Jet/scripts/install-local.sh --upgrade"
    echo ""
fi

# ── Models directory ──────────────────────────────────────────────────────────
mkdir -p "${HOME}/models"
echo "Models directory: ~/models/"

# ── jetson-infer ──────────────────────────────────────────────────────────────
echo "Installing jetson-infer..."
mkdir -p ~/bin
# Use a symlink so `git pull` in ~/Token-Jet picks up updates automatically.
ln -sf "${REPO_ROOT}/jetson-infer" ~/bin/jetson-infer
cp "${REPO_ROOT}/jetson-infer.service" ~/bin/jetson-infer.service
chmod +x "${REPO_ROOT}/jetson-infer"
echo "  ~/bin/jetson-infer: OK (symlink → ${REPO_ROOT}/jetson-infer)"

if ! grep -q '"$HOME/bin"\|$HOME/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
fi

# ── TUI venv ──────────────────────────────────────────────────────────────────
echo "Setting up TUI environment..."
if [[ "$MODE" == "upgrade" ]]; then
    "${INSTALL_BASE}/venv/bin/pip" install -q --upgrade "${REPO_ROOT}/tui/"
    echo "  TUI upgraded OK"
else
    mkdir -p "$INSTALL_BASE" "$BIN_DIR"
    if [[ ! -x "${INSTALL_BASE}/venv/bin/pip" ]]; then
        rm -rf "${INSTALL_BASE}/venv"
        python3 -m venv "${INSTALL_BASE}/venv"
        echo "  Created venv"
    fi
    echo "  Installing dependencies..."
    "${INSTALL_BASE}/venv/bin/pip" install -q --upgrade pip
    "${INSTALL_BASE}/venv/bin/pip" install -q "${REPO_ROOT}/tui/"
    echo "  token-jet-tui: OK"
fi

# ── Launcher ──────────────────────────────────────────────────────────────────
cat > "${BIN_DIR}/token-jet" << LAUNCHER_EOF
#!/usr/bin/env bash
export LD_LIBRARY_PATH="${CUDA_LIB_PATH}:\${LD_LIBRARY_PATH:-}"
exec "\${HOME}/.local/share/token-jet/venv/bin/token-jet-tui" "\$@"
LAUNCHER_EOF
chmod +x "${BIN_DIR}/token-jet"
cp "${BIN_DIR}/token-jet" "${BIN_DIR}/token-jet-tui"
echo "  launcher: ~/.local/bin/token-jet"

if ! grep -q '.local/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

# ── Pi coding agent ───────────────────────────────────────────────────────────
# Pi requires Node.js 22+. Ubuntu 24.04's default repos ship Node 18, so we
# add the NodeSource repo if a suitable version isn't already present.
echo "Installing pi coding agent..."
NODE_OK=false
if command -v node &>/dev/null; then
    NODE_MAJOR=$(node --version 2>/dev/null | grep -oP '(?<=v)\d+' || echo 0)
    [[ "$NODE_MAJOR" -ge 22 ]] && NODE_OK=true
fi
if ! $NODE_OK; then
    echo "  Installing Node.js 22 (via NodeSource)..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - 2>/dev/null
    sudo apt-get install -y -qq nodejs
fi
echo "  Node.js $(node --version): OK"

# npm global installs default to /usr/lib/node_modules which needs root.
# Redirect to a user-local prefix so installs never need sudo.
NPM_GLOBAL="${HOME}/.npm-global"
if [[ "$(npm config get prefix 2>/dev/null)" != "$NPM_GLOBAL" ]]; then
    mkdir -p "$NPM_GLOBAL"
    npm config set prefix "$NPM_GLOBAL"
fi
if ! grep -q '.npm-global/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc
fi
export PATH="${NPM_GLOBAL}/bin:${PATH}"

# Install pi. --ignore-scripts matches upstream install recommendation.
npm install -g --ignore-scripts @earendil-works/pi-coding-agent 2>/dev/null \
    && echo "  pi $(pi --version 2>/dev/null || echo installed): OK" \
    || echo "  WARNING: pi install failed — check npm output above"

# Deploy default settings before 'pi install' so the repo version lands on fresh
# installs. pi install creates settings.json as a side effect, so this must run
# first; otherwise the conditional below always finds the file already present.
if [[ ! -f ~/.pi/agent/settings.json ]]; then
    mkdir -p ~/.pi/agent/
    cp "${REPO_ROOT}/pi/settings.json" ~/.pi/agent/settings.json
    echo "  pi settings: ~/.pi/agent/settings.json"
else
    echo "  pi settings: preserved (already exists)"
fi

# Install pi extensions — pre-configured and available immediately after install.
# Each uses pi's own package manager (pi install npm:...) which handles placement
# into ~/.pi/agent/ automatically.
echo "  Installing pi extensions..."
yes | pi install npm:pi-mcp-adapter 2>/dev/null \
    && echo "    pi-mcp-adapter: OK" \
    || echo "    WARNING: pi-mcp-adapter install failed"

# Install pi-web (browser UI for pi sessions — accessible at http://<jetson-ip>:30141).
npm install -g @agegr/pi-web 2>/dev/null \
    && echo "  pi-web: OK" \
    || echo "  WARNING: pi-web install failed — check npm output above"

# Install ddg-search skill dependencies (shipped in this repo — no clone needed,
# no API key required). npm install is idempotent; safe on both install and upgrade.
npm --prefix "${REPO_ROOT}/pi/ddg-search" install --ignore-scripts 2>/dev/null \
    && echo "  ddg-search skill: ~/Token-Jet/pi/ddg-search (keyless web search)" \
    || echo "  WARNING: ddg-search npm install failed"

# Deploy provider extension — always overwrite so repo changes land on upgrade.
mkdir -p ~/.pi/agent/extensions/
cp "${REPO_ROOT}/pi/jetson-provider.ts" ~/.pi/agent/extensions/jetson-provider.ts
echo "  jetson-provider: ~/.pi/agent/extensions/jetson-provider.ts"
cp "${REPO_ROOT}/pi/wifi-manager.ts" ~/.pi/agent/extensions/wifi-manager.ts
echo "  wifi-manager: ~/.pi/agent/extensions/wifi-manager.ts"
chmod +x "${REPO_ROOT}/pi/wifi-manager/wifi.py"

# Merge required settings into settings.json. 'pi install' can rewrite
# settings.json with only its own fields, stripping extensions/skills/
# compaction that we set above. This runs after pi install and after the
# extensions are deployed to guarantee all required keys are present.
python3 - <<'PYEOF'
import json, os
path = os.path.expanduser("~/.pi/agent/settings.json")
try:
    current = json.loads(open(path).read()) if os.path.exists(path) else {}
except Exception:
    current = {}
required = {
    "enableInstallTelemetry": False,
    "PI_SKIP_VERSION_CHECK": True,
    "extensions": [
        "~/.pi/agent/extensions/jetson-provider.ts",
        "~/.pi/agent/extensions/wifi-manager.ts",
    ],
    "skills": ["~/Token-Jet/pi/ddg-search"],
    "thinkingBudgets": {"minimal": 256, "low": 512, "medium": 1024, "high": 2048, "xhigh": 4096},
    "compaction": {"reserveTokens": 4096, "keepRecentTokens": 2048},
}
changed = [k for k in required if k not in current]
for k in changed:
    current[k] = required[k]
if changed:
    open(path, "w").write(json.dumps(current, indent=2) + "\n")
    print(f"  pi settings: merged missing fields: {', '.join(changed)}")
else:
    print("  pi settings: all required fields present")
PYEOF

# Write the jetson-local API key into auth.json so pi's auth check always
# passes for the local provider. pi requires every provider to have auth
# configured; llama-server ignores the Bearer header since it has no key.
# We merge rather than overwrite so existing cloud provider tokens survive.
mkdir -p ~/.pi/agent/
python3 - <<'PYEOF'
import json, os, sys
path = os.path.expanduser("~/.pi/agent/auth.json")
try:
    d = json.loads(open(path).read()) if os.path.exists(path) else {}
except Exception:
    d = {}
if d.get("jetson-local", {}).get("key") != "none":
    d["jetson-local"] = {"type": "api_key", "key": "none"}
    open(path, "w").write(json.dumps(d, indent=2) + "\n")
    print("  pi auth: jetson-local credential written to auth.json")
else:
    print("  pi auth: auth.json already configured")
PYEOF

# Sudoers rule — grants NOPASSWD for nmcli so the wifi-manager skill can toggle
# the radio and connect to networks from a non-interactive SSH/pi session.
SUDOERS_FILE="/etc/sudoers.d/token-jet-wifi"
SUDOERS_RULE="${JETSON_USER} ALL=(ALL) NOPASSWD: /usr/bin/nmcli"
if ! sudo grep -qF "$SUDOERS_RULE" "$SUDOERS_FILE" 2>/dev/null; then
    printf '%s\n' "$SUDOERS_RULE" \
        | sudo tee "$SUDOERS_FILE" > /dev/null
    sudo chmod 440 "$SUDOERS_FILE"
    echo "  sudoers: /etc/sudoers.d/token-jet-wifi (nmcli NOPASSWD)"
else
    echo "  sudoers: already configured"
fi

# ── Pi-web service ────────────────────────────────────────────────────────────
# Deploy the pi-web systemd user service on every install/upgrade so changes
# from the repo land automatically. Then start (install) or restart (upgrade).
echo "Installing pi-web service..."
mkdir -p ~/.config/systemd/user/
cp "${REPO_ROOT}/pi-web.service" ~/.config/systemd/user/pi-web.service
systemctl --user daemon-reload 2>/dev/null || true
if [[ "$MODE" == "upgrade" ]]; then
    systemctl --user restart pi-web 2>/dev/null || true
    echo "  pi-web service: restarted"
else
    systemctl --user enable pi-web 2>/dev/null || true
    systemctl --user start  pi-web 2>/dev/null || true
    echo "  pi-web service: enabled + started"
fi

# ── dufs file server ──────────────────────────────────────────────────────────
# dufs serves ~/shared/ over HTTP (browser drag-and-drop) and WebDAV (native
# OS drive mounting). No build required — pre-built aarch64 musl binary.
# Mac:     Finder → Go → Connect to Server → http://<jetson-ip>:30140
# Windows: Map Network Drive → \\<jetson-ip>@30140\DavWWWRoot
echo "Installing dufs file server..."
DUFS_VERSION="0.46.0"
DUFS_BIN="${HOME}/bin/dufs"
DUFS_URL="https://github.com/sigoden/dufs/releases/download/v${DUFS_VERSION}/dufs-v${DUFS_VERSION}-aarch64-unknown-linux-musl.tar.gz"
_current_dufs_ver=$("$DUFS_BIN" --version 2>/dev/null | grep -oP '[\d.]+' | head -1 || echo "none")
if [[ ! -x "$DUFS_BIN" ]] || [[ "$_current_dufs_ver" != "$DUFS_VERSION" ]]; then
    echo "  Downloading dufs v${DUFS_VERSION} (aarch64-linux-musl)..."
    curl -fsSL "$DUFS_URL" -o /tmp/dufs.tar.gz
    tar -xzf /tmp/dufs.tar.gz -C /tmp/ dufs
    mv /tmp/dufs "$DUFS_BIN"
    chmod +x "$DUFS_BIN"
    rm -f /tmp/dufs.tar.gz
    echo "  dufs v${DUFS_VERSION}: installed at ~/bin/dufs"
else
    echo "  dufs v${DUFS_VERSION}: already current"
fi
mkdir -p "${HOME}/shared"
echo "  shared directory: ~/shared/"
mkdir -p ~/.config/systemd/user/
cp "${REPO_ROOT}/dufs.service" ~/.config/systemd/user/dufs.service
systemctl --user daemon-reload 2>/dev/null || true
if [[ "$MODE" == "upgrade" ]]; then
    systemctl --user restart dufs 2>/dev/null || true
    echo "  dufs service: restarted"
else
    systemctl --user enable dufs 2>/dev/null || true
    systemctl --user start  dufs 2>/dev/null || true
    echo "  dufs service: enabled + started at port 30140"
fi

# ── Default config (install only) ────────────────────────────────────────────
if [[ "$MODE" == "install" ]]; then
    mkdir -p "$CONFIG_DIR"
    if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
        cat > "${CONFIG_DIR}/config.toml" << TOML_EOF
# Token-Jet configuration
model_dir            = "/home/${JETSON_USER}/models"
llama_cpp_bin        = "/home/${JETSON_USER}/llama.cpp/build/bin"
server_port          = 1234
ld_library_path      = "${CUDA_LIB_PATH}"
jetson_infer_bin     = "/home/${JETSON_USER}/bin/jetson-infer"
hf_download_timeout  = 300

# Model to load on startup. If unset, uses the project-recommended model
# (Qwen3.5-4B-Coder) if downloaded, then the first .gguf found in model_dir.
# startup_model = "/home/${JETSON_USER}/models/qwen3.5-4B-super-coder.Q4_0.gguf"

# Cap thinking tokens on reasoning models (0 = no cap).
# reasoning_budget = 1024
TOML_EOF
        echo "  config: ${CONFIG_DIR}/config.toml"
    else
        echo "  config preserved (already exists)"
    fi
fi

# ── Systemd user service ─────────────────────────────────────────────────────
# Refresh the service file on every run so --upgrade picks up changes.
echo "Installing jetson-infer service..."
mkdir -p ~/.config/systemd/user/
cp ~/bin/jetson-infer.service ~/.config/systemd/user/jetson-infer.service
systemctl --user daemon-reload 2>/dev/null || true
if [[ "$MODE" == "upgrade" ]]; then
    systemctl --user restart jetson-infer 2>/dev/null || true
    echo "  jetson-infer service: restarted"
else
    systemctl --user enable jetson-infer 2>/dev/null || true
    sudo loginctl enable-linger "$JETSON_USER" 2>/dev/null || true
    echo "  jetson-infer service: enabled"
fi

# ── jetson-clocks service (install + upgrade) ─────────────────────────────────
# Refresh the system service file on every install/upgrade so changes land.
sudo cp "${REPO_ROOT}/jetson-clocks-boot.service" /etc/systemd/system/jetson-clocks-boot.service
sudo systemctl daemon-reload 2>/dev/null || true

# ── NVGPU reinit service ──────────────────────────────────────────────────────
# nvgpu probes at early kernel boot before /lib → /usr/lib symlinks resolve.
# The firmware path /lib/firmware/nvidia/ga10b/acr-gsp*.prod fails with ELOOP
# (error -40), leaving the GPU in a CPU-fallback state. A one-shot service that
# reloads nvgpu after local-fs.target fixes this for every subsequent boot.
echo "Installing nvgpu-reinit service..."
sudo tee /etc/systemd/system/nvgpu-reinit.service > /dev/null << 'SVCEOF'
[Unit]
Description=NVGPU reinit — reload nvgpu after rootfs mounts to fix /lib firmware path
DefaultDependencies=no
After=local-fs.target
Before=sysinit.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c '/sbin/modprobe -r nvgpu; /sbin/modprobe nvgpu'

[Install]
WantedBy=sysinit.target
SVCEOF
sudo systemctl daemon-reload
sudo systemctl enable nvgpu-reinit.service 2>/dev/null \
    && echo "  nvgpu-reinit: enabled" \
    || echo "  nvgpu-reinit: enable failed (non-fatal)"

# ── USB device mode (RNDIS-only) ─────────────────────────────────────────────
# NVIDIA's default enables ACM + UMS + ECM alongside RNDIS. On Windows, ACM
# (USB serial) and UMS (16 MB FAT image) cause the host to loop-enumerate the
# composite gadget indefinitely. Fix: disable everything except RNDIS.
# bcdDevice 0x0003 forces Windows to flush its stale composite-device driver
# cache, picking up the new single-function RNDIS configuration cleanly.
echo "Configuring USB device mode (RNDIS-only)..."
USB_CFG="/opt/nvidia/l4t-usb-device-mode/nv-l4t-usb-device-mode-config.sh"
USB_START="/opt/nvidia/l4t-usb-device-mode/nv-l4t-usb-device-mode-start.sh"
USB_CHANGED=false
if [[ -f "$USB_CFG" ]]; then
    if grep -qE '^enable_(acm|ums|ecm)=1' "$USB_CFG"; then
        sudo sed -i \
            -e 's/^enable_acm=1/enable_acm=0/' \
            -e 's/^enable_ums=1/enable_ums=0/' \
            -e 's/^enable_ecm=1/enable_ecm=0/' \
            "$USB_CFG"
        USB_CHANGED=true
        echo "  usb-mode config: ACM/UMS/ECM disabled (RNDIS-only)"
    else
        echo "  usb-mode config: already configured"
    fi
else
    echo "  usb-mode config: not found, skipping (non-Jetson or service not installed)"
fi
if [[ -f "$USB_START" ]]; then
    if grep -q '0x0002' "$USB_START"; then
        sudo sed -i 's/0x0002/0x0003/' "$USB_START"
        USB_CHANGED=true
        echo "  usb-mode start: bcdDevice bumped to 0x0003"
    else
        echo "  usb-mode start: bcdDevice already at 0x0003"
    fi
fi
if [[ -f "$USB_CFG" ]]; then
    if grep -q 'net_dhcp_lease_time=15' "$USB_CFG"; then
        sudo sed -i 's/net_dhcp_lease_time=15/net_dhcp_lease_time=3600/' "$USB_CFG"
        USB_CHANGED=true
        echo "  usb-mode dhcp: lease time 15 s → 3600 s"
    else
        echo "  usb-mode dhcp: lease time already configured"
    fi
fi

# Drop-in: make nv-l4t-usb-device-mode start after nvgpu-reinit.
# nvgpu module reload floods udev events; the USB service times out waiting
# for the udev queue unless it is explicitly ordered after nvgpu-reinit.
sudo mkdir -p /etc/systemd/system/nv-l4t-usb-device-mode.service.d/
sudo tee /etc/systemd/system/nv-l4t-usb-device-mode.service.d/after-nvgpu.conf > /dev/null << 'DROPIN'
[Unit]
After=nvgpu-reinit.service
DROPIN
echo "  usb-mode ordering: After=nvgpu-reinit.service drop-in installed"
if $USB_CHANGED; then
    sudo systemctl restart nv-l4t-usb-device-mode 2>/dev/null \
        && echo "  nv-l4t-usb-device-mode: restarted" \
        || echo "  nv-l4t-usb-device-mode: restart skipped (service not active)"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
JETSON_IP=$(hostname -I | awk '{print $1}')
echo "=== Installation complete! ==="
echo ""
echo "  source ~/.bashrc      (or open a new terminal)"
echo "  token-jet             (launch the TUI dashboard)"
echo "  pi-web                (start browser UI manually, if not using the service)"
echo ""
echo "Services running as background systemd user services:"
echo "  http://${JETSON_IP}:30141   ← pi-web  (browser UI for pi coding agent)"
echo "  http://${JETSON_IP}:30140   ← dufs    (file share — upload/download + WebDAV)"
echo ""
echo "File sharing from Mac/Windows:"
echo "  Browser:  http://${JETSON_IP}:30140"
echo "  Mac mount: Finder → Go → Connect to Server → http://${JETSON_IP}:30140"
echo "  Windows:   Map Network Drive → \\\\${JETSON_IP}@30140\\DavWWWRoot"
echo "  Drop files into ~/shared/ for pi to work on"
echo ""
echo "First run — do these steps inside the TUI:"
echo "  1. Ctrl+D  → open the model browser and download a model"
echo "               (Qwen3.5-4B-Coder recommended — 2.5 GB, 20 t/s)"
echo "  2. Ctrl+S  → select and start the downloaded model"
echo "  3. Type in the chat box and press Enter"
echo ""
echo "The TUI will guide you — no need to start the server manually."
echo ""
