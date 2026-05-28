# Claude Code → NVIDIA NIM Fallback

Route Claude Code agent traffic through a local [LiteLLM](https://github.com/BerriAI/litellm) proxy, with **DeepSeek V4 Pro** on NVIDIA NIM as a fallback when your Anthropic Max account hits rate limits.

```
Claude Code agents
      │
      ▼
LiteLLM proxy (localhost:4000)
      │
      ├─ primary ──▶ Anthropic API (your API key / Max OAuth)
      └─ fallback ──▶ NVIDIA NIM  (DeepSeek V4 Pro)
```

Switch backends in one command:

```bash
switch-backend nvidia      # route to DeepSeek V4 Pro
switch-backend anthropic   # route to Anthropic
switch-backend status      # show current backend
```

Or from Claude Code: `/switch-backend nvidia`

---

## Prerequisites

- Python 3.10+
- `systemd` (Linux)
- A Claude Code setup running a director that spawns agents (or any setup that respects `ANTHROPIC_BASE_URL`)
- API keys:
  - [NVIDIA NIM](https://integrate.api.nvidia.com) — free tier available
  - Anthropic API key (optional — can use Claude Max OAuth instead)

---

## Quick install

```bash
git clone https://github.com/markusresearchops/claude-nvidia-fallback
cd claude-nvidia-fallback
./setup.sh
```

The script will prompt for your API keys and wire everything up.

---

## What `setup.sh` does

1. Installs `litellm[proxy]` via pip
2. Creates `~/litellm/config.yaml` with DeepSeek V4 Pro on NVIDIA NIM
3. Creates `~/litellm/.env` with your API keys (chmod 600)
4. Installs `~/.config/systemd/user/litellm-proxy.service` and enables it
5. Installs `~/bin/switch-backend` toggle script
6. Installs `/switch-backend` Claude Code slash command
7. Creates a systemd drop-in for your director service (optional)

---

## Manual setup

### 1. Install LiteLLM

```bash
pip install 'litellm[proxy]' --break-system-packages
```

### 2. Create config

```bash
mkdir -p ~/litellm
cp litellm/config.yaml ~/litellm/config.yaml
```

Edit `~/litellm/config.yaml` to set your preferred fallback model.

### 3. Create env file

```bash
cat > ~/litellm/.env << EOF
NVIDIA_NIM_API_KEY=nvapi-xxxx
ANTHROPIC_API_KEY=sk-ant-xxxx   # optional
LITELLM_MASTER_KEY=sk-litellm-$(python3 -c "import secrets; print(secrets.token_hex(16))")
EOF
chmod 600 ~/litellm/.env
```

### 4. Start the proxy

```bash
cp systemd/litellm-proxy.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now litellm-proxy
```

### 5. Install switch-backend

```bash
cp bin/switch-backend ~/bin/switch-backend
chmod +x ~/bin/switch-backend

mkdir -p ~/.claude/commands
cp .claude/commands/switch-backend.md ~/.claude/commands/
```

### 6. Wire into your director (optional)

If you have a system-level director service (`monitor-deepresearch.service` or similar), create a drop-in:

```bash
sudo mkdir -p /etc/systemd/system/YOUR-DIRECTOR.service.d/
sudo cp systemd/litellm-dropin.conf /etc/systemd/system/YOUR-DIRECTOR.service.d/litellm.conf
sudo systemctl daemon-reload
sudo systemctl restart YOUR-DIRECTOR
```

---

## Switching backends

```bash
# From terminal
switch-backend nvidia      # → DeepSeek V4 Pro on NVIDIA NIM
switch-backend anthropic   # → Anthropic (Max OAuth or API key)
switch-backend status      # → show current

# From Claude Code
/switch-backend nvidia
/switch-backend anthropic
/switch-backend status
```

---

## Available NVIDIA NIM models

Any model from [integrate.api.nvidia.com](https://integrate.api.nvidia.com) works. Edit `~/litellm/config.yaml` to change. Confirmed working alternatives:

| Model | ID |
|---|---|
| DeepSeek V4 Pro | `deepseek-ai/deepseek-v4-pro` |
| Llama 3.3 70B | `meta/llama-3.3-70b-instruct` |
| Mistral Large | `mistralai/mistral-large` |
| Nemotron Ultra 253B | `nvidia/llama-3.1-nemotron-ultra-253b-v1` |

---

## License

MIT
