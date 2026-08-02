# Install Script Backlog

Issues found during pre-wipe audit (2026-07-25). All three blockers and most warnings are specific to `install.sh` (workstation SSH path).

**Fixed 2026-07-26:** `install-local.sh` now builds the PrismML fork by default (using the existing `_build_llama` helper with its `-j3` cap and CUDA auto-detection). Pass `--no-prism-build` to skip. This resolves the root cause of Bonsai falling back to CPU after a local install.

---

## Fixed 2026-08-01

### FX1 — Unwanted pi packages installed on every fresh deploy
**Commit:** `d15f452`  
`install-local.sh` and `install.sh` both called `yes | pi install` for `@plannotator/pi-extension`, `@juicesharp/rpiv-ask-user-question`, and `pi-knowledge`. Even when the npm install failed, `pi install` registered the packages in `~/.pi/agent/settings.json`, bloating the context window on every session. Removed all three `pi install` calls from both scripts.

### FX2 — pi `settings.json` never deployed on fresh install
**Commit:** `d15f452`  
The repo's `pi/settings.json` was guarded by `if [[ ! -f ~/.pi/agent/settings.json ]]`, but `pi install npm:pi-mcp-adapter` (which ran first) creates that file as a side effect. Moved the settings.json deployment to before the `pi install` step so the repo version actually lands on fresh installs.

### FX3 — TUI model switch bypassed SWITCH_LOCK, causing watchdog race
**Commit:** `475f46b`  
`_switch_worker` in `main_screen.py` called `jetson-infer stop` then `jetson-infer start` as two separate commands. No SWITCH_LOCK was set during the gap, so the watchdog saw the server go dark, treated it as a crash, and restarted the startup model — racing against (and overwriting) the TUI's `start` call. Bonsai and any non-default model consistently failed to load. Fixed by calling `jetson-infer switch` instead, which holds SWITCH_LOCK for the full transition.

### FX4 — Context formula used FP16 bytes/element instead of Q8_0
**Commit:** `ce6de05`  
`calculate_max_context` computed KV cost with `* 2` (FP16, 2 bytes/element), but llama-server is launched with `--cache-type-k/v q8_0` (1 byte/element). This halved the computed context window. Bonsai-8B landed at 12288 instead of 24576. The old hard cap of 20480 masked the bug for Qwen3.5-4B (the physics calculation exceeded the cap anyway). The size-based fallback coefficient was also wrong (144 → 72). Fixed by using `* 1` for Q8_0 throughout.

---

---

## Blockers — `install.sh` only

### B1 — NodeSource install broken
**File:** `scripts/install.sh:322`

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | echo '${JETSON_PASS}' | sudo -SE bash -
```

In a three-stage pipe, `echo` ignores its stdin and discards curl's output. `bash -` receives nothing and Node.js is not installed. All subsequent npm/pi steps will fail.

**Fix:** Restructure to pre-authenticate sudo separately, then `curl ... | sudo -E bash -` without the echo-in-the-middle. Reference: `install-local.sh:361` does this correctly.

---

### B2 — ddg-search JS files not deployed by `install.sh`
**Files:** `scripts/install.sh:291-304`, `pi/jetson-provider.ts:12,127,239`

`install.sh` creates `/usr/local/bin/ddg-search` and `/usr/local/bin/fetch-url` wrappers on the Jetson that reference `~/Token-Jet/pi/ddg-search/search.js` and `content.js`, but those files are never transferred. `install-local.sh` avoids this because it clones the full repo.

**Fix:** Either transfer `pi/ddg-search/` via tar in `install.sh`, or clone the full repo on the Jetson as part of the SSH install path.

---

### B3 — pi-web service directory created after the file write
**File:** `scripts/install.sh:413-416`

`_pipe_to "~/.config/systemd/user/pi-web.service"` runs before `mkdir -p ~/.config/systemd/user/`. On a fresh Jetson the directory doesn't exist and the `cat >` write fails with ENOENT.

**Fix:** Move the `mkdir -p ~/.config/systemd/user/` call to a prior `_ssh` block, before any writes to that directory.

---

## Warnings — `install.sh` only

### W1 — PrismML build uses uncapped parallelism
**File:** `scripts/install.sh:503`

`cmake --build ... -j$(nproc)` uses all 6 CPU cores. Each `nvcc` job uses ~1.5 GB; 6 jobs = 9 GB, exceeding the Jetson's 8 GB. The mainline build in `install-local.sh` caps at `-j3`. The prism build may OOM-kill mid-build.

**Fix:** Change to `-j3` (matching the mainline build cap).

---

### W2 — CUDA path hardcoded to `cuda-13.2`
**Files:** `scripts/install.sh:277`, `scripts/install.sh:494`, `scripts/install.sh:526`

The workstation launcher, PrismML CUDACXX, and written config.toml all hardcode `/usr/local/cuda-13.2/`. `install-local.sh` dynamically detects the installed CUDA version. If the new JetPack ships a different CUDA version, the PrismML build will fail and the config will be wrong.

**Fix:** Mirror `install-local.sh`'s dynamic detection: `CUDA_ROOT=$(ls -d /usr/local/cuda-* | sort -V | tail -1)`.

---

### W3 — PrismML build leaves ~1-2 GB of intermediates
**File:** `scripts/install.sh:483-506`

After `cmake --build`, the build tree (`*.o`, `*.a`, `CMakeFiles/`) is not cleaned. `install-local.sh`'s `_build_llama` removes them to recover disk space. On an eMMC Jetson this may exhaust storage mid-install.

**Fix:** After `cmake --build`, add `find ~/llama.cpp-prism/build -name '*.o' -o -name '*.a' | xargs rm -f` (matching `install-local.sh`'s pattern).

---

## Warnings — Both Paths

### W5 — Config key name mismatch for prism binary path
**Files:** `tui/token_jet_tui/config.py:27`, `jetson-infer:143`

- `jetson-infer` reads `prism_llama_cpp_bin` from config.toml
- TUI `config.py` uses the field name `llama_cpp_prism_bin`

Both tools default to `~/llama.cpp-prism/build/bin` so this only breaks manual path overrides in config.toml. Pick one name and make both files consistent; AGENT_REFERENCE specifies `prism_llama_cpp_bin`.

---

### F2 — TUI `config.py` cannot read config.toml on Python 3.10
**File:** `tui/token_jet_tui/config.py:13`

```python
# Wrong: tomllib is not in stdlib on Python 3.10
import tomllib
```

Should be:
```python
import tomli as tomllib
```

`tomli` is already declared as a dependency in `pyproject.toml` for Python < 3.11, but the import is never attempted. On Ubuntu 22.04 (JetPack 6.0, Python 3.10), the TUI silently ignores `config.toml` and uses hardcoded defaults. Not relevant on Ubuntu 24.04 (Python 3.12.3).

---

## Low Priority

### W6 — `install.sh` default `--user` is `ubuntu`
**File:** `scripts/install.sh:38`

Running `./scripts/install.sh <ip>` without `--user sblanken` will fail immediately. Should default to the current local user, or at minimum be more prominent in the usage output.

### W7 — Eval scripts deployed to wrong directory case by `install.sh`
**File:** `scripts/install.sh:599`

Creates `~/token-jet/eval/` (lowercase) instead of `~/Token-Jet/eval/` (repo convention). Harmless but leaves a spurious directory.
