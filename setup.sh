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

# 4. Systemd user service
echo "[4/6] Installing litellm-proxy systemd service..."
mkdir -p ~/.config/systemd/user
cp systemd/litellm-proxy.service ~/.config/systemd/user/litellm-proxy.service
systemctl --user daemon-reload
systemctl --user enable --now litellm-proxy
sleep 5
systemctl --user is-active litellm-proxy && echo "  ✓ LiteLLM proxy running on localhost:4000"

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
echo "Usage:"
echo "  switch-backend nvidia      # route agents to DeepSeek V4 Pro"
echo "  switch-backend anthropic   # route agents to Anthropic"
echo "  switch-backend status      # show current backend"
echo
echo "From Claude Code: /switch-backend nvidia"
echo
echo "To wire into a director service, see README.md § 'Wire into your director'."
echo "LITELLM_MASTER_KEY=${MASTER_KEY}"
