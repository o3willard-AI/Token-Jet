# <img src="images/token-jet-logo-v1.jpg" alt="Token-Jet" width="48" align="left"> Token-Jet

**Run a local LLM on your NVIDIA Jetson and control it from your workstation.**

Token-Jet deploys [llama.cpp](https://github.com/ggml-org/llama.cpp) to your Jetson Orin Nano and gives you a full terminal dashboard (TUI) to download models, switch between them, chat, and monitor performance — all from one keyboard-driven interface.

---

## Requirements

- **Jetson:** NVIDIA Jetson Orin Nano 8 GB, Ubuntu 22.04 or 24.04 (JetPack 6.x), llama.cpp built with CUDA
- **curl and git** are included in the default JetPack image; if for some reason they are missing: `sudo apt install -y curl git`

---

## Install

### Option 1 — On the Jetson directly (recommended)

Log into the Jetson (directly or over SSH) and run the one-liner:

```bash
curl -sL https://raw.githubusercontent.com/o3willard-AI/Token-Jet/main/scripts/install-local.sh | bash
```

This clones the repo to `~/Token-Jet`, installs the TUI into a Python venv, deploys `jetson-infer`, and creates a `token-jet` launcher.  After it finishes:

```bash
source ~/.bashrc
token-jet
```

### Option 2 — From a Mac, Linux, or Windows (WSL) workstation

Clone the repo on your **workstation**, then point the installer at your Jetson's IP:

```bash
git clone https://github.com/o3willard-AI/Token-Jet.git
cd Token-Jet
./scripts/install.sh <jetson-ip>
```

The installer SSHs into the Jetson to deploy everything remotely, then creates a local `token-jet-tui` launcher on your workstation that opens the TUI over SSH.

**Supported platforms for the workstation installer:**
- macOS
- Linux
- Windows with WSL 2

**Options:**

```
./scripts/install.sh <jetson-ip> [options]

  --user USER      Jetson SSH username (default: ubuntu)
  --pass PASS      SSH password (prompted if omitted)
  --no-pass        Use key-based SSH auth instead of a password
  --upgrade        Re-deploy source files; preserves user config
  --self-update    Pull latest from GitHub, then upgrade automatically
  --uninstall      Remove TUI, jetson-infer, and systemd service from Jetson
```

**SSH key setup (skip the password prompt every time):**

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
   Select a model from the curated list and press `Enter` to browse its GGUF files, then `Enter` again to start downloading. MiniCPM5-1B is the fastest starter; Bonsai-8B is the highest quality.

3. **Switch to the downloaded model** — press `Ctrl+S`, select the model, press `Enter`.  
   The dashboard stops any running server and starts the new one. A status line shows progress.

4. **Chat** — type in the input box at the bottom and press `Enter`.  
   Reasoning models (like MiniCPM5-1B) show a collapsible "Reasoning" section before the answer.

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

The speed champion — over 30 tokens per second with a generous 16K context window at just 1.1 GB. Claude-distilled, so it inherits strong instruction-following and reasoning patterns. Ideal for interactive agents where latency matters. Pairs well with the full 16K context for long conversations or document processing.

### Qwen3.5-4B-Coder (Q4_0)

The pragmatic middle choice. More than twice as fast as the Bonsai-8B with solid code generation ability. The tighter 8K context window is the trade-off — adequate for most coding tasks but limiting for very long files. A good choice when you want decent accuracy without waiting.

### Ternary-Bonsai-8B (Q2_0)

The accuracy leader. At 1.58-bit ternary quantization, this model consistently handles the most complex coding challenges that trip up the others. The cost is speed — at 8 tokens per second, it's the slowest of the three. Best for offline or batch code generation where quality matters more than responsiveness.

### Trade-offs at a glance

- **Speed:** MiniCPM5 (31 t/s) ≫ Qwen3.5 (20 t/s) ≫ Bonsai-8B (8 t/s)
- **Context:** MiniCPM5 = Bonsai-8B (16K) > Qwen3.5 (8K)
- **Code quality:** Bonsai-8B > Qwen3.5 ≈ MiniCPM5
- **Disk footprint:** MiniCPM5 (1.1 GB) < Bonsai-8B (2.0 GB) < Qwen3.5 (2.5 GB)

For most users, MiniCPM5-1B is the best starting point — fast, generous context, and competent across a range of tasks. Switch to Bonsai-8B when you need the extra accuracy for complex code generation.

---

## OpenAI-Compatible API

Any OpenAI-compatible client can connect to the Jetson directly:

```bash
# Endpoint
http://<jetson-ip>:1234/v1

# Example with curl
curl http://<jetson-ip>:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"local","messages":[{"role":"user","content":"hello"}],"max_tokens":256}'
```

---

## jetson-infer CLI (on the Jetson)

```bash
jetson-infer start                    # Start default model (MiniCPM5-1B)
jetson-infer start --model 8B         # Start Bonsai-8B (highest accuracy)
jetson-infer start --model qwen3.5    # Start Qwen3.5-4B-Coder
jetson-infer status                   # Show running model, memory, health
jetson-infer stop                     # Stop the server
jetson-infer models                   # List available models with speeds + max context
jetson-infer install                  # Install systemd service (auto-start on boot)
```

---

## Update / Uninstall

**If installed on the Jetson directly:**

```bash
# Update (pulls latest from GitHub, preserves config and models)
~/Token-Jet/scripts/install-local.sh --upgrade

# Remove (models in ~/models/ and config are not deleted)
~/Token-Jet/scripts/install-local.sh --uninstall
```

**If installed from a workstation:**

```bash
# Pull latest and upgrade (preserves downloaded models and config)
./scripts/install.sh <jetson-ip> --self-update

# Remove everything from the Jetson
./scripts/install.sh <jetson-ip> --uninstall
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
    ├── model-results.md      # Full eval results
    ├── hardware-setup.md     # Jetson Orin setup from scratch
    └── resilience.md         # Watchdog, auto-recovery, memory monitoring
```

---

## License

MIT — see [LICENSE](LICENSE).
