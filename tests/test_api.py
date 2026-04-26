from __future__ import annotations

import json
import os
import socket
import threading
import time
from contextlib import closing
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.server import run_server



def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ServerCtx:
    def __init__(self) -> None:
        self.thread = None
        self.httpd = None
        self.old_env = dict(os.environ)

    def __enter__(self):
        port = _free_port()
        os.environ["HOST"] = "127.0.0.1"
        os.environ["PORT"] = str(port)
        os.environ["MWS_FIXTURE_DIR"] = "tests/fixtures/mws"
        self.httpd = run_server()
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.1)
        return f"http://127.0.0.1:{port}"

    def __exit__(self, exc_type, exc, tb):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        os.environ.clear()
        os.environ.update(self.old_env)


def test_empty_body_returns_400() -> None:
    with ServerCtx() as base_url:
        req = Request(
            f"{base_url}/v1/chat/completions",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(req)
            assert False, "ожидался 400"
        except HTTPError as e:
            assert e.code == 400
            body = json.loads(e.read().decode("utf-8"))
            assert body["error"]["message"] == "пустое тело запроса"


def test_chat_completion_nonstream() -> None:
    with ServerCtx() as base_url:
        payload = {
            "model": "mws-model-selector",
            "messages": [{"role": "user", "content": "Нужен чат-ассистент. 100 запросов в день. 1000 входящих и 300 исходящих токенов. Бюджет 5000 ₽."}],
            "stream": False,
        }
        req = Request(
            f"{base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Session-Id": "api-1"},
            method="POST",
        )
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        assert data["object"] == "chat.completion"
        assert "Рекомендованные модели" in data["choices"][0]["message"]["content"]


def test_chat_completion_stream() -> None:
    with ServerCtx() as base_url:
        payload = {
            "model": "mws-model-selector",
            "messages": [{"role": "user", "content": "Нужен мультимодальный ассистент с изображениями. 50 запросов в день. 1500 входящих и 500 исходящих токенов. Бюджет 8000 ₽."}],
            "stream": True,
        }
        req = Request(
            f"{base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            text = resp.read().decode("utf-8")
        assert "data: [DONE]" in text
        assert "chat.completion.chunk" in text


def test_followup_session_merges_previous_inputs() -> None:
    with ServerCtx() as base_url:
        first = {
            "model": "mws-model-selector",
            "messages": [{"role": "user", "content": "Нужен чат-ассистент. 100 запросов в день. 1000 входящих и 300 исходящих токенов."}],
            "stream": False,
        }
        req1 = Request(
            f"{base_url}/v1/chat/completions",
            data=json.dumps(first).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Session-Id": "followup-1"},
            method="POST",
        )
        with urlopen(req1) as resp1:
            body1 = json.loads(resp1.read().decode("utf-8"))
        text1 = body1["choices"][0]["message"]["content"]
        assert "Рекомендованные модели" in text1
        assert "Бюджет: н/д / месяц" in text1

        second = {
            "model": "mws-model-selector",
            "messages": [{"role": "user", "content": "Бюджет 7000 ₽ в месяц. Нужен баланс цены и качества."}],
            "stream": False,
        }
        req2 = Request(
            f"{base_url}/v1/chat/completions",
            data=json.dumps(second).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Session-Id": "followup-1"},
            method="POST",
        )
        with urlopen(req2) as resp2:
            body2 = json.loads(resp2.read().decode("utf-8"))
        text2 = body2["choices"][0]["message"]["content"]
        assert "Рекомендованные модели" in text2
        assert "7 000.00 ₽" in text2
