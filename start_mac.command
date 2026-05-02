#!/bin/bash
echo "========================================"
echo "  OSINT War Room - Starting..."
echo "========================================"
echo

cd "$(dirname "$0")"

if ! docker info > /dev/null 2>&1; then
    echo "[ERROR] Docker Desktop is not running. Please start Docker Desktop first."
    read -p "Press Enter to close..."
    exit 1
fi

echo "[*] Building and starting containers..."
docker compose up -d --build

if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to start. Check Docker Desktop is running."
    read -p "Press Enter to close..."
    exit 1
fi

echo
echo "[*] Waiting for server to be ready..."
sleep 3

echo "[*] Opening dashboard..."
open http://localhost:8000

echo
echo "========================================"
echo "  War Room is LIVE at localhost:8000"
echo "  (The server keeps running in Docker)"
echo "========================================"
read -p "Press Enter to close..."
