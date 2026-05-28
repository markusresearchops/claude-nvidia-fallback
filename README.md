# Claude Code → NVIDIA NIM Fallback

Route Claude Code agent traffic through a local proxy, with automatic rotation across the strongest **NVIDIA NIM** models as a fallback when your Anthropic Max account hits rate limits.

```
Claude Code agents  (Anthropic SDK /v1/messages format)
      │
      ▼
nim_proxy.py  (localhost:4000)
      │
      ├─ try 1 ──▶ Nemotron Ultra 253B
      ├─ try 2 ──▶ Mistral Large 3 675B   ← rotates on 429 / timeout
      ├─ try 3 ──▶ Qwen 3.5 397B
      ├─ try 4 ──▶ DeepSeek V4 Pro
      └─ try 5 ──▶ Llama 3.3 70B (fast fallback)
```

Models that return 429 or timeout go on a 60-second cooldown; the next available model in the pool is tried automatically. Claude Code never needs to know — it just sees an Anthropic-compatible endpoint.

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
- Linux (systemd) or macOS (launchd)
- Claude Code CLI installed
- API keys:
  - **NVIDIA NIM** — free tier available. Get your key at [build.nvidia.com](https://build.nvidia.com) → sign in → top-right menu → **API Keys** → Generate. The key starts with `nvapi-`.
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

1. Installs `fastapi uvicorn httpx` via pip (lightweight, no heavy deps)
2. Copies `litellm/nim_proxy.py` to `~/litellm/` — the custom rotation proxy
3. Creates `~/litellm/.env` with your API keys (chmod 600)
4. Registers the proxy as a background service (systemd on Linux, launchd on macOS)
5. Installs `~/bin/switch-backend` toggle script
6. Installs `/switch-backend` Claude Code slash command

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

**Linux (systemd):**

```bash
cp systemd/litellm-proxy.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now litellm-proxy
```

**macOS (launchd):**

```bash
# Fill in your username in the plist first
sed "s/YOUR_USERNAME/$(whoami)/g" launchd/com.litellm.proxy.plist \
  > ~/Library/LaunchAgents/com.litellm.proxy.plist

launchctl load ~/Library/LaunchAgents/com.litellm.proxy.plist
launchctl start com.litellm.proxy
```

Logs go to `~/litellm/litellm-proxy.log`. Check with:
```bash
tail -f ~/litellm/litellm-proxy.log
```

To stop/unload:
```bash
launchctl unload ~/Library/LaunchAgents/com.litellm.proxy.plist
```

### 5. Install switch-backend

```bash
mkdir -p ~/bin
cp bin/switch-backend ~/bin/switch-backend
chmod +x ~/bin/switch-backend

# Make sure ~/bin is on your PATH (add to ~/.zshrc or ~/.bashrc if needed):
# export PATH="$HOME/bin:$PATH"

mkdir -p ~/.claude/commands
cp .claude/commands/switch-backend.md ~/.claude/commands/
```

### 6. Wire into Claude Code (all platforms)

Add to your shell profile (`~/.zshrc` on Mac, `~/.bashrc` on Linux):

```bash
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_API_KEY=$(grep LITELLM_MASTER_KEY ~/litellm/.env | cut -d= -f2)
```

Then restart your terminal. Claude Code will now route through LiteLLM → DeepSeek V4 Pro.

To switch back to Anthropic directly:
```bash
unset ANTHROPIC_BASE_URL
unset ANTHROPIC_API_KEY   # or set to your real Anthropic key
```

### 7. Wire into a director service (Linux only, optional)

If you have a system-level director service (`monitor-deepresearch.service` or similar):

```bash
sudo mkdir -p /etc/systemd/system/YOUR-DIRECTOR.service.d/
sudo cp systemd/litellm-dropin.conf /etc/systemd/system/YOUR-DIRECTOR.service.d/litellm.conf
# Edit the file to replace YOUR-USERNAME with your actual username
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
