"""
Minimal Anthropic-compatible proxy → NVIDIA NIM with model rotation.

Listens on :4000, accepts /v1/messages (Anthropic SDK format),
translates to OpenAI chat/completions, rotates through NIM models
on 429/503/timeout, returns Anthropic-format response.
"""
import asyncio, json, os, time, logging
from collections import defaultdict
from typing import Optional
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nim_proxy")

NVIDIA_API_KEY = os.environ["NVIDIA_NIM_API_KEY"]
NIM_BASE = "https://integrate.api.nvidia.com/v1"
PORT = int(os.environ.get("NIM_PROXY_PORT", "4000"))

# Rotation pool — ordered by preference
MODELS = [
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "mistralai/mistral-large-3-675b-instruct-2512",
    "qwen/qwen3.5-397b-a17b",
    "deepseek-ai/deepseek-v4-pro",
    "meta/llama-3.3-70b-instruct",   # fast fallback
]

# Cooldown tracking: model → time when it becomes available again
_cooldown: dict[str, float] = defaultdict(float)
COOLDOWN_SECS = 60

app = FastAPI()


def _available_models() -> list[str]:
    now = time.time()
    available = [m for m in MODELS if now >= _cooldown[m]]
    return available or MODELS  # if all cooled down, try anyway


def _set_cooldown(model: str):
    _cooldown[model] = time.time() + COOLDOWN_SECS
    log.info("Cooldown set for %s (60s)", model)


def _anthropic_to_openai(body: dict) -> dict:
    """Translate Anthropic /v1/messages request to OpenAI chat/completions."""
    messages = []
    if system := body.get("system"):
        if isinstance(system, str):
            messages.append({"role": "system", "content": system})
        elif isinstance(system, list):
            text = " ".join(b.get("text", "") for b in system if b.get("type") == "text")
            messages.append({"role": "system", "content": text})

    for m in body.get("messages", []):
        role = m["role"]
        content = m["content"]
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content if b.get("type") == "text"
            )
            messages.append({"role": role, "content": text})

    payload: dict = {
        "messages": messages,
        "max_tokens": body.get("max_tokens", 4096),
        "stream": body.get("stream", False),
    }
    if temp := body.get("temperature"):
        payload["temperature"] = temp
    if stop := body.get("stop_sequences"):
        payload["stop"] = stop
    if tools := body.get("tools"):
        # translate Anthropic tool format to OpenAI
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in tools
        ]
    return payload


def _openai_to_anthropic(oai: dict, model: str) -> dict:
    """Translate OpenAI response to Anthropic /v1/messages format."""
    choice = oai["choices"][0]
    msg = choice["message"]
    content = []

    if text := msg.get("content"):
        content.append({"type": "text", "text": text})

    if calls := msg.get("tool_calls"):
        for c in calls:
            content.append({
                "type": "tool_use",
                "id": c["id"],
                "name": c["function"]["name"],
                "input": json.loads(c["function"].get("arguments", "{}")),
            })

    stop_reason_map = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "content_filter": "stop_sequence",
    }
    stop_reason = stop_reason_map.get(choice.get("finish_reason", "stop"), "end_turn")

    usage = oai.get("usage", {})
    return {
        "id": oai.get("id", "msg_nim"),
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    oai_payload = _anthropic_to_openai(body)
    is_stream = oai_payload.get("stream", False)

    async with httpx.AsyncClient(timeout=180) as client:
        for model in _available_models():
            oai_payload["model"] = model
            try:
                if is_stream:
                    return await _stream(client, oai_payload, model)
                resp = await client.post(
                    f"{NIM_BASE}/chat/completions",
                    json=oai_payload,
                    headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                )
                if resp.status_code in (429, 503, 502):
                    _set_cooldown(model)
                    log.warning("%s → %s, rotating", model, resp.status_code)
                    continue
                resp.raise_for_status()
                oai_resp = resp.json()
                return JSONResponse(_openai_to_anthropic(oai_resp, model))
            except httpx.TimeoutException:
                _set_cooldown(model)
                log.warning("%s → timeout, rotating", model)
            except Exception as e:
                _set_cooldown(model)
                log.warning("%s → %s, rotating", model, e)

    return JSONResponse(
        {"type": "error", "error": {"type": "overloaded_error",
         "message": "All NIM models exhausted or on cooldown"}},
        status_code=529,
    )


async def _stream(client: httpx.AsyncClient, payload: dict, model: str):
    async def gen():
        # Send stream-start event
        yield f"event: message_start\ndata: {json.dumps({'type':'message_start','message':{'id':'msg_nim','type':'message','role':'assistant','model':model,'content':[],'stop_reason':None,'stop_sequence':None,'usage':{'input_tokens':0,'output_tokens':0}}})}\n\n"
        yield "event: content_block_start\ndata: {\"type\":\"content_block_start\",\"index\":0,\"content_block\":{\"type\":\"text\",\"text\":\"\"}}\n\n"
        try:
            async with client.stream(
                "POST", f"{NIM_BASE}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    if text := delta.get("content"):
                        yield f"event: content_block_delta\ndata: {json.dumps({'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':text}})}\n\n"
        except Exception as e:
            log.error("stream error: %s", e)
        yield "event: content_block_stop\ndata: {\"type\":\"content_block_stop\",\"index\":0}\n\n"
        yield "event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/health/liveliness")
async def health():
    return {"status": "ok", "models": _available_models()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
