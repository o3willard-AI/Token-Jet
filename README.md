# Token-Jet

**Turn your NVIDIA Jetson into a local inference server in one command.**

Token-Jet wraps [llama.cpp](https://github.com/ggml-org/llama.cpp) into a smart inference server that automatically selects the optimal model and context window for your Jetson's available memory. Exposes an OpenAI-compatible API that any agent (OpenCode, PI, Claude Code, etc.) can use.

## Quick Start

### On the Jetson (one-time setup)

```bash
# Clone and deploy
git clone https://github.com/o3willard-AI/Token-Jet.git
cd Token-Jet
./scripts/deploy.sh <jetson-ip>

# SSH in and start serving
ssh jetson
jetson-infer start
```

### On your workstation (one-time setup)

```bash
# Download the connect script
curl -O https://raw.githubusercontent.com/o3willard-AI/Token-Jet/main/token-jet-connect
chmod +x token-jet-connect

# Run it — installs OpenCode, configures the tunnel, sets up launchers
./token-jet-connect <jetson-ip>
```

### Daily use

```bash
# Launch OpenCode TUI (auto-connects to Jetson)
token-jet-opencode

# In the TUI: press /connect → select LMStudio
# Model name doesn't matter — the Jetson uses its loaded model

# CLI one-shot:
token-jet-opencode run --model lmstudio/openai/gpt-oss-20b "your prompt"
```

### Other agents

Any OpenAI-compatible client can connect directly:

```bash
# PI
api_base: http://<jetson-ip>:1234/v1

# curl
curl http://<jetson-ip>:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hello"}],"max_tokens":50}'
```

## Features

- **Auto-context:** Calculates the largest context window that fits in available unified memory
- **Model selection:** Ships with pre-configured profiles for Bonsai ternary models (4B, 8B, 27B) and Gemma-3-1B
- **OpenAI-compatible:** Standard `/v1/chat/completions` and `/v1/models` endpoints
- **Auto-start:** Systemd service for boot-time startup
- **Evaluated:** All models benchmarked on coding (5-task) and IT troubleshooting (5-scenario) tasks

## Models

| Model | Coding | IT Support | Speed | Best For |
|-------|:------:|:----------:|:-----:|----------|
| **Ternary-Bonsai-8B** | 4/5 | 2/5 | 8.4 t/s | Best overall. Code generation + architecture |
| Ternary-Bonsai-4B | 3/5 | 1/5 | 16.3 t/s | Interactive use, low latency |
| Gemma-3-1B | 2/5 | 1/5 | 15.6 t/s | Fastest, but unreliable for complex tasks |
| Bonsai-27B | 0/5* | N/A | 3.2 t/s | Experimental only — unstable |

*\* 27B loads and benchmarks but crashes on real inference. See docs/bonsai-27b.md.*

## Requirements

- NVIDIA Jetson Orin Nano (8GB) or any Jetson with unified memory
- Ubuntu 24.04 (JetPack 39.2+)
- llama.cpp with CUDA support (included in deploy script)

## Commands

```bash
jetson-infer start              # Start best model (8B) with auto context
jetson-infer start --model 4B   # Start 4B (faster, lower quality)
jetson-infer status             # Show running model, memory, health
jetson-infer stop               # Stop the server
jetson-infer models             # List models with scores + max context
jetson-infer install            # Install systemd service (auto-start on boot)
```

## How It Works

On startup, `jetson-infer`:

1. Reads available memory from `/proc/meminfo`
2. Calculates max context: `(free - model_size - 512MB_safety) × 0.85 ÷ 144KB_per_token`
3. Starts llama-server with the optimal `--ctx-size` and `--n-gpu-layers 99`
4. Health-checks until ready, then reports the endpoint

The per-token cost (144 KB) was empirically measured from Jetson Orin — it's ~4.4× the theoretical minimum due to CUDA alignment overhead.

## Project Structure

```
Token-Jet/
├── jetson-infer              # The inference server utility
├── jetson-infer.service      # Systemd service file
├── token-jet-connect         # One-command OpenCode + tunnel setup for workstations
├── docs/
│   ├── model-results.md      # Full eval results (coding + IT troubleshooting)
│   ├── bonsai-27b.md         # 27B dead-end investigation
│   ├── hardware-setup.md     # Jetson Orin setup from scratch
│   └── resilience.md         # Watchdog, auto-recovery, memory monitoring
├── eval/
│   ├── coding-eval.py        # 5-task coding benchmark
│   └── it-eval.py            # 5-scenario IT troubleshooting test
└── scripts/
    └── deploy.sh             # One-command deploy to Jetson
```

## License

MIT — see [LICENSE](LICENSE).
