# Resilience & Watchdog

Token-Jet includes a built-in watchdog that monitors the inference server and auto-recovers from crashes and memory exhaustion.

## Why This Exists

During testing, the llama-server process exhibited **silent crashes** — the process dies with no OOM killer log, no segfault, no CUDA error. Likely causes:

- **Memory pressure**: Jetson Orin Nano has no swap. When the 7.3 GiB unified memory fills (model + KV cache + CUDA context + prompt cache), the kernel kills the process silently.
- **PrismML fork instability**: The llama.cpp PrismML fork (required for Bonsai ternary/1-bit models) may have memory leaks or context corruption under sustained use.
- **Prompt accumulation**: OpenCode sends 7K+ token system prompts. Over many requests, the prompt cache grows and fragments available memory.

The watchdog ensures the server stays available even when these failures occur.

## Architecture

```
┌─────────────────────────────────────────┐
│               Watchdog                  │
│                                         │
│  Every 10s:  GET /health               │
│  Every 30s:  check /proc/meminfo        │
│                                         │
│  On failure:                            │
│    1. SIGTERM → 5s grace               │
│    2. SIGKILL if still alive            │
│    3. pkill -9 fallback                 │
│    4. Wait for memory to free (≤ 60s)   │
│    5. Restart llama-server              │
│    6. Reset restart counter on success  │
│                                         │
│  After 10 consecutive failures:         │
│    → Logs error and exits              │
│    → Systemd Restart=on-failure         │
│      picks it up after 10s             │
└─────────────────────────────────────────┘
```

## Configuration

All thresholds are configurable at the top of `jetson-infer`:

| Constant | Default | Description |
|----------|---------|-------------|
| `HEALTH_CHECK_INTERVAL` | 10s | How often to ping `/health` |
| `MEMORY_CHECK_INTERVAL` | 30s | How often to check free memory |
| `MEMORY_RESTART_THRESHOLD_MB` | 200 | Restart if free memory drops below this |
| `MAX_RESTARTS` | 10 | Consecutive failures before watchdog exits |

## Usage

### Manual

```bash
jetson-infer start --watchdog
```

### Systemd (production)

```bash
jetson-infer install
systemctl --user start jetson-infer
```

The systemd service file uses `--watchdog` by default. Systemd provides a second layer of recovery: if the watchdog itself crashes, `Restart=on-failure` restarts it after 10 seconds.

### Logs

| File | Contents |
|------|----------|
| `/tmp/jetson-infer.log` | llama-server output |
| `/tmp/jetson-watchdog.log` | Watchdog events (health failures, restarts, memory warnings) |
| `/tmp/jetson-infer-service.log` | Systemd service output (when running as a service) |

## What Happens During a Crash

1. Watchdog detects `/health` is unreachable (or memory < 200 MB)
2. Logs: `[timestamp] SERVER UNHEALTHY (restart 1/10)`
3. Kills the old llama-server process
4. Waits for memory to recover (up to 60s)
5. Logs: `[timestamp] Restarting server...`
6. Calls `jetson-infer start` internally
7. On success: `[timestamp] Server recovered` — restart counter resets to 0
8. Client tunnel/user may see a brief interruption (~30-60s) while the server reloads

## Testing Resilience

To verify the watchdog works:

```bash
# Start with watchdog
jetson-infer start --watchdog &

# Kill the server
kill $(pgrep llama-server)

# Watch recovery
tail -f /tmp/jetson-watchdog.log
```

Expected output:
```
[2026-07-16 13:03:31] Watchdog started
[2026-07-16 13:10:05] SERVER UNHEALTHY (restart 1/10)
[2026-07-16 13:10:15] Restarting server...
[2026-07-16 13:10:47] Server recovered
```

## Memory Budget Reference

For the Bonsai-8B model on Jetson Orin Nano 8GB:

| Component | Size |
|-----------|------|
| Model (Q2_0) | 2.03 GB |
| KV Cache (16K ctx) | ~512 MB |
| CUDA context | ~500 MB |
| System overhead | ~800 MB |
| **Total** | **~3.8 GB** |
| **Remaining free** | **~3.5 GB** |

The watchdog triggers at 200 MB free — well before the kernel OOM killer would act. If memory consistently trends toward this threshold, the model or context size should be reduced.
