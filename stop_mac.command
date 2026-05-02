#!/bin/bash
echo "========================================"
echo "  OSINT War Room - Stopping..."
echo "========================================"
echo

cd "$(dirname "$0")"

docker compose down

echo
echo "[*] War Room stopped. Data is preserved in ./data/"
echo
read -p "Press Enter to close..."
