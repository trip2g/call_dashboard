import asyncio
import json
import os
import sys
import time
import uuid

sys.path.insert(0, "/opt/hermes")

from aiohttp import web

from agent.auxiliary_client import _build_codex_client

BRIDGE_KEY = os.environ["BRIDGE_KEY"]
LISTEN_PORT = int(os.environ.get("BRIDGE_PORT", "8000"))


def tool_call_dict(tc):
    return {
        "id": tc.id,
        "type": "function",
        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
    }


def merged_system(messages):
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    if len(system) < 2:
        return messages
    text = "\n\n".join(m.get("content") or "" for m in system)
    return [{"role": "system", "content": text}] + rest


def usage_dict(usage):
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", 0) or 0
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}


async def chat_completions(request):
    if request.headers.get("Authorization", "") != "Bearer " + BRIDGE_KEY:
        return web.json_response({"error": {"message": "bad bridge key"}}, status=401)
    body = await request.json()
    model = body.get("model", "")
    client, model = _build_codex_client(model)
    if client is None:
        message = "no Codex login: run `docker compose run --rm hermes auth add openai-codex`"
        return web.json_response({"error": {"message": message}}, status=503)
    kwargs = {"model": model, "messages": merged_system(body.get("messages", []))}
    if body.get("tools"):
        kwargs["tools"] = body["tools"]
    try:
        resp = await asyncio.to_thread(client.chat.completions.create, **kwargs)
    except Exception as exc:
        return web.json_response({"error": {"message": str(exc)}}, status=502)
    choice = resp.choices[0]
    message = {"role": "assistant", "content": choice.message.content}
    if choice.message.tool_calls:
        message["tool_calls"] = [tool_call_dict(tc) for tc in choice.message.tool_calls]
    payload = {
        "id": "chatcmpl-" + uuid.uuid4().hex,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if choice.message.tool_calls else "stop"}],
        "usage": usage_dict(resp.usage),
    }
    return web.json_response(payload)


app = web.Application(client_max_size=16 * 1024 * 1024)
app.router.add_post("/v1/chat/completions", chat_completions)
web.run_app(app, host="0.0.0.0", port=LISTEN_PORT)
