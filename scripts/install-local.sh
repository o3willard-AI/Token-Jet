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
    echo "  llama.cpp preserved at: ~/llama.cpp  ~/llama.cpp-prism"
    echo "  Config preserved at:    $CONFIG_DIR"
    echo "  Models preserved at:    ~/models/"
    echo "  Remove manually if desired: rm -rf $CONFIG_DIR ~/models/ ~/llama.cpp ~/llama.cpp-prism"
    exit 0
fi

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

# Build tools + python3-venv (Ubuntu 22.04 strips ensurepip from system Python)
MISSING_PKGS=()
command -v cmake &>/dev/null || MISSING_PKGS+=("cmake")
command -v gcc   &>/dev/null || MISSING_PKGS+=("build-essential")
python3 -m venv --help &>/dev/null || MISSING_PKGS+=("python3-venv")
if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
    echo "  Installing build tools: ${MISSING_PKGS[*]}..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq cmake build-essential python3-venv
fi
echo "  cmake $(cmake --version | head -1 | awk '{print $3}'): OK"
echo "  python3-venv: OK"

# CUDA — JetPack puts nvcc at /usr/local/cuda/bin which is NOT on the default PATH.
# Check the known location directly before falling back to a PATH search.
NVCC_BIN=""
for candidate in /usr/local/cuda/bin/nvcc /usr/local/cuda-*/bin/nvcc; do
    if [[ -x "$candidate" ]]; then
        NVCC_BIN="$candidate"
        break
    fi
done
command -v nvcc &>/dev/null && NVCC_BIN="nvcc"

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
    echo "  WARNING: nvcc not found — llama.cpp will build CPU-only (very slow for inference)"
    echo "    Expected at: /usr/local/cuda/bin/nvcc"
    echo "    Verify JetPack CUDA is installed: dpkg -l | grep cuda"
    CUDA_FLAGS=""
fi

# Detect CUDA library path for LD_LIBRARY_PATH in config/launcher
CUDA_LIB_PATH=$(find /usr/local -maxdepth 4 -name "libcudart.so*" -printf "%h\n" 2>/dev/null \
    | grep -v "stubs" | head -1 || echo "")
if [[ -z "$CUDA_LIB_PATH" ]]; then
    CUDA_LIB_PATH="/usr/local/cuda/targets/sbsa-linux/lib"
fi
echo "  CUDA libs: $CUDA_LIB_PATH"

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

# ── Build llama.cpp (standard — used by MiniCPM5 and Qwen3.5) ───────────────
_build_llama \
    "llama.cpp" \
    "https://github.com/ggml-org/llama.cpp" \
    "${HOME}/llama.cpp" \
    ""

# ── Build llama.cpp-prism (PrismML fork — required for Ternary-Bonsai-8B) ───
_build_llama \
    "llama.cpp-prism" \
    "https://github.com/PrismML-Eng/llama.cpp" \
    "${HOME}/llama.cpp-prism" \
    "prism"

echo ""

# ── Models directory ──────────────────────────────────────────────────────────
mkdir -p "${HOME}/models"
echo "Models directory: ~/models/"

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
    "${INSTALL_BASE}/venv/bin/pip" install -q --upgrade "${REPO_ROOT}/tui/"
    echo "  TUI upgraded OK"
else
    mkdir -p "$INSTALL_BASE" "$BIN_DIR"
    if [[ ! -d "${INSTALL_BASE}/venv" ]]; then
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

# ── Default config (install only) ────────────────────────────────────────────
if [[ "$MODE" == "install" ]]; then
    mkdir -p "$CONFIG_DIR"
    if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
        cat > "${CONFIG_DIR}/config.toml" << TOML_EOF
# Token-Jet configuration
model_dir            = "/home/${JETSON_USER}/models"
llama_cpp_bin        = "/home/${JETSON_USER}/llama.cpp/build/bin"
llama_cpp_prism_bin  = "/home/${JETSON_USER}/llama.cpp-prism/build/bin"
default_model        = ""
server_host          = "127.0.0.1"
server_port          = 1234
ld_library_path      = "${CUDA_LIB_PATH}"
jetson_infer_bin     = "/home/${JETSON_USER}/bin/jetson-infer"
hf_download_timeout  = 300
TOML_EOF
        echo "  config: ${CONFIG_DIR}/config.toml"
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
