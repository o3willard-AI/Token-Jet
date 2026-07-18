# <img src="images/token-jet-logo-v1.jpg" alt="Token-Jet" width="48" align="left"> Token-Jet

**Run a local LLM on your NVIDIA Jetson and control it from your workstation.**

Token-Jet turns a Jetson Orin Nano into a self-contained local AI server. One command handles everything: it builds the inference engine from source, installs a terminal dashboard, and has you chatting with a model in under 30 minutes — no cloud, no subscriptions, no GPU server required.

---

## Prerequisites

### Hardware

- **NVIDIA Jetson Orin Nano 8 GB** (4 GB may work but is not tested)
- A network connection during install — the script clones repos and the TUI downloads models from Hugging Face

### Software — what JetPack gives you out of the box

Token-Jet is designed to work with a **stock JetPack 6.x image** (Ubuntu 22.04). Everything below comes pre-installed:

| What | Why it's needed |
|------|----------------|
| Ubuntu 22.04 | Base OS |
| CUDA 12.x + cuDNN | GPU inference via llama.cpp |
| Python 3.10 | TUI and jetson-infer utility |
| `curl`, `git` | Bootstrap and source cloning |

> **Haven't flashed JetPack yet?** See [`docs/hardware-setup.md`](docs/hardware-setup.md) for a step-by-step guide from unboxed device to ready-to-install.

### Software — what the installer adds

The install script handles all of this automatically — you don't need to do it by hand:

| What | Where it lands |
|------|---------------|
| `cmake`, `build-essential` | System packages (via `apt`) |
| llama.cpp (standard build) | `~/llama.cpp/` |
| llama.cpp-prism fork | `~/llama.cpp-prism/` (needed for Ternary-Bonsai-8B) |
| Token-Jet TUI | `~/.local/share/token-jet/` (isolated Python venv) |
| `jetson-infer` utility | `~/bin/jetson-infer` |
| `token-jet` launcher | `~/.local/bin/token-jet` |
| Default config | `~/.config/token-jet/config.toml` |
| Systemd service | Auto-starts inference server on boot |

---

## Install

### Option 1 — On the Jetson directly (recommended)

Log into the Jetson (directly at a keyboard, or over SSH from any machine) and run:

```bash
curl -sL https://raw.githubusercontent.com/o3willard-AI/Token-Jet/main/scripts/install-local.sh | bash
```

**What happens next** (the script runs unattended — expect 20–30 minutes total):

1. Clones this repo to `~/Token-Jet`
2. Installs `cmake` and `build-essential` if missing
3. Detects your CUDA version and architecture automatically
4. Clones and builds `llama.cpp` from source *(~10–15 min)*
5. Clones and builds the `llama.cpp-prism` fork from source *(~10–15 min)*
6. Installs the TUI into an isolated Python venv
7. Deploys `jetson-infer` and creates the `token-jet` launcher
8. Writes a default config and enables the systemd service

When it finishes:

```bash
source ~/.bashrc
token-jet
```

### Option 2 — From a Mac, Linux, or Windows (WSL) workstation

If you'd rather drive the install remotely, clone the repo on your **workstation** and point the installer at your Jetson's IP address:

```bash
git clone https://github.com/o3willard-AI/Token-Jet.git
cd Token-Jet
./scripts/install.sh <jetson-ip>
```

The installer SSHs into the Jetson, runs the same deployment steps remotely, then creates a `token-jet-tui` launcher on your workstation that opens the TUI over SSH.

**Options:**

```
./scripts/install.sh <jetson-ip> [options]

  --user USER      Jetson SSH username (default: ubuntu)
  --pass PASS      SSH password (prompted if omitted)
  --no-pass        Use key-based SSH auth instead
  --upgrade        Re-deploy source files; preserve config and models
  --self-update    Pull latest from GitHub, then upgrade automatically
  --uninstall      Remove Token-Jet from the Jetson
```

**Tip — skip the password prompt with SSH keys:**

```bash
ssh-copy-id ubuntu@<jetson-ip>
./scripts/install.sh <jetson-ip> --no-pass
```

---

## First Run

1. **Launch the TUI:**

   ```bash
   token-jet        # if installed on the Jetson directly
   token-jet-tui    # if installed from a workstation
   ```

2. **Download a model** — press `Ctrl+D` to open the model browser.  
   Select any model from the curated list and press `Enter` to see its GGUF files, then `Enter` again to start downloading. MiniCPM5-1B downloads in a few minutes and is the best starting point.

3. **Load the model** — press `Ctrl+S`, select the model you downloaded, press `Enter`.  
   A status line shows the server starting up. Takes 5–15 seconds.

4. **Chat** — type in the input box at the bottom and press `Enter`.  
   Thinking models (like MiniCPM5-1B) display their reasoning process before the answer.

---

## TUI Keyboard Reference

| Key | Action |
|-----|--------|
| `Ctrl+D` | Download a model (model browser) |
| `Ctrl+S` | Switch the active model |
| `Ctrl+X` | Remove a downloaded model |
| `Ctrl+R` | Reset performance counters |
| `Ctrl+P` | Palette & Settings (theme, screenshot) |
| `Ctrl+Q` | Quit |
| `Enter` | Send chat message |
| `Ctrl+V` / `Shift+Insert` | Paste clipboard into chat |
| `Esc` | Close any open dialog |

---

## Recommended Models

After evaluating ten models across coding tasks, IT troubleshooting scenarios, and real-world agent usage on the Jetson Orin Nano 8 GB, we recommend these three. The assessments below reflect our observations as of July 2026.

| Model | Size | Speed | Max Context | Best For |
|-------|------|:-----:|:-----------:|----------|
| **MiniCPM5-1B** | 1.1 GB | 31 t/s | 16K | Interactive use, low latency, generous context |
| **Qwen3.5-4B-Coder** | 2.5 GB | 20 t/s | 8K | Solid all-rounder, good speed at moderate context |
| **Ternary-Bonsai-8B** | 2.0 GB | 8 t/s | 16K | Complex code generation, highest accuracy |

All three are available directly from the TUI model browser (`Ctrl+D`) under the **Verified** tag.

### MiniCPM5-1B (Q8_0)

The speed champion — over 30 tokens per second with a generous 16K context window at just 1.1 GB. Claude-distilled, so it inherits strong instruction-following and reasoning patterns. Ideal for interactive agents where latency matters.

### Qwen3.5-4B-Coder (Q4_0)

The pragmatic middle choice. More than twice as fast as the Bonsai-8B with solid code generation ability. The tighter 8K context window is the main trade-off — adequate for most coding tasks but limiting for very long files.

### Ternary-Bonsai-8B (Q2_0)

The accuracy leader. At 1.58-bit ternary quantization, it consistently handles complex coding challenges that trip up the others. The cost is speed — 8 t/s. Best for offline or batch work where quality matters more than responsiveness. Requires the `llama.cpp-prism` build (installed automatically).

### Trade-offs at a glance

- **Speed:** MiniCPM5 (31 t/s) ≫ Qwen3.5 (20 t/s) ≫ Bonsai-8B (8 t/s)
- **Context:** MiniCPM5 = Bonsai-8B (16K) > Qwen3.5 (8K)
- **Code quality:** Bonsai-8B > Qwen3.5 ≈ MiniCPM5
- **Disk footprint:** MiniCPM5 (1.1 GB) < Bonsai-8B (2.0 GB) < Qwen3.5 (2.5 GB)

For most users, MiniCPM5-1B is the best starting point. Switch to Bonsai-8B when you need maximum accuracy on complex code generation.

---

## Update / Uninstall

**If installed on the Jetson directly:**

```bash
# Update TUI and jetson-infer (preserves config, models, and llama.cpp builds)
~/Token-Jet/scripts/install-local.sh --upgrade

# Remove Token-Jet (models in ~/models/ and config are not deleted)
~/Token-Jet/scripts/install-local.sh --uninstall
```

**If installed from a workstation:**

```bash
# Pull latest and upgrade
./scripts/install.sh <jetson-ip> --self-update

# Remove Token-Jet from the Jetson
./scripts/install.sh <jetson-ip> --uninstall
```

---

## OpenAI-Compatible API

Once a model is running, any OpenAI-compatible client can connect directly:

```bash
curl http://<jetson-ip>:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"local","messages":[{"role":"user","content":"hello"}],"max_tokens":256}'
```

Endpoint: `http://<jetson-ip>:1234/v1`

---

## jetson-infer CLI (on the Jetson)

```bash
jetson-infer start                                  # Start the default model
jetson-infer start --model ~/models/foo.gguf        # Start any model by full path
jetson-infer status                                 # Show running model, memory, health
jetson-infer stop                                   # Stop the server
jetson-infer models                                 # List downloaded models + estimated context
jetson-infer install                                # Install systemd service (auto-start on boot)
```

The **default model** is whichever path is set as `default_model` in `~/.config/token-jet/config.toml`. If that's empty, `jetson-infer start` uses the first `.gguf` file found in `model_dir` (alphabetically). Set it once and forget it:

```bash
# In ~/.config/token-jet/config.toml
default_model = "/home/ubuntu/models/MiniCPM5-1B-Claude-Opus-Fable5-Thinking-Q8_0.gguf"
```

---

## Project Structure

```
Token-Jet/
├── jetson-infer              # Inference server utility (runs on the Jetson)
├── jetson-infer.service      # Systemd service file
├── tui/                      # Terminal dashboard (Textual)
│   └── token_jet_tui/
├── scripts/
│   ├── install-local.sh      # Install directly on the Jetson (recommended)
│   └── install.sh            # Install remotely from a workstation
├── eval/
│   ├── coding-eval.py        # 5-task coding benchmark
│   └── it-eval.py            # 5-scenario IT troubleshooting test
└── docs/
    ├── hardware-setup.md     # Jetson Orin setup from scratch
    ├── model-results.md      # Full eval results
    └── resilience.md         # Watchdog, auto-recovery, memory monitoring
```

---

## License

MIT — see [LICENSE](LICENSE).
