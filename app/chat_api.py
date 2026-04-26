from __future__ import annotations

import json
import math
import time
import uuid
from typing import Iterable

from app.schemas import ChatCompletionResponse, Choice, Usage



def make_chat_completion(model: str, content: str) -> dict:
    prompt_tokens = max(1, math.ceil(len(content) / 4))
    resp = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=model,
        choices=[Choice(message={"role": "assistant", "content": content})],
        usage=Usage(prompt_tokens=0, completion_tokens=prompt_tokens, total_tokens=prompt_tokens),
    )
    return resp.model_dump(mode="json")



def stream_chunks(model: str, content: str, chunk_size: int = 180) -> Iterable[bytes]:
    response_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    role_chunk = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(role_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
    for i in range(0, len(content), chunk_size):
        piece = content[i : i + chunk_size]
        chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")
    final_chunk = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
    yield b"data: [DONE]\n\n"
