# Token-Jet

**Turn your NVIDIA Jetson into a local inference server in one command.**

Token-Jet wraps [llama.cpp](https://github.com/ggml-org/llama.cpp) into a smart inference server that automatically selects the optimal model and context window for your Jetson's available memory. Exposes an OpenAI-compatible API that any agent (OpenCode, PI, Claude Code, etc.) can use.

## Quick Start

```bash
# 1. Deploy to your Jetson
./scripts/deploy.sh 192.168.1.100

# 2. SSH in and start
ssh jetson
jetson-infer start

# 3. Point your agent at it
# OpenCode:  opencode --api-base http://192.168.1.100:1234/v1
# PI:        api_base: http://192.168.1.100:1234/v1
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
├── docs/
│   ├── model-results.md      # Full eval results (coding + IT troubleshooting)
│   ├── bonsai-27b.md         # 27B dead-end investigation
│   └── hardware-setup.md     # Jetson Orin setup from scratch
├── eval/
│   ├── coding-eval.py        # 5-task coding benchmark
│   └── it-eval.py            # 5-scenario IT troubleshooting test
└── scripts/
    └── deploy.sh             # One-command deploy to Jetson
```

## License

MIT — see [LICENSE](LICENSE).
