from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from agent.brief import OutlookBrief
from agent.errors import AgentError, AgentHttpError
from store.settings import Settings, settings

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "gemini": "gemini-2.5-flash",
}
PROVIDERS = frozenset(DEFAULT_MODELS)
T = TypeVar("T", bound=BaseModel)


class AgentClient(Protocol):
    provider: str
    model: str

    def complete(
        self, *, system: str, user: str, schema: type[BaseModel] = OutlookBrief
    ) -> BaseModel: ...


def make_client(
    cfg: Settings | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> AgentClient | None:
    conf = cfg or settings
    chosen = (provider or conf.agent_provider or "").strip().lower()
    if not chosen:
        if conf.anthropic_api_key.strip():
            chosen = "anthropic"
        elif conf.resolved_gemini_key:
            chosen = "gemini"
        else:
            return None
    if chosen not in PROVIDERS:
        raise AgentError(f"unknown agent provider {chosen!r}; use anthropic or gemini")
    name = (model or conf.agent_model or "").strip() or DEFAULT_MODELS[chosen]
    if chosen == "anthropic":
        return AnthropicAgent(conf.anthropic_api_key, model=name)
    return GeminiAgent(conf.resolved_gemini_key, model=name)


class AnthropicAgent:
    """Official Anthropic SDK. Do not call api.anthropic.com with raw httpx."""

    provider = "anthropic"

    def __init__(self, api_key: str, *, model: str) -> None:
        key = api_key.strip()
        if not key:
            raise AgentError("ANTHROPIC_API_KEY is missing")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise AgentError("anthropic SDK is not installed") from exc
        self.model = model
        self._client = Anthropic(api_key=key)

    def complete(
        self, *, system: str, user: str, schema: type[T] = OutlookBrief
    ) -> T:
        output = schema
        try:
            parse = getattr(self._client.messages, "parse", None)
            if parse is not None:
                result = parse(
                    model=self.model,
                    max_tokens=2048,
                    temperature=0.2,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    output_format=output,
                )
                parsed = getattr(result, "parsed_output", None) or getattr(result, "parsed", None)
                if parsed is not None:
                    return output.model_validate(parsed)
            response = self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                temperature=0.2,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except AgentError:
            raise
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            raise AgentHttpError(f"anthropic: {exc}", status_code=status) from exc
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return parse_model(text, output)


class GeminiAgent:
    """Official google-genai SDK. Do not call generativelanguage.googleapis.com with raw httpx."""

    provider = "gemini"

    def __init__(self, api_key: str, *, model: str) -> None:
        key = api_key.strip()
        if not key:
            raise AgentError("GEMINI_API_KEY is missing")
        try:
            from google import genai
        except ImportError as exc:
            raise AgentError("google-genai SDK is not installed") from exc
        self.model = model
        self._client = genai.Client(api_key=key)

    def complete(
        self, *, system: str, user: str, schema: type[T] = OutlookBrief
    ) -> T:
        output = schema
        try:
            payload = self._client.models.generate_content(
                model=self.model,
                contents=user,
                config={
                    "system_instruction": system,
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                    "response_json_schema": output.model_json_schema(),
                    "automatic_function_calling": {"disable": True},
                },
            )
        except AgentError:
            raise
        except Exception as exc:
            raise AgentHttpError(f"gemini: {exc}") from exc
        parsed = getattr(payload, "parsed", None)
        if parsed is not None:
            return output.model_validate(parsed)
        text = getattr(payload, "text", None) or ""
        return parse_model(text, output)


def brief_from_text(text: str) -> OutlookBrief:
    return parse_model(text, OutlookBrief)


def parse_model[U: BaseModel](text: str, schema: type[U]) -> U:
    blob = text.strip()
    if blob.startswith("```"):
        blob = blob.split("\n", 1)[-1]
        if blob.endswith("```"):
            blob = blob[: blob.rfind("```")].strip()
    try:
        return schema.model_validate_json(blob)
    except Exception as exc:
        raise AgentError(f"agent response is not valid {schema.__name__} JSON") from exc
