# Model Evaluation Results

All benchmarks run on NVIDIA Jetson Orin Nano 8GB (JetPack 39.2, CUDA 13.2, Ubuntu 24.04 aarch64).

## Coding Eval (5 tasks)

Progressive difficulty: Palindrome → FizzBuzz → Find Pairs O(n) → Circular Buffer → Semver Parser. Each task auto-appends test harness if model only outputs function body. Verified by actual `python3 -c` execution.

| Model | Score | t/s | Size | Passed | Failed |
|-------|:-----:|:---:|------|--------|--------|
| **Ternary-Bonsai-8B Q2_0** | **4/5** | 8.4 | 2.03 GB | Palindrome, FizzBuzz, Find Pairs, Semver | Circular Buffer |
| Ternary-Bonsai-4B Q2_0 | 3/5 | 16.3 | 1.02 GB | Palindrome, FizzBuzz, Find Pairs | Circular Buffer, Semver |
| Gemma-3-1B F16 | 2/5 | 15.6 | 1.86 GB | Palindrome, FizzBuzz | Find Pairs, Circular Buffer, Semver |
| Bonsai-27B Q1_0 | 0/5 | 3.2 | 3.53 GB | — | All (crashes server) |

**Universal failure:** Circular Buffer. No model solved it. Requires multi-step reasoning: overflow tracking, head/tail arithmetic, size management, IndexError on empty.

**Key findings:**
- 1.58-bit ternary (4B, 8B) is the sweet spot for edge coding
- 1-bit quantization at 27B collapses into repetition loops
- The 4B loses Semver when it can't see the test cases (TDD matters for small models)
- All models produce function-only output on simple tasks — test harness must be auto-appended

## IT Troubleshooting Eval (5 scenarios)

Conversational diagnostic test: DNS failure → Disk full mystery → SSH works/no internet → SSL date error → Multi-server architecture. Models act as tech support, user provides misleading info.

| Model | Score | Passed | Failed |
|-------|:-----:|--------|--------|
| **Ternary-Bonsai-8B Q2_0** | **2/5** | DNS, Architecture | Disk, SSH, SSL |
| Ternary-Bonsai-4B Q2_0 | 1/5 | DNS | Disk, SSH, SSL, Arch |
| Gemma-3-1B F16 | 1/5 | DNS | Disk, SSH, SSL, Arch |

**Universal failures:**
1. **Disk Full Mystery**: No model mentioned `lsof` or deleted file handles
2. **SSL Date Error**: Every model trusted the user's "clock is fine" claim — no skepticism
3. **SSH/No Internet**: None recognized `127.0.0.53` as systemd-resolved stub resolver

**Key insight:** IT troubleshooting is harder than coding for small models. Coding has clear contracts (function signatures, test cases). Troubleshooting requires questioning assumptions — which these models don't do.

## Cross-Eval Comparison

| Domain | Bonsai-8B | Bonsai-4B | Gemma-3-1B |
|--------|:---------:|:---------:|:----------:|
| Coding | 4/5 🥇 | 3/5 🥈 | 2/5 🥉 |
| IT Support | 2/5 🥇 | 1/5 🥈 | 1/5 🥈 |
| **Best for** | Code gen + architecture | Interactive/low latency | Speed over quality |

## Methodology Notes

- **Coding eval**: Uses `/completion` endpoint (bypasses chat template issues). Test harness auto-appended. Thinking mode disabled for Gemma. Markdown fence extraction via regex.
- **IT eval**: Uses `/v1/chat/completions`. Multi-turn conversations with intentional user misdirection. 600 max_tokens. Keyword-based scoring (lenient — tests domain identification, not exact commands).
- **Hardware**: All tests on same Jetson Orin Nano. llama-server with `--n-gpu-layers 99`. Eval scripts deploy via base64 pipe to survive SSH drops during model loading.

Full eval scripts in `eval/` directory.
