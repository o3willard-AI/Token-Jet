#!/bin/bash
# Deploy Token-Jet to a Jetson Orin Nano on the local network.
# Usage: ./scripts/deploy.sh <jetson-ip> [user]
# Example: ./scripts/deploy.sh 192.168.101.10 sblanken

set -e

JETSON_IP="${1:-192.168.101.10}"
JETSON_USER="${2:-sblanken}"
JETSON_HOME="/home/${JETSON_USER}"

echo "=== Token-Jet Deploy ==="
echo "Target: ${JETSON_USER}@${JETSON_IP}"
echo ""

# Check SSH access
echo "Checking SSH access..."
if ! ssh -o ConnectTimeout=5 "${JETSON_USER}@${JETSON_IP}" 'echo OK' > /dev/null 2>&1; then
    echo "ERROR: Cannot SSH to ${JETSON_USER}@${JETSON_IP}"
    echo "Make sure SSH is set up and the Jetson is on the network."
    exit 1
fi
echo "SSH: OK"

# Create directories
echo "Creating directories..."
ssh "${JETSON_USER}@${JETSON_IP}" "mkdir -p ${JETSON_HOME}/bin"

# Deploy jetson-infer
echo "Deploying jetson-infer..."
base64 jetson-infer | ssh "${JETSON_USER}@${JETSON_IP}" "base64 -d > ${JETSON_HOME}/bin/jetson-infer && chmod +x ${JETSON_HOME}/bin/jetson-infer"
echo "  jetson-infer: OK ($(wc -c < jetson-infer) bytes)"

# Deploy service file
echo "Deploying systemd service..."
base64 jetson-infer.service | ssh "${JETSON_USER}@${JETSON_IP}" "base64 -d > ${JETSON_HOME}/bin/jetson-infer.service"
echo "  jetson-infer.service: OK"

# Deploy eval scripts
echo "Deploying eval scripts..."
ssh "${JETSON_USER}@${JETSON_IP}" "mkdir -p ${JETSON_HOME}/token-jet/eval"
base64 eval/coding-eval.py | ssh "${JETSON_USER}@${JETSON_IP}" "base64 -d > ${JETSON_HOME}/token-jet/eval/coding-eval.py"
base64 eval/it-eval.py | ssh "${JETSON_USER}@${JETSON_IP}" "base64 -d > ${JETSON_HOME}/token-jet/eval/it-eval.py"
echo "  eval scripts: OK"

echo ""
echo "=== Deploy Complete ==="
echo ""
echo "Next steps:"
echo "  ssh ${JETSON_USER}@${JETSON_IP}"
echo "  jetson-infer models     # See available models"
echo "  jetson-infer start      # Start inference server"
echo "  jetson-infer install    # Auto-start on boot (optional)"
echo ""
echo "Agent endpoint: http://${JETSON_IP}:1234/v1"
