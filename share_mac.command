#!/bin/bash
echo "========================================"
echo "  OSINT War Room - Share Anywhere"
echo "========================================"
echo

cd "$(dirname "$0")"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q osint-warroom; then
    echo "[ERROR] War Room is not running. Double-click start_mac.command first."
    read -p "Press Enter to close..."
    exit 1
fi

# Check if cloudflared is installed
if ! command -v cloudflared &> /dev/null; then
    echo "[*] cloudflared not found. Installing via Homebrew..."
    if ! command -v brew &> /dev/null; then
        echo "[ERROR] Homebrew is not installed."
        echo "        Install it first: https://brew.sh"
        read -p "Press Enter to close..."
        exit 1
    fi
    brew install cloudflare/cloudflare/cloudflared
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install cloudflared."
        read -p "Press Enter to close..."
        exit 1
    fi
    echo
fi

# Get local IP for LAN URL
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)

# Start tunnel in background, capture output to temp file
CF_LOG=$(mktemp)
cloudflared tunnel --url http://localhost:8000 > "$CF_LOG" 2>&1 &
CF_PID=$!

echo "[*] Connecting to Cloudflare..."

# Wait for URL to appear (up to 30 seconds)
TRIES=0
while [ $TRIES -lt 30 ]; do
    sleep 1
    TRIES=$((TRIES + 1))
    if grep -q 'https://.*trycloudflare' "$CF_LOG" 2>/dev/null; then
        break
    fi
done

TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$CF_LOG" | head -1)

if [ -z "$TUNNEL_URL" ]; then
    echo "[!] Could not get tunnel URL."
    kill $CF_PID 2>/dev/null
    rm -f "$CF_LOG"
    read -p "Press Enter to close..."
    exit 1
fi

echo
echo "========================================"
echo
echo "  PUBLIC URL:  $TUNNEL_URL"
echo
if [ -n "$LOCAL_IP" ]; then
    echo "  LAN:         http://${LOCAL_IP}:8000"
fi
echo "  Local:       http://localhost:8000"
echo
echo "========================================"
echo
echo "  Share the link above with anyone."
echo "  Press Ctrl+C to stop sharing."
echo

# Cleanup on exit
cleanup() {
    echo
    echo "[*] Tunnel stopped."
    kill $CF_PID 2>/dev/null
    rm -f "$CF_LOG"
    exit 0
}
trap cleanup INT TERM

# Keep alive until cloudflared exits or user presses Ctrl+C
wait $CF_PID
rm -f "$CF_LOG"
echo
echo "[*] Tunnel stopped."
read -p "Press Enter to close..."
