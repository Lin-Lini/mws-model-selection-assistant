from __future__ import annotations

import json
import os
import socket
import threading
import time
from contextlib import closing
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


def test_embeddings_request_is_parsed() -> None:
    with ServerCtx() as base_url:
        payload = {
            "model": "mws-model-selector",
            "messages": [
                {
                    "role": "user",
                    "content": "Нужны эмбеддинги для поиска по базе знаний. 300000 текстов в месяц. В среднем 700 токенов на документ. Нужен недорогой вариант.",
                }
            ],
            "stream": False,
        }
        req = Request(
            f"{base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            txt = body["choices"][0]["message"]["content"]
            assert "эмбеддинг" in txt.lower()
            assert "bge-m3" in txt.lower() or "bge-multilingual-gemma2" in txt.lower()
