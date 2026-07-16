# Bonsai-27B Investigation (July 2026 — Dead End)

## Summary

**Verdict: Not viable for coding or troubleshooting on Jetson Orin Nano.**

The Bonsai-27B-Q1_0 model (PrismML, 1-bit, Qwen3.5 hybrid architecture) was
evaluated alongside the 4B and 8B ternary models. Despite promising benchmark
numbers, real inference is unstable.

## Discovery Timeline

### 1. Initial benchmark (ngl=50)
- `llama-bench` showed 1.90 t/s with half layers on GPU
- Model loaded and produced the bench result
- Assumption: ngl=99 would be faster — full GPU offload

### 2. Server loading (ngl=99)
- Server reaches health=ok after ~520 seconds (slow eMMC: 3.53 GB at ~8 MB/s)
- Memory usage: ~5.7 GiB out of 7.3 GiB
- llama-bench at ngl=99 FAILS because model already loaded in VRAM by server
  — `NvMapMemHandleAlloc failed: error 12` (ENOMEM). Expected.

### 3. Architecture discovery
- GGUF metadata reveals: `general.architecture = qwen35`
- **Not qwen3** (like 4B/8B). This is **Qwen 3.5** — hybrid architecture
  combining attention layers with SSM/Mamba layers.
- Has SSM parameters: `qwen35.ssm.conv_kernel`, `qwen35.ssm.state_size`,
  `qwen35.ssm.group_count`, `qwen35.ssm.time_step_rank`, `qwen35.ssm.inner_size`
- Has `[Start thinking]` reasoning mode similar to DeepSeek-R1/QwQ

### 4. Chat API failure
- `/v1/chat/completions` routes ALL tokens to `reasoning_content`
- `content` field is always empty string
- `"thinking": {"type": "disabled"}` has NO effect — thinking mode is hardcoded
- Result: 0/5 on coding eval with `NameError` on every task (no code in content)

### 5. llama-cli direct test
- `llama-cli` interactive mode WORKS — produces "Here's a" at 4.4 t/s generation
- Prompt processing: 7.7 t/s
- But enters infinite interactive prompt loop (`> ` repeated) via SSH
- Exit code 124 (SIGTERM timeout)

### 6. Completion endpoint workaround
- Raw `/completion` endpoint bypasses chat template → returns content directly
- Short tests (40-80 tokens) work at 3.0-3.2 t/s
- But output quality is poor: repetition loops (`is_palindrome1` through `is_palindrome5`
  all with identical implementation)
- `<think>` blocks leak into output even on completion endpoint

### 7. Server crashes on real workloads
- 150-250 token completion requests work
- 300 token requests crash the server (`Connection refused` on subsequent requests)
- Server process dies silently, no OOM (memory shows 6.4 GiB free after crash)
- Likely cause: PrismML fork incompatibility with Qwen3.5 hybrid architecture
  at 1-bit precision, or SSM layer bug triggered at longer sequences

## Technical details

```
Architecture:  qwen35 (Qwen 3.5 hybrid: attention + SSM/Mamba)
Parameters:    26.9B
Quantization:  Q1_0 (1-bit)
File size:     3.53 GB
VRAM usage:    ~5.7 GiB (ngl=99, ctx=2048)
Speed:         3.0-4.4 t/s generation, 3.7-7.7 t/s prompt processing
Server:        PrismML llama.cpp fork (build b9591-62061f910)
```

## Root causes of failure

1. **Chat template incompatibility**: Qwen3.5's thinking mode isn't properly
   handled by the PrismML fork's chat template. Tokens go to `reasoning_content`
   and can't be redirected.

2. **1-bit instability**: At 27B scale, 1-bit quantization collapses into
   repetition loops. The model loses the ability to produce diverse output
   and instead copies its own output verbatim.

3. **Server instability**: Longer completions crash the server, possibly due
   to SSM layer bugs or memory management issues in the PrismML fork.

## Conclusion

The Bonsai-27B is a dead end for practical use on the Jetson Orin Nano.
The 8B ternary model (4/5 coding, 2/5 IT troubleshooting) is the clear winner.
The 1-bit quantization format works at 4B scale but breaks down at 27B.

If Qwen3.5 hybrid architecture is interesting, wait for a properly quantized
version (Q2_0 or Q4_0) from a maintained fork, or test on hardware with more
VRAM where the server crash might not reproduce.
