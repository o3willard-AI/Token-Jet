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
- **OpenAI-compatible:** Standard `/v1/chat/completions` and `/v1/models` endpoints
- **Auto-start:** Systemd service for boot-time startup with watchdog recovery

## Recommended Models

After evaluating ten models across coding tasks, IT troubleshooting scenarios, and real-world agent usage on the Jetson Orin Nano 8GB, we recommend these three. The assessments below reflect our observations as of July 2026 — they represent our best effort, not a definitive ranking.

| Model | Size | Speed | Max Context | Best For |
|-------|------|:-----:|:-----------:|----------|
| **MiniCPM5-1B** | 1.1 GB | 31 t/s | 16K | Interactive use, low latency, generous context |
| **Qwen3.5-4B-Coder** | 2.5 GB | 20 t/s | 8K | Solid all-rounder, good speed at moderate context |
| **Ternary-Bonsai-8B** | 2.0 GB | 8 t/s | 16K | Complex code generation, highest accuracy |

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

## Requirements

- NVIDIA Jetson Orin Nano (8GB) or any Jetson with unified memory
- Ubuntu 24.04 (JetPack 39.2+)
- llama.cpp with CUDA support (included in deploy script)

## Commands

```bash
jetson-infer start                    # Start recommended model (MiniCPM5-1B)
jetson-infer start --model 8B         # Start Bonsai-8B (highest accuracy)
jetson-infer start --model qwen3.5    # Start Qwen3.5-4B-Coder
jetson-infer status                   # Show running model, memory, health
jetson-infer stop                     # Stop the server
jetson-infer models                   # List available models with speeds + max context
jetson-infer install                  # Install systemd service (auto-start on boot)
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
