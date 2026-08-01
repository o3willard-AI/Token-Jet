# Token-Jet — Agent Reference

Internal document for Claude Code and other agents working in this repo.
**Do not commit or push this file.**

---

## Project at a Glance

Token-Jet deploys a self-contained local AI server on a **Jetson Orin Nano 8 GB** (JetPack 6.x / Ubuntu 22.04 or 24.04). A single install command builds everything from source, wires up a TUI dashboard, a coding agent, and a browser UI, and makes the Jetson reachable over Wi-Fi, Ethernet, or a bare USB-C cable — no cloud, no subscriptions.

**Live deployment target:**
- Jetson IP: `192.168.101.91` (Wi-Fi/Ethernet) or `192.168.55.1` (USB)
- SSH user: `jetuser` / password: `101abn`
- Repo clone on Jetson: `~/Token-Jet`

---

## Repository Layout

```
Token-Jet/
├── jetson-infer              # Python CLI: start/stop/status/watchdog/usb-status
├── jetson-infer.service      # Systemd user unit: auto-starts inference server on boot
├── pi-web.service            # Systemd user unit: auto-starts pi-web on port 30141
├── jetson-clocks-boot.service# System unit: locks CPU/GPU at max frequency on boot
├── tui/                      # Textual Python TUI dashboard
│   └── token_jet_tui/
├── pi/                       # pi coding agent extensions (TypeScript)
│   ├── jetson-provider.ts    # Provider registration + list_models, switch_model, web_search, fetch_url + /models, /switch commands
│   ├── wifi-manager.ts       # Wi-Fi tools + /wifi command
│   ├── wifi-manager/
│   │   └── wifi.py           # nmcli wrapper backend for wifi-manager.ts
│   ├── settings.json         # pi default settings (deployed to ~/.pi/agent/settings.json)
│   └── ddg-search/           # Node.js DuckDuckGo search skill
│       ├── search.js         # Returns titles/links/snippets
│       └── content.js        # Fetches URL → Markdown
├── scripts/
│   ├── install-local.sh      # Run directly on Jetson (recommended)
│   └── install.sh            # Run from workstation, SSH-deploys to Jetson
├── eval/
│   ├── coding-eval.py        # 5-task coding benchmark
│   └── it-eval.py            # 5-scenario IT troubleshooting benchmark
└── docs/
    ├── hardware-setup.md
    ├── model-results.md
    ├── resilience.md
    └── bonsai-27b.md
```

---

## Component Details

### jetson-infer (Python CLI)

The core server management utility. Runs on the Jetson.

**Key behaviors:**
- `start` — selects best available model (config `startup_model` → `qwen3.5-4B-super-coder.Q4_0.gguf` → first `.gguf` in `~/models/`); calculates maximum context window that fits in shared RAM; launches `llama-server`
- `start --watchdog` — wraps start in a health+memory monitor; restarts on crash or if free RAM drops below `MEMORY_RESTART_THRESHOLD_MB` (200 MB); max 10 consecutive restarts
- `status` — reads PID file, checks `llama-server` process, queries `/health` endpoint
- `stop` — sends SIGTERM to stored PID; fallback `pkill -f llama-server`
- `models` — scans `~/models/*.gguf`, shows size and estimated context
- `switch <model>` — stops current server, starts with new model
- `usb-status` — checks if `192.168.55.1` is assigned on any interface; shows cable state, active DHCP client, inference API health, pi-web health
- `install` — installs systemd user service

**llama-server flags used:**
```
--n-gpu-layers 99        (all layers on GPU)
--ctx-size <calculated>
--host 0.0.0.0
--port 1234
--reasoning auto         (routes <think> tokens to reasoning_content field)
--reasoning-budget N     (optional cap from config; 0 = disabled)
```

**Binary selection:**
- Any model with `bonsai` in the filename → uses `~/llama.cpp-prism/build/bin/llama-server` (PrismML fork with TYPE_41/TYPE_42 CUDA kernels)
- All other models → uses `~/llama.cpp/build/bin/llama-server` (mainline)

**Context calculation:**
- Reads model architecture from GGUF metadata (KV heads, head dim, layer count)
- Hardcoded fallback table for known models (`bonsai8b`, `bonsai8b-g64`, `bonsai27b`)
- Formula: `kv_budget_mb = free_memory_mb * 0.85`; divides by per-token KV cost
- Constants: `SAFETY_MARGIN_MB=512`, `MIN_FREE_MB=256`

**Config file:** `~/.config/token-jet/config.toml`
```toml
model_dir            = "/home/<user>/models"
llama_cpp_bin        = "/home/<user>/llama.cpp/build/bin"
prism_llama_cpp_bin  = "/home/<user>/llama.cpp-prism/build/bin"   # optional override
server_port          = 1234
ld_library_path      = "/usr/local/cuda-13.2/targets/sbsa-linux/lib"
jetson_infer_bin     = "/home/<user>/bin/jetson-infer"
hf_download_timeout  = 300
startup_model        = "/home/<user>/models/qwen3.5-4B-super-coder.Q4_0.gguf"  # optional
reasoning_budget     = 1024   # optional; 0 = no cap
```

**Log files:** `/tmp/jetson-infer.log`, `/tmp/jetson-watchdog.log`

---

### TUI (Python/Textual)

Terminal dashboard installed to `~/.local/share/token-jet/venv/`. Launched via `token-jet` (Jetson) or `token-jet-tui` (SSH launcher from workstation).

**Keyboard shortcuts:**
| Key | Action |
|-----|--------|
| `Ctrl+D` | Model browser (download from Hugging Face) |
| `Ctrl+S` | Switch active model |
| `Ctrl+X` | Remove downloaded model |
| `Ctrl+R` | Reset performance counters |
| `Ctrl+P` | Palette & settings |
| `Ctrl+Q` | Quit |

Downloads stream from HuggingFace with SHA-256 verification. Live status panel shows RAM / CPU / GPU / Temp updated every second.

---

### pi Coding Agent Integration

pi is installed at `~/.npm-global/bin/pi`. Extensions live at `~/.pi/agent/extensions/`.

**`pi/settings.json`** (deployed to `~/.pi/agent/settings.json`):
```json
{
  "model": "jetson-local/local",
  "enableInstallTelemetry": false,
  "PI_SKIP_VERSION_CHECK": true,
  "extensions": ["~/.pi/agent/extensions/jetson-provider.ts"],
  "skills": ["~/Token-Jet/pi/ddg-search"],
  "thinkingBudgets": { "minimal": 256, "low": 512, "medium": 1024, "high": 2048, "xhigh": 4096 }
}
```

**`pi/jetson-provider.ts`** registers:
- Provider `jetson-local` pointing to `http://localhost:1234/v1`
- Tools: `web_search` (DuckDuckGo via `search.js`), `fetch_url` (via `content.js`), `list_models` (scans `~/models/`), `switch_model` (calls `jetson-infer switch`)
- Commands: `/models`, `/switch`

**`pi/wifi-manager.ts`** registers:
- Tools: `wifi_status`, `wifi_scan`, `wifi_on`, `wifi_off`, `wifi_connect`, `wifi_disconnect`, `wifi_forget`
- Command: `/wifi`
- Calls `~/Token-Jet/pi/wifi-manager/wifi.py` via `python3`; all output is JSON
- Timeout: 35 seconds per call

**`pi/wifi-manager/wifi.py`** — nmcli wrapper:
- Uses `nmcli -m multiline` for scan output (handles SSIDs containing colons)
- `line.partition(":")` splits on first colon only
- Privileged ops (`radio wifi on/off`, `device wifi connect`, `device disconnect`, `connection delete`) call `sudo nmcli` — requires the sudoers rule
- Output: always JSON to stdout

**Sudoers rule** (`/etc/sudoers.d/token-jet-wifi`, mode 440):
```
<user> ALL=(ALL) NOPASSWD: /usr/bin/nmcli
```

**pi auth:** `~/.pi/agent/auth.json` must have `"jetson-local": {"type": "api_key", "key": "none"}` — llama-server ignores Bearer headers but pi requires auth to be configured.

**pi-web service** (`pi-web.service`, user unit): runs `pi-web` on `0.0.0.0:30141`. No application authentication — LAN-only use.

**ddg-search skill:** Node.js scripts in `~/Token-Jet/pi/ddg-search/`. Wrappers at `/usr/local/bin/ddg-search` and `/usr/local/bin/fetch-url` (installed by `install.sh`; not present in `install-local.sh`).

**After a `/switch` model change:** user must `/quit` pi and reopen it — pi reconnects to the new model from a fresh session.

---

### USB Device Mode (Air-Gapped)

Managed by NVIDIA's `nv-l4t-usb-device-mode.service`.

**Config files patched by the installer:**
- `/opt/nvidia/l4t-usb-device-mode/nv-l4t-usb-device-mode-config.sh`
  - `enable_rndis=1` (RNDIS = Windows/Linux USB Ethernet)
  - `enable_acm=0` (USB serial for SDK Manager flashing — disabled: causes Windows loop-enumerate)
  - `enable_ums=0` (16 MB FAT image for SDK Manager — disabled: same reason)
  - `enable_ecm=0` (CDC-ECM/NCM — disabled: NCM SET_INTERFACE caused carrier flaps on Windows)
- `/opt/nvidia/l4t-usb-device-mode/nv-l4t-usb-device-mode-start.sh`
  - `bcdDevice` set to `0x0003` (forces Windows to flush stale composite-device driver cache)

**Why RNDIS-only:** NVIDIA's default 4-function composite gadget (ACM + UMS + ECM + RNDIS) causes Windows to issue SETUP requests to USB serial and mass-storage interfaces it can't handle, triggering `tegra-xudc: setup request failed: -22` and a lost-carrier / gained-carrier oscillation loop. RNDIS-only eliminates this entirely.

**Network topology over USB:**
- Jetson IP: `192.168.55.1`
- Client IP (DHCP): `192.168.55.100`
- Subnet: `192.168.55.0/24`, no default gateway advertised (client keeps its existing internet connection)

**Platform support:**
- Windows 10/11: RNDIS native, no drivers needed
- Linux: RNDIS native
- macOS: requires [HoRNDIS](https://github.com/jwise/HoRNDIS) — no built-in RNDIS support

**USB selective suspend:** Windows suspends RNDIS adapters after ~2 s of idle, causing carrier flaps in Jetson logs. Functionally benign but visible. User-side fix: Device Manager → RNDIS adapter → Power Management → uncheck "Allow the computer to turn off this device."

**Checking USB status:** `jetson-infer usb-status`

---

### dufs File Server

A pre-built Rust binary (`~/bin/dufs`) serving `~/shared/` over HTTP and WebDAV.

**Port:** `30140`  
**Service:** `dufs.service` (systemd user unit)  
**Shared directory:** `~/shared/` — flat; users drop files here directly and create their own subdirectories as needed.

**pi integration:**
- `list_shared_files` tool: lists `~/shared/` with file sizes and directory markers
- `/files` command: shows `~/shared/` contents

**Access:**
- Browser (any platform): `http://<jetson-ip>:30140`
- Mac native mount: Finder → Go → Connect to Server → `http://<jetson-ip>:30140`
- Windows native mount: Map Network Drive → `\\<jetson-ip>@30140\DavWWWRoot`

**Binary:** `aarch64-unknown-linux-musl` static binary — no runtime dependencies, no build step.  
**Version:** pinned in `install-local.sh` as `DUFS_VERSION`; auto-updates when version string changes on upgrade.  
**Auth:** none (LAN-trust model, matches pi-web).

---

### Install Scripts

Both scripts are idempotent and safe to re-run as `--upgrade`.

**`scripts/install-local.sh`** — runs on the Jetson:
- Clones repo to `~/Token-Jet` if not present; `git pull` on `--upgrade`
- Installs missing apt packages (cmake, build-essential, cuda-nvcc, libcublas-dev, python-venv)
- Detects CUDA via `/usr/local/cuda*/bin/nvcc`; requires CUDA for CUDA_FLAGS
- Performance mode: `nvpmodel -m 0` (MAXN); installs `jetson-clocks-boot.service`
- Builds `~/llama.cpp` (mainline) with `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=87`; caps at 3 parallel jobs (memory constraint); cleans `.o`/`.a` after build
- Installs TUI venv at `~/.local/share/token-jet/`
- Installs Node.js 22 via NodeSource if needed
- Installs pi + extensions via `pi install` + npm
- Deploys `jetson-provider.ts` and `wifi-manager.ts` to `~/.pi/agent/extensions/`
- Writes sudoers rule for nmcli
- Patches NVIDIA USB config (RNDIS-only, bcdDevice 0x0003)
- Writes `~/.pi/agent/auth.json` with `jetson-local` key
- Enables `jetson-infer` and `pi-web` systemd user services

**`scripts/install.sh`** — runs on the workstation, SSHs to Jetson:
- Uses `sshpass` when available; falls back to key-based SSH (`--no-pass`)
- `_pipe_to <remote-path>`: pipes stdin to remote file via `cat > <path>`
- Deploys TUI source via `tar | ssh | tar`
- Builds PrismML fork (`~/llama.cpp-prism`, branch `pr/q2_0-cuda`) in addition to mainline; skip with `--no-prism-build`
- Same USB gadget patch, sudoers, and auth.json steps as install-local.sh
- Creates `~/bin/token-jet-tui` workstation launcher (embeds password when using sshpass; mode 700)
- `--self-update` mode: `git pull` on workstation repo then re-execs as `--upgrade`

**Sudoers temp-file pattern** (required in install.sh to avoid stdin conflict with `sudo -S`):
```bash
TMPF=$(mktemp)
printf '%s\n' "$RULE" > "$TMPF"
echo '${JETSON_PASS}' | sudo -S cp "$TMPF" "$FILE"
echo '${JETSON_PASS}' | sudo -S chmod 440 "$FILE"
rm -f "$TMPF"
```

**Shell escaping in `install.sh` `_ssh "..."` blocks:**
- `${JETSON_PASS}` → expanded by local shell (intentional — injects password)
- `${JETSON_USER}` → expanded by local shell (intentional — injects username)
- `\$VAR` → escaped; expanded by the remote shell
- `\$(...)` → escaped; executed by the remote shell
- Single quotes inside double-quoted strings are literal chars — used to shell-quote values on the remote (e.g., `echo '${JETSON_PASS}' | sudo -S` becomes `echo '101abn' | sudo -S` on the remote)

---

## Models

| Model | File pattern | Size | Context | Speed | GPU binary | Agent-capable |
|-------|-------------|------|---------|-------|-----------|--------------|
| Qwen3.5-4B-Coder ⭐ | `qwen3.5-4B-super-coder.Q4_0.gguf` | 2.5 GB | 32K | 20 t/s | mainline llama.cpp | Yes |
| Ternary-Bonsai-8B | `*bonsai*` | 2.0 GB | 16–20K | 8 t/s | PrismML fork | Yes |
| MiniCPM5-1B | `*minicpm*` | 1.1 GB | 32K | 31 t/s | mainline llama.cpp | No |

- Inference API endpoint: `http://<jetson-ip>:1234/v1` (OpenAI-compatible)
- All models run with `--reasoning auto` — thinking tokens surfaced via `reasoning_content`
- Bonsai routing: any `.gguf` with `bonsai` in the filename → PrismML binary; otherwise mainline

---

## Key Runtime Paths (on Jetson)

| Path | Purpose |
|------|---------|
| `~/Token-Jet/` | Repo clone |
| `~/bin/jetson-infer` | Inference server CLI (symlink in install-local; copy in install.sh) |
| `~/.local/share/token-jet/venv/` | TUI Python venv |
| `~/.local/bin/token-jet` | TUI launcher script |
| `~/.config/token-jet/config.toml` | Main config |
| `~/models/` | GGUF model files |
| `~/llama.cpp/build/bin/llama-server` | Mainline llama-server binary |
| `~/llama.cpp-prism/build/bin/llama-server` | PrismML fork binary (Bonsai models) |
| `~/.npm-global/bin/pi` | pi coding agent |
| `~/.pi/agent/extensions/jetson-provider.ts` | Jetson pi provider extension |
| `~/.pi/agent/extensions/wifi-manager.ts` | Wi-Fi pi extension |
| `~/Token-Jet/pi/wifi-manager/wifi.py` | nmcli backend for wifi-manager.ts |
| `~/.pi/agent/settings.json` | pi settings (preserved on upgrade) |
| `~/.pi/agent/auth.json` | pi API keys (merged on install, preserved on upgrade) |
| `~/.config/systemd/user/jetson-infer.service` | Inference server auto-start |
| `~/.config/systemd/user/pi-web.service` | pi-web auto-start |
| `~/.config/systemd/user/dufs.service` | dufs file server auto-start |
| `~/bin/dufs` | dufs binary (aarch64 musl static) |
| `~/shared/` | file drop zone — users place files here for pi; create subdirs as needed |
| `/etc/systemd/system/jetson-clocks-boot.service` | Clock lock at boot |
| `/etc/sudoers.d/token-jet-wifi` | nmcli NOPASSWD rule |
| `/opt/nvidia/l4t-usb-device-mode/nv-l4t-usb-device-mode-config.sh` | USB gadget config |
| `/opt/nvidia/l4t-usb-device-mode/nv-l4t-usb-device-mode-start.sh` | USB gadget start script |
| `/tmp/jetson-infer.log` | Inference server log |
| `/tmp/jetson-infer.pid` | Inference server PID |
| `/tmp/jetson-watchdog.log` | Watchdog log |

---

## Known Constraints and Gotchas

- **Build job cap:** `install-local.sh` caps CMake at 3 parallel jobs. Each `nvcc` invocation uses ~1.5 GB; 4 jobs × 1.5 GB = 6 GB which exhausts the 8 GB Jetson. Do not raise without testing.
- **PrismML fork not built by install-local.sh:** Only `install.sh` (workstation path) builds the PrismML fork. The local installer skips it to keep install time manageable on fresh machines. Users who install locally and want Bonsai GPU inference need to build it manually.
- **CUDA path:** JetPack puts nvcc at `/usr/local/cuda-X.Y/bin/nvcc`, not in PATH by default. `install-local.sh` adds it to `~/.bashrc` and exports it during the install session so CMake finds it.
- **`pi install` is interactive:** Uses `yes |` to pipe `y` to its prompts. The `pi` binary must be on PATH when this runs — the npm prefix must already be set.
- **`nmcli -m multiline` parsing:** Using `line.partition(":")` is intentional — SSIDs can contain colons; `split(":", 1)` or `split(":")` would give incorrect results for the key. The current code correctly handles all SSID characters.
- **pi auth.json merging:** The install scripts merge rather than overwrite `~/.pi/agent/auth.json` so existing cloud provider tokens (OpenAI, Anthropic, etc.) survive an upgrade.
- **pi settings.json preserved on upgrade:** `~/.pi/agent/settings.json` is NOT overwritten on upgrade — user customizations are preserved. It is only written on fresh install if missing.
- **Token-jet-tui workstation launcher security:** The launcher generated by `install.sh` embeds the SSH password in plaintext and is chmod 700 (user-only read). Treat it accordingly.
- **`nv-l4t-usb-device-mode` restart:** The USB gadget service restart at the end of the USB config patch takes ~2 seconds and briefly drops any active USB connection. Expected behavior.
- **USB oscillation root cause documented:** See the USB Device Mode section above. The tegra-xudc EINVAL loop was caused by NVIDIA's composite gadget — do not re-enable `enable_acm`, `enable_ums`, or `enable_ecm` without testing on Windows first.
- **bcdDevice:** Currently `0x0003` in `nv-l4t-usb-device-mode-start.sh`. If the USB gadget config changes significantly again, bump this to force Windows to re-enumerate.
- **`tomli` / `tomllib`:** `jetson-infer` uses stdlib `tomllib` (Python 3.11+) or `tomli` backport (Python 3.10). Has an inline fallback parser for simple `key = "value"` lines if neither is available.

---

## Use Cases

1. **Local AI chat** — private, no-internet, no token cost inference via TUI or pi
2. **Coding agent sessions** — pi + jetson-provider.ts gives a full coding agent with web search, URL fetching, and model management, running entirely on-device
3. **Browser-based UI** — pi-web at port 30141 for laptop/tablet access without SSH
4. **Air-gapped operation** — disable Wi-Fi via `/wifi`, plug USB-C cable, full functionality at `192.168.55.1` with no network
5. **USB-tethered workstation AI** — workstation gets a DHCP lease over USB; infer at `192.168.55.1:1234/v1` from any OpenAI-compatible client
6. **Embedded/IoT AI backend** — headless `jetson-infer start` via systemd; query the OpenAI-compatible API from any other device on the network
7. **Evaluation harness** — `eval/coding-eval.py` and `eval/it-eval.py` for reproducible model benchmarking on-device
