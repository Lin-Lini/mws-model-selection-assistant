from __future__ import annotations

import json
import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from pydantic import ValidationError

from app.adk_runtime import ADKAssistantRuntime
from app.chat_api import make_chat_completion, stream_chunks
from app.config import Settings, configure_logging
from app.memory import SessionStore
from app.mws_client import MwsClient
from app.schemas import ChatCompletionRequest

logger = logging.getLogger(__name__)

class AssistantHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

class AssistantApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.metrics: dict[str, int | float] = {
            "requests_total": 0,
            "mws_fetches": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "response_time_total_ms": 0.0,
        }
        self.cache_store = SessionStore(ttl_seconds=settings.session_ttl_seconds)
        self.mws_client = MwsClient(settings=settings, session_store=self.cache_store, metrics=self.metrics)
        self.runtime = ADKAssistantRuntime(self.mws_client)

    def handle_chat(self, request: ChatCompletionRequest, session_id: str | None) -> tuple[int, str, bool, str]:
        resolved_session_id, content = self.runtime.run_request(request, session_id=session_id)
        return 200, content, request.stream, resolved_session_id

    def metrics_snapshot(self) -> dict[str, int | float]:
        requests_total = int(self.metrics["requests_total"])
        avg = 0.0
        if requests_total:
            avg = float(self.metrics["response_time_total_ms"]) / requests_total
        return {
            **self.metrics,
            "avg_response_time_ms": round(avg, 2),
        }


def create_handler(app: AssistantApp):
    class Handler(BaseHTTPRequestHandler):
        server_version = "mws-model-selector/0.2"

        def _read_json(self) -> dict:
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            if content_length <= 0:
                raise ValueError("пустое тело запроса")
            if content_length > app.settings.max_body_bytes:
                raise OverflowError("тело запроса превышает допустимый размер")
            raw = self.rfile.read(content_length)
            return json.loads(raw.decode("utf-8"))

        def _write_json(self, status: int, payload: dict, session_id: str | None = None) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            if session_id:
                self.send_header("X-Session-Id", session_id)
            self.end_headers()
            self.wfile.write(body)

        def _write_sse(self, status: int, model: str, content: str, session_id: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            if session_id:
                self.send_header("X-Session-Id", session_id)
            self.end_headers()
            for chunk in stream_chunks(model=model, content=content):
                self.wfile.write(chunk)
                self.wfile.flush()

        def _json_error(self, status: int, message: object) -> None:
            self._write_json(status, {"error": {"message": message, "type": "invalid_request_error"}})

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/healthz":
                self._write_json(200, {"status": "ok"})
                return
            if path == "/metrics":
                self._write_json(200, app.metrics_snapshot())
                return
            self._json_error(404, "эндпоинт не найден")

        def do_POST(self) -> None:  # noqa: N802
            started = time.perf_counter()
            app.metrics["requests_total"] = int(app.metrics["requests_total"]) + 1
            path = urlparse(self.path).path

            try:
                if path != "/v1/chat/completions":
                    self._json_error(404, "эндпоинт не найден")
                    return

                session_id = self.headers.get("X-Session-Id")
                payload = self._read_json()
                request = ChatCompletionRequest.model_validate(payload)
                status, content, streaming, resolved_session_id = app.handle_chat(request, session_id=session_id)

                if streaming:
                    self._write_sse(status, request.model, content, session_id=resolved_session_id)
                else:
                    self._write_json(
                        status,
                        make_chat_completion(model=request.model, content=content),
                        session_id=resolved_session_id,
                    )

            except OverflowError:
                self._json_error(413, "тело запроса превышает MAX_BODY_BYTES")
            except json.JSONDecodeError:
                self._json_error(400, "некорректный JSON")
            except ValueError as exc:
                self._json_error(400, str(exc))
            except ValidationError as exc:
                self._json_error(422, exc.errors(include_url=False))
            except Exception as exc:  # pragma: no cover
                logger.exception("необработанная ошибка")
                self._json_error(500, f"внутренняя ошибка: {exc}")
            finally:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                app.metrics["response_time_total_ms"] = float(app.metrics["response_time_total_ms"]) + elapsed_ms

        def log_message(self, fmt: str, *args) -> None:
            logger.info("%s - %s", self.address_string(), fmt % args)

    return Handler


def run_server() -> AssistantHTTPServer:
    settings = Settings()
    configure_logging(settings.log_level)
    app = AssistantApp(settings)
    handler = create_handler(app)
    httpd = AssistantHTTPServer((settings.host, settings.port), handler)
    logger.info("сервис запущен: http://%s:%s", settings.host, settings.port)
    return httpd


def main() -> None:
    httpd = run_server()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()