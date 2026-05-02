#!/bin/bash
echo "========================================"
echo "  OSINT War Room - Mac Setup"
echo "========================================"
echo

cd "$(dirname "$0")"

# Make all .command files executable (one-time setup)
chmod +x start_mac.command stop_mac.command share_mac.command setup_mac.command

echo "[*] All scripts are now double-clickable."
echo
echo "  start_mac.command  — Start the War Room"
echo "  stop_mac.command   — Stop the War Room"
echo "  share_mac.command  — Share via public URL"
echo
echo "[*] Setup complete. You can now double-click any of the above."
echo
read -p "Press Enter to close..."
