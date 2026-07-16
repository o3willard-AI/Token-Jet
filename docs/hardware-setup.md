# Jetson Orin Nano Setup Guide

From unboxed device to running Token-Jet inference server.

## Prerequisites

- NVIDIA Jetson Orin Nano (8GB recommended, 4GB may work)
- USB-C power supply (15W mode) or barrel jack (19W mode)
- microSD or NVMe SSD (for model storage if eMMC is too small)
- Ubuntu 24.04 host machine for flashing

## 1. Flash JetPack

Download NVIDIA SDK Manager from https://developer.nvidia.com/sdk-manager

```bash
# On host machine
sudo apt install ./sdkmanager_*.deb
sdkmanager --cli install --logintype devzone --product Jetson --target-os Linux --version 6.2
```

Select:
- **Host Machine:** (your laptop/desktop)
- **Target:** Jetson Orin Nano (8GB)
- **JetPack:** 6.2 (or latest)
- **Components:** CUDA, cuDNN, TensorRT, OpenCV, VPI

Flash via USB-C in recovery mode (hold REC button, press RST, release REC).

## 2. First Boot Setup

```bash
# Set performance mode
sudo nvpmodel -m 0          # MAXN (full performance)
sudo jetson_clocks           # Lock clocks at maximum

# Verify CUDA
nvcc --version
python3 -c "import torch; print(torch.cuda.is_available())"
```

## 3. Install llama.cpp with CUDA

```bash
# Standard llama.cpp (for Gemma and standard models)
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
mkdir build && cd build
cmake .. -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="87"
make -j6

# PrismML fork (for Bonsai ternary/1-bit models)
cd ~
git clone https://github.com/PrismML-Eng/llama.cpp llama.cpp-prism
cd llama.cpp-prism
git checkout prism
mkdir build && cd build
cmake .. -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="87"
make -j6
```

Set `LD_LIBRARY_PATH` for CUDA libraries:

```bash
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-13.2/targets/sbsa-linux/lib:$LD_LIBRARY_PATH' >> ~/.bashrc
```

## 4. Download Models

Recommended starter set (~6 GB total):

```bash
mkdir ~/models

# Ternary-Bonsai-8B (best overall, 2.0 GB)
wget -P ~/models https://huggingface.co/prism-ml/Ternary-Bonsai-8B-gguf/resolve/main/Ternary-Bonsai-8B-Q2_0.gguf

# Ternary-Bonsai-4B (faster, lower quality, 1.0 GB)
wget -P ~/models https://huggingface.co/prism-ml/Ternary-Bonsai-4B-gguf/resolve/main/Ternary-Bonsai-4B-Q2_0.gguf

# Gemma-3-1B (optional, 1.9 GB)
wget -P ~/models https://huggingface.co/bartowski/Gemma-3-1B-it-GGUF/resolve/main/Gemma-3-1B-it-GLM-4.7-Flash-Heretic-Uncensored-Thinking_F16.gguf
```

## 5. Deploy Token-Jet

```bash
# From your dev machine
./scripts/deploy.sh <jetson-ip>

# Or manually
scp jetson-infer jetson-infer.service user@jetson:~/bin/
ssh user@jetson
cd ~/bin
chmod +x jetson-infer
```

## 6. Start Serving

```bash
jetson-infer start              # Best model (8B) with auto context
jetson-infer install            # Auto-start on boot (optional)
```

## 7. Verify

```bash
# From any machine on the network
curl http://<jetson-ip>:1234/v1/models
curl http://<jetson-ip>:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"max_tokens":20}'
```

## Performance Notes

- **eMMC is slow:** ~8 MB/s read. 2 GB model takes ~4 minutes to load first time. Subsequent starts are faster if model stays in page cache.
- **No swap:** Jetson Orin has no swap partition. Memory is tight — the 8B model at 16K context uses ~6 GB.
- **Power:** 15W mode limits GPU clocks. Use MAXN (nvpmodel -m 0) for full performance.
- **Thermal:** Passive cooling is fine for inference. No throttling observed at 15W continuous.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `cudaMalloc failed: out of memory` | Context too large | `jetson-infer models` shows max context for free memory |
| Server times out loading | eMMC bottleneck | Wait longer; model is loading. Check `/tmp/jetson-infer.log` |
| Chat API returns empty content | Chat template issue with Qwen3.5 models | Use 4B/8B (Qwen3 architecture). 27B is known-broken |
| `NvMapMemHandleAlloc failed: error 12` | Out of GPU memory | Kill other processes, reduce context |
