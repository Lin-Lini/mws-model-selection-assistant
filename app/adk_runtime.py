from __future__ import annotations

import asyncio
import logging
import uuid
from typing import AsyncGenerator

from app.mws_client import MwsClient
from app.recommender import recommend
from app.reports import build_missing_data_prompt, build_report
from app.scenario_parser import parse_messages
from app.schemas import ChatCompletionRequest, ChatMessage
from app.state_codec import (
    recommendations_from_state,
    recommendations_to_state,
    scenario_from_state,
    scenario_to_state,
    snapshot_from_meta,
    snapshot_meta_to_state,
)

logger = logging.getLogger(__name__)

APP_NAME = "mws_model_selector"
DEFAULT_USER_ID = "openai_api_user"

try:  # pragma: no cover - covered in environments with google-adk installed.
    from google.adk.agents import BaseAgent, SequentialAgent
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events import Event, EventActions
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    from pydantic import PrivateAttr

    ADK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in minimal CI sandboxes.
    ADK_AVAILABLE = False


if ADK_AVAILABLE:

    class IntakeAgent(BaseAgent):
        async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
            raw_messages = ctx.session.state.get("openai_messages", [])
            messages = [ChatMessage.model_validate(item) for item in raw_messages]
            incoming = parse_messages(messages)
            previous = scenario_from_state(ctx.session.state.get("scenario"))
            merged = previous.merge(incoming)
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                actions=EventActions(state_delta={"scenario": scenario_to_state(merged)}),
            )

    class CatalogAgent(BaseAgent):
        _mws_client: MwsClient = PrivateAttr()

        def __init__(self, *, name: str, mws_client: MwsClient):
            super().__init__(name=name)
            self._mws_client = mws_client

        async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
            snapshot = self._mws_client.get_catalog(session_id=ctx.session.id)
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                actions=EventActions(state_delta={"catalog_meta": snapshot_meta_to_state(snapshot)}),
            )

    class RecommendationAgent(BaseAgent):
        _mws_client: MwsClient = PrivateAttr()

        def __init__(self, *, name: str, mws_client: MwsClient):
            super().__init__(name=name)
            self._mws_client = mws_client

        async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
            scenario = scenario_from_state(ctx.session.state.get("scenario"))
            if not scenario.has_minimum_for_costing:
                yield Event(
                    author=self.name,
                    invocation_id=ctx.invocation_id,
                    branch=ctx.branch,
                    actions=EventActions(
                        state_delta={
                            "recommendations": [],
                            "needs_clarification": True,
                            "clarification_prompt": build_missing_data_prompt(scenario),
                        }
                    ),
                )
                return

            snapshot = self._mws_client.get_catalog(session_id=ctx.session.id)
            recommendations = recommend(snapshot, scenario)
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                actions=EventActions(
                    state_delta={
                        "recommendations": recommendations_to_state(recommendations),
                        "needs_clarification": False,
                        "clarification_prompt": None,
                    }
                ),
            )

    class ReportAgent(BaseAgent):
        _mws_client: MwsClient = PrivateAttr()

        def __init__(self, *, name: str, mws_client: MwsClient):
            super().__init__(name=name)
            self._mws_client = mws_client

        async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
            scenario = scenario_from_state(ctx.session.state.get("scenario"))
            if ctx.session.state.get("needs_clarification"):
                content = str(ctx.session.state.get("clarification_prompt") or build_missing_data_prompt(scenario))
            else:
                snapshot = self._mws_client.get_catalog(session_id=ctx.session.id)
                meta = ctx.session.state.get("catalog_meta") or snapshot_meta_to_state(snapshot)
                snapshot_for_report = snapshot_from_meta(meta, snapshot.models)
                recommendations = recommendations_from_state(ctx.session.state.get("recommendations"))
                content = build_report(scenario, recommendations, snapshot_for_report)

            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                actions=EventActions(state_delta={"final_report": content}),
                content=types.Content(role="assistant", parts=[types.Part.from_text(text=content)]),
                turn_complete=True,
            )

    class ADKAssistantRuntime:
        def __init__(self, mws_client: MwsClient):
            self.mws_client = mws_client
            self.root_agent = SequentialAgent(
                name="MwsModelSelectionWorkflow",
                description="Последовательный ADK-сценарий: разбор вводных, получение актуального каталога MWS, подбор моделей и формирование отчёта.",
                sub_agents=[
                    IntakeAgent(name="IntakeAgent"),
                    CatalogAgent(name="CatalogAgent", mws_client=mws_client),
                    RecommendationAgent(name="RecommendationAgent", mws_client=mws_client),
                    ReportAgent(name="ReportAgent", mws_client=mws_client),
                ],
            )
            self.runner = InMemoryRunner(agent=self.root_agent, app_name=APP_NAME)

        async def _ensure_session(self, *, session_id: str, user_id: str) -> None:
            session = await self.runner.session_service.get_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )
            if session is None:
                await self.runner.session_service.create_session(
                    app_name=APP_NAME,
                    user_id=user_id,
                    session_id=session_id,
                )

        @staticmethod
        def _last_user_text(request: ChatCompletionRequest) -> str:
            for msg in reversed(request.messages):
                if msg.role == "user":
                    return msg.content
            return request.messages[-1].content

        async def run_request_async(self, request: ChatCompletionRequest, session_id: str | None) -> tuple[str, str]:
            resolved_session_id = session_id or f"ephemeral-{uuid.uuid4().hex}"
            user_id = request.user or DEFAULT_USER_ID
            await self._ensure_session(session_id=resolved_session_id, user_id=user_id)
            new_message = types.Content(role="user", parts=[types.Part.from_text(text=self._last_user_text(request))])
            state_delta = {
                "openai_messages": [message.model_dump(mode="json") for message in request.messages],
                "request_model": request.model,
            }
            final_content: str | None = None
            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=resolved_session_id,
                new_message=new_message,
                state_delta=state_delta,
            ):
                if event.content and event.content.parts:
                    text = "".join(part.text or "" for part in event.content.parts if getattr(part, "text", None))
                    if text:
                        final_content = text
            if final_content is None:
                raise RuntimeError("ADK-сценарий завершился без финального сообщения ассистента")
            return resolved_session_id, final_content

        def run_request(self, request: ChatCompletionRequest, session_id: str | None) -> tuple[str, str]:
            return asyncio.run(self.run_request_async(request, session_id=session_id))

else:

    class ADKAssistantRuntime:
        """Small deterministic fallback for local test sandboxes without google-adk installed.

        The production path above is used automatically when the required google-adk
        dependency from requirements.txt is available.
        """

        def __init__(self, mws_client: MwsClient):
            self.mws_client = mws_client
            self._scenarios: dict[str, dict] = {}

        def run_request(self, request: ChatCompletionRequest, session_id: str | None) -> tuple[str, str]:
            resolved_session_id = session_id or f"ephemeral-{uuid.uuid4().hex}"
            incoming = parse_messages(request.messages)
            previous = scenario_from_state(self._scenarios.get(resolved_session_id))
            scenario = previous.merge(incoming)
            self._scenarios[resolved_session_id] = scenario_to_state(scenario)

            snapshot = self.mws_client.get_catalog(session_id=resolved_session_id)
            if not scenario.has_minimum_for_costing:
                return resolved_session_id, build_missing_data_prompt(scenario)

            recommendations = recommend(snapshot, scenario)
            return resolved_session_id, build_report(scenario, recommendations, snapshot)
