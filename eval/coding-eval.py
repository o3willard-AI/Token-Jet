#!/usr/bin/env python3
"""Coding eval for edge-device models via llama-server API.

Designed for Jetson Orin Nano but works on any device running llama-server.
Handles: Bonsai ternary (PrismML fork), Gemma (thinking disable), standard models.

Setup: scp this to the device, update MODELS list, run.
Outputs: terminal log + JSON summary.
"""
import subprocess, urllib.request, urllib.error, json, time, sys, os, re

PORT = 1234

# MODEL LIST — edit these for your device
# Format: (display_name, model_path, server_binary, needs_thinking_disable)
MODELS = [
    ("Gemma-3-1B", "/path/to/model.gguf",     "/path/to/llama.cpp/build/bin/llama-server",        True),
    ("Bonsai-8B",  "/path/to/model.gguf",     "/path/to/llama.cpp-prism/build/bin/llama-server",   False),
    ("Bonsai-4B",  "/path/to/model.gguf",     "/path/to/llama.cpp-prism/build/bin/llama-server",   False),
]

TASKS = [
    {
        "name": "Task 1: Palindrome",
        "prompt": "Write ONLY Python code. No explanation.\n\n# Palindrome check function\n# Returns True if s is a palindrome (ignore case and spaces)\ndef is_palindrome(s: str) -> bool:\n    # your code here\n\n# Test\nresult = is_palindrome(\"Race car\")\nprint(f\"PASS: palindrome\" if result == True else f\"FAIL: got {result}\")\nresult2 = is_palindrome(\"Hello\")\nprint(f\"PASS: not palindrome\" if result2 == False else f\"FAIL: got {result2}\")\nprint(\"ALL TESTS PASSED\")\n",
    },
    {
        "name": "Task 2: FizzBuzz",
        "prompt": "Write ONLY Python code. No explanation.\n\n# FizzBuzz function: returns list of strings for numbers 1 to n\n# Multiples of 3 -> \"Fizz\", multiples of 5 -> \"Buzz\", both -> \"FizzBuzz\"\ndef fizzbuzz(n: int) -> list:\n    # your code here\n\n# Tests\nfb = fizzbuzz(15)\nassert fb[2] == \"Fizz\", f\"Expected Fizz, got {fb[2]}\"\nassert fb[4] == \"Buzz\", f\"Expected Buzz, got {fb[4]}\"\nassert fb[14] == \"FizzBuzz\", f\"Expected FizzBuzz, got {fb[14]}\"\nassert len(fb) == 15, f\"Expected 15 items, got {len(fb)}\"\nprint(\"PASS: fizzbuzz\")\nprint(\"ALL TESTS PASSED\")\n",
    },
    {
        "name": "Task 3: Find Pairs O(n)",
        "prompt": "Write ONLY Python code. No explanation.\n\n# Find all pairs in array that sum to target. O(n) time with a set.\n# Return list of tuples (smaller, larger), sorted, no duplicates.\ndef find_pairs(arr: list, target: int) -> list:\n    # your code here\n\n# Tests\nresult = find_pairs([1, 5, 3, 7, 9, 2, 4, 6, 8], 10)\nexpected = [(1, 9), (2, 8), (3, 7), (4, 6)]\nassert result == expected, f\"Expected {expected}, got {result}\"\nprint(\"PASS: find_pairs O(n)\")\nprint(\"ALL TESTS PASSED\")\n",
    },
    {
        "name": "Task 4: Circular Buffer",
        "prompt": "Write ONLY Python code. No explanation.\n\n# Circular buffer with fixed capacity. Overwrites oldest on overflow.\n# Raises IndexError on pop from empty buffer.\nclass CircularBuffer:\n    def __init__(self, capacity: int):\n        pass\n\n    def push(self, item):\n        pass\n\n    def pop(self):\n        pass  # raises IndexError if empty\n\n    def __len__(self):\n        pass\n\n# Tests\ncb = CircularBuffer(3)\ncb.push(1); cb.push(2); cb.push(3)\nassert len(cb) == 3, f\"Expected 3, got {len(cb)}\"\ncb.push(4)\nassert cb.pop() == 2, \"Expected 2 (oldest remaining)\"\nassert cb.pop() == 3\nassert cb.pop() == 4\ntry:\n    cb.pop()\n    assert False, \"Should have raised IndexError\"\nexcept IndexError:\n    pass\nprint(\"PASS: circular buffer\")\nprint(\"ALL TESTS PASSED\")\n",
    },
    {
        "name": "Task 5: Semver Parser",
        "prompt": "Write ONLY Python code. No explanation.\n\n# Semantic version parser. Parse \"MAJOR.MINOR.PATCH\" string.\n# Support comparison operators: ==, <, >, <=, >=\n# Raise ValueError on invalid format.\nclass SemVer:\n    def __init__(self, version: str):\n        pass\n\n    def __eq__(self, other): pass\n    def __lt__(self, other): pass\n    def __le__(self, other): pass\n    def __gt__(self, other): pass\n    def __ge__(self, other): pass\n    def __repr__(self): pass\n\n# Tests\nv1 = SemVer(\"1.2.3\")\nv2 = SemVer(\"1.2.4\")\nv3 = SemVer(\"2.0.0\")\nv4 = SemVer(\"1.2.3\")\nassert v1 == v4\nassert v1 < v2\nassert v2 > v1\nassert v1 <= v4\nassert v1 < v3\nassert v3 >= v2\ntry:\n    SemVer(\"1.2\")\n    assert False, \"Should have raised ValueError\"\nexcept ValueError:\n    pass\nprint(\"PASS: semver\")\nprint(\"ALL TESTS PASSED\")\n",
    },
]


def start_server(server_bin, model_path):
    """Start llama-server, poll /health until ready. Returns Popen or None."""
    subprocess.run(["pkill", "-f", "llama-server"], stderr=subprocess.DEVNULL)
    time.sleep(2)
    proc = subprocess.Popen(
        [server_bin, "-m", model_path, "--host", "0.0.0.0", "--port", str(PORT),
         "--n-gpu-layers", "99", "--ctx-size", "4096"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    for i in range(90):
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2)
            data = r.read()
            if b'"status":"ok"' in data or b'"status": "ok"' in data:
                return proc
        except:
            pass
        time.sleep(2)
    proc.kill(); proc.wait()
    return None


def stop_server(proc):
    proc.kill(); proc.wait(); time.sleep(1)


def extract_code(content):
    """Extract runnable Python from model output.

    PITFALL: Small/ternary models often wrap output in ```python...``` fences.
    Do NOT use removeprefix/removesuffix — those only strip one occurrence.
    Use regex to find and extract the fenced block.

    Also strips <think>/<thinking> blocks (Gemma, reasoning models).
    """
    # Strip thinking blocks
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL)

    # Extract from ```python ... ``` fences (most reliable)
    fence_match = re.search(r'```python\s*\n(.*?)```', content, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    # Fallback: generic ``` ... ``` fences
    fence_match = re.search(r'```\s*\n(.*?)```', content, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    # No fences — find where code starts and take everything from there
    lines = content.strip().split('\n')
    code_start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith(('def ', 'class ', 'import ', 'from ',
                                     'result ', 'cb ', 'v1 ', 'v2 ', 'v3 ', 'v4 ',
                                     'try', '#')):
            code_start = i
            break
    return '\n'.join(lines[code_start:]).strip()


def run_task(task, is_gemma):
    body = {
        "messages": [{"role": "user", "content": task["prompt"]}],
        "max_tokens": 512,
        "temperature": 0,
    }
    if is_gemma:
        body["thinking"] = {"type": "disabled"}

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        data=data, headers={"Content-Type": "application/json"}
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
        raw_content = resp["choices"][0]["message"]["content"]
        code = extract_code(raw_content)

        result = subprocess.run(["python3", "-c", code],
                              capture_output=True, text=True, timeout=15)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        passed = "ALL TESTS PASSED" in stdout

        r = {
            "name": task["name"],
            "passed": passed,
            "output": (stdout + "\n" + stderr).strip()[:300],
            "code_len": len(raw_content),
            "extracted_len": len(code),
        }

        if not passed:
            r["raw_model_output"] = raw_content[:600]
            r["extracted_code"] = code[:600]
            r["exec_stdout"] = stdout[:200]
            r["exec_stderr"] = stderr[:200]

        return r
    except Exception as e:
        return {
            "name": task["name"],
            "passed": False,
            "output": str(e)[:200],
            "code_len": 0, "extracted_len": 0,
            "error": str(e)[:300],
        }


def main():
    summary = []
    for name, path, server_bin, is_gemma in MODELS:
        print(f"\n{'='*60}")
        print(f"EVALUATING: {name}")
        print(f"{'='*60}")

        proc = start_server(server_bin, path)
        if not proc:
            print("FAILED to start server")
            summary.append({"name": name, "results": [], "score": 0})
            continue

        print("Server started OK")
        results = []
        for task in TASKS:
            print(f"\n  Running: {task['name']}...")
            r = run_task(task, is_gemma)
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  {status} | code_len={r['code_len']} | output: {r.get('output','')[:80]}")
            if not r["passed"] and "raw_model_output" in r:
                print(f"    RAW: {r['raw_model_output'][:120]}...")
                print(f"    EXTRACTED: {r['extracted_code'][:120]}...")
                if r.get("exec_stderr"):
                    print(f"    STDERR: {r['exec_stderr'][:120]}")
            results.append(r)

        stop_server(proc)
        score = sum(1 for r in results if r["passed"])
        print(f"\n  SCORE: {score}/5")
        summary.append({"name": name, "results": results, "score": score})

    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    for s in summary:
        print(f"\n{s['name']}: {s['score']}/5")
        for r in s["results"]:
            ok = "PASS" if r["passed"] else "FAIL"
            detail = ""
            if not r["passed"] and r.get("exec_stderr"):
                detail = f"  [{r['exec_stderr'][:80]}]"
            print(f"  {ok} {r['name']} (code={r['code_len']}b){detail}")

    out_path = "/tmp/coding_eval_results.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults written to {out_path}")

if __name__ == "__main__":
    main()
