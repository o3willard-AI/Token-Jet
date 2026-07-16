#!/usr/bin/env python3
"""
IT Troubleshooting Assistant Eval — 5 scenarios of increasing difficulty.
Tests conversational diagnostic ability on Jetson Orin Nano.

Deploy: base64 it_eval.py | ssh sblanken@192.168.101.10 'base64 -d > /tmp/it_eval.py'
Run: ssh sblanken@192.168.101.10 'python3 /tmp/it_eval.py'

Modify SCENARIOS to add/change test cases. Modify MODELS for different hardware.
"""
import urllib.request, json, re, time, subprocess as sp

SCENARIOS = [
    {
        "name": "DNS Resolution Failure",
        "difficulty": "Easy",
        "turns": [
            {"role": "user", "content": "Hey, I'm trying to run 'apt update' on my Ubuntu 22.04 server but getting 'Could not resolve archive.ubuntu.com'. I *can* ping 8.8.8.8 though. What should I check?"}
        ],
        "must_match": ["dns", "resolv"],
    },
    {
        "name": "Disk Full Mystery",
        "difficulty": "Easy-Medium",
        "turns": [
            {"role": "user", "content": "My server says disk is full — 'df -h /' shows 98% used on a 100GB disk. But when I run 'du -sh /*' it only adds up to about 30GB. Where's the other 70GB? I already rebooted, no change. What's going on?"}
        ],
        "must_match": ["deleted", "lsof", "open file", "file handle"],
    },
    {
        "name": "SSH Works But No Internet",
        "difficulty": "Medium",
        "turns": [
            {"role": "user", "content": "Weird problem. I can SSH into my Ubuntu server fine. From ON the server, ping 8.8.8.8 works, but 'curl https://google.com' fails with 'Could not resolve host'. Already checked iptables — rules are empty. What should I look at?"},
            {"role": "assistant", "content": "Let's check DNS resolution. What does 'cat /etc/resolv.conf' show?"},
            {"role": "user", "content": "It says 'nameserver 127.0.0.53'. So it's using localhost for DNS. Is that the problem?"},
        ],
        "must_match": ["systemd-resolved", "stub resolver", "127.0.0.53 is", "systemd"],
    },
    {
        "name": "SSL Certificate Date Error",
        "difficulty": "Medium-Hard",
        "turns": [
            {"role": "user", "content": "My production website was working fine yesterday. Today Chrome shows NET::ERR_CERT_DATE_INVALID. The SSL cert from Let's Encrypt doesn't expire for 3 more months. I already restarted nginx — no change. What could cause this?"},
            {"role": "assistant", "content": "That's often a system clock issue. What does 'date' return on the server?"},
            {"role": "user", "content": "'date' shows: Thu Jul 16 14:22:01 PDT 2026. That looks right — it IS July 16th. So the clock is fine."},
        ],
        "must_match": ["ntp", "timedatectl", "clock skew", "synchron", "hardware clock", "timezone"],
    },
    {
        "name": "Multi-Server Web Architecture",
        "difficulty": "Hard",
        "turns": [
            {"role": "user", "content": "I have 4 fresh Ubuntu 22.04 servers (8GB RAM, 4 cores each). I need to deploy a Python/FastAPI app that uses PostgreSQL and Redis. It needs to handle about 10,000 concurrent users, be fault-tolerant (survive losing one server), and have HTTPS. Walk me through the architecture — which services go where, and the key setup steps."}
        ],
        "must_match": ["load balanc", "replic", "ssl"],
    },
]


def score_response(response, must_match):
    response_lower = response.lower()
    matches = []
    for keyword in must_match:
        if keyword.lower() in response_lower:
            matches.append(keyword)
    return len(matches) == len(must_match), matches


def start_server(bin_path, model_path, port=1234):
    sp.run(["pkill", "-f", "llama-server"], stderr=sp.DEVNULL)
    time.sleep(2)
    proc = sp.Popen([bin_path, "-m", model_path, "--host", "0.0.0.0", "--port", str(port),
                     "--n-gpu-layers", "99", "--ctx-size", "4096"],
                    stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    for i in range(90):
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
            if b'"status":"ok"' in r.read() or b'"status": "ok"' in r.read():
                return proc
        except: pass
        time.sleep(2)
    proc.kill(); return None


# Edit this list for your hardware
MODELS = [
    ("Gemma-3-1B", "/home/sblanken/models/Gemma-3-1B-it-GLM-4.7-Flash-Heretic-Uncensored-Thinking_F16.gguf",
     "/home/sblanken/llama.cpp/build/bin/llama-server", True),
    ("Ternary-Bonsai-8B", "/home/sblanken/models/Ternary-Bonsai-8B-Q2_0.gguf",
     "/home/sblanken/llama.cpp-prism/build/bin/llama-server", False),
    ("Ternary-Bonsai-4B", "/home/sblanken/models/Ternary-Bonsai-4B-Q2_0.gguf",
     "/home/sblanken/llama.cpp-prism/build/bin/llama-server", False),
]

print("=" * 60)
print("IT TROUBLESHOOTING ASSISTANT EVAL")
print("=" * 60)

summary = []
for name, path, bin_path, is_gemma in MODELS:
    print(f"\n{'='*60}")
    print(f"MODEL: {name}")
    print(f"{'='*60}")
    
    proc = start_server(bin_path, path)
    if not proc:
        summary.append({"name": name, "error": "server failed"})
        continue
    print("  Server ready", flush=True)
    
    results = []
    for sc in SCENARIOS:
        print(f"\n  --- {sc['name']} ({sc['difficulty']}) ---", flush=True)
        
        messages = [{"role": t["role"], "content": t["content"]} for t in sc["turns"]]
        body = {"messages": messages, "max_tokens": 600, "temperature": 0}
        if is_gemma:
            body["thinking"] = {"type": "disabled"}
        
        try:
            resp = json.loads(urllib.request.urlopen(
                urllib.request.Request(f"http://127.0.0.1:1234/v1/chat/completions",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"}), timeout=240).read())
            response = resp["choices"][0]["message"]["content"]
        except Exception as e:
            response = f"[ERROR: {e}]"
        
        passed, matched = score_response(response, sc["must_match"])
        missing = [k for k in sc["must_match"] if k not in [m.lower() for m in matched]]
        
        status = "PASS" if passed else "FAIL"
        print(f"    {status} | matched: {matched} | missing: {missing}", flush=True)
        print(f"    Response ({len(response)} chars): {response[:250]}...", flush=True)
        
        results.append({
            "name": sc["name"], "difficulty": sc["difficulty"],
            "passed": passed, "matched": matched, "missing": missing,
            "response": response[:600],
        })
    
    proc.kill(); proc.wait()
    score = sum(1 for r in results if r["passed"])
    summary.append({"name": name, "results": results, "score": score})
    print(f"\n  SCORE: {score}/{len(SCENARIOS)}", flush=True)

print("\n" + "=" * 60)
print("FINAL RESULTS")
print("=" * 60)
for s in summary:
    if "error" in s:
        print(f"\n{s['name']}: ERROR — {s['error']}")
        continue
    print(f"\n{s['name']}: {s['score']}/{len(SCENARIOS)}")
    for r in s["results"]:
        ok = "PASS" if r["passed"] else "FAIL"
        detail = f" (matched: {r['matched']})" if r.get("matched") else ""
        print(f"  {ok} {r['name']} ({r['difficulty']}){detail}")

with open("/tmp/it_eval_results.json", "w") as f:
    json.dump(summary, f, indent=2)
print("\nResults -> /tmp/it_eval_results.json")
