#!/usr/bin/env bash
set -e

echo "=== Claude Code → NVIDIA NIM Fallback Setup ==="
echo

# Prompt for keys
read -rp "NVIDIA NIM API key (nvapi-...): " NVIDIA_KEY
read -rp "Anthropic API key (sk-ant-... or leave blank for OAuth only): " ANTHROPIC_KEY
MASTER_KEY="sk-litellm-$(python3 -c "import secrets; print(secrets.token_hex(16))")"

# 1. Install LiteLLM
echo
echo "[1/6] Installing LiteLLM..."
pip install 'litellm[proxy]' --quiet --break-system-packages

# 2. Config
echo "[2/6] Writing ~/litellm/config.yaml..."
mkdir -p ~/litellm
cp litellm/config.yaml ~/litellm/config.yaml

# 3. Env file
echo "[3/6] Writing ~/litellm/.env..."
cat > ~/litellm/.env << EOF
NVIDIA_NIM_API_KEY=${NVIDIA_KEY}
ANTHROPIC_API_KEY=${ANTHROPIC_KEY}
LITELLM_MASTER_KEY=${MASTER_KEY}
EOF
chmod 600 ~/litellm/.env

# 4. Background service (systemd on Linux, launchd on macOS)
echo "[4/6] Installing background service..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLIST=~/Library/LaunchAgents/com.litellm.proxy.plist
    mkdir -p ~/Library/LaunchAgents
    sed "s/YOUR_USERNAME/$(whoami)/g" launchd/com.litellm.proxy.plist > "$PLIST"
    # Inject env vars into the plist
    LITELLM_BIN=$(python3 -c "import shutil; print(shutil.which('litellm') or '$HOME/.local/bin/litellm')")
    sed -i '' "s|/Users/YOUR_USERNAME/.local/bin/litellm|${LITELLM_BIN}|g" "$PLIST"
    # Write env vars into the plist EnvironmentVariables dict
    /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:NVIDIA_NIM_API_KEY ${NVIDIA_KEY}" "$PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:NVIDIA_NIM_API_KEY string ${NVIDIA_KEY}" "$PLIST"
    /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:ANTHROPIC_API_KEY string ${ANTHROPIC_KEY}" "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:LITELLM_MASTER_KEY string ${MASTER_KEY}" "$PLIST" 2>/dev/null || true
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    sleep 3
    launchctl list | grep com.litellm && echo "  ✓ LiteLLM proxy running on localhost:4000 (launchd)"
else
    mkdir -p ~/.config/systemd/user
    cp systemd/litellm-proxy.service ~/.config/systemd/user/litellm-proxy.service
    systemctl --user daemon-reload
    systemctl --user enable --now litellm-proxy
    sleep 5
    systemctl --user is-active litellm-proxy && echo "  ✓ LiteLLM proxy running on localhost:4000 (systemd)"
fi

# 5. switch-backend script
echo "[5/6] Installing switch-backend..."
mkdir -p ~/bin
cp bin/switch-backend ~/bin/switch-backend
chmod +x ~/bin/switch-backend

# 6. Claude Code slash command
echo "[6/6] Installing /switch-backend slash command..."
mkdir -p ~/.claude/commands
cp .claude/commands/switch-backend.md ~/.claude/commands/switch-backend.md

echo
echo "=== Done ==="
echo
echo "Add these lines to your shell profile (~/.zshrc on Mac, ~/.bashrc on Linux)"
echo "to route Claude Code through LiteLLM by default:"
echo
echo "  export ANTHROPIC_BASE_URL=http://localhost:4000"
echo "  export ANTHROPIC_API_KEY=${MASTER_KEY}"
echo
echo "Then restart your terminal and run: switch-backend status"
echo
echo "Usage:"
echo "  switch-backend nvidia      # route to DeepSeek V4 Pro on NVIDIA NIM"
echo "  switch-backend anthropic   # route to Anthropic directly"
echo "  switch-backend status      # show current backend"
echo
echo "From Claude Code: /switch-backend nvidia"
