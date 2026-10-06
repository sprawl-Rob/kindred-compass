"""Provider adapters behind one task interface.

OpenAI and Anthropic differ in model discovery, capability reporting, request
shape, structured-output syntax, and errors, so each has its own adapter.
Shapes follow the current official SDKs (openai 3.x Responses API; anthropic 1.x
Messages API) as documented at:
  https://developers.openai.com/api/docs  (models.list, responses.create)
  https://platform.claude.com/docs/en/api/models/list  (capabilities on ModelInfo)
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

PROVIDERS = {"openai": "OpenAI", "anthropic": "Anthropic"}

# Substrings of model ids that the OpenAI list returns for non-text-generation models.
# This is a heuristic used only to *label* models; the user can still pick any model.
OPENAI_NON_TEXT_HINTS = ("embedding", "tts", "whisper", "dall-e", "moderation", "transcribe", "audio", "realtime", "image", "sora", "search-api")


class AIError(Exception):
    """Normalised provider error with an actionable message."""

    def __init__(self, code: str, message: str, retryable: bool = False, status: int | None = None, provider: str | None = None):
        super().__init__(message)
        self.code, self.message, self.retryable, self.status, self.provider = code, message, retryable, status, provider

    def to_dict(self):
        return {"code": self.code, "message": self.message, "retryable": self.retryable, "status": self.status}


@dataclass
class GenerateRequest:
    model: str
    instructions: str
    text: str
    schema: dict | None = None
    schema_name: str = "result"
    images: list[tuple[str, bytes]] = field(default_factory=list)   # (mime, bytes)
    pdfs: list[bytes] = field(default_factory=list)
    max_output_tokens: int = 4000
    effort: str | None = None


@dataclass
class GenerateResult:
    text: str
    parsed: Any
    input_tokens: int | None
    output_tokens: int | None
    stop_reason: str | None
    model: str


def _status_of(e) -> int | None:
    return getattr(e, "status_code", None)


def normalise_error(e: Exception, provider: str, model: str | None = None) -> AIError:
    name = type(e).__name__
    status = _status_of(e)
    label = PROVIDERS.get(provider, provider)
    body_code = getattr(e, "code", None)
    msg = str(getattr(e, "message", "") or e)
    if isinstance(e, AIError):
        return e
    if name == "APITimeoutError":
        return AIError("timeout", f"{label} did not respond before the timeout. Try again, raise the timeout in AI Settings, or shorten the input.", True, None, provider)
    if name == "APIConnectionError":
        return AIError("network", f"Could not reach {label}. Check your internet connection.", True, None, provider)
    if status == 401 or name == "AuthenticationError":
        return AIError("auth", f"{label} rejected the API key. Re-enter it in AI Settings.", False, status, provider)
    if status == 402:
        return AIError("billing", f"{label} reported a billing problem for this account.", False, status, provider)
    if status == 403 or name == "PermissionDeniedError":
        return AIError("permission", f"This {label} key does not have access to this model or feature.", False, status, provider)
    if status == 404 or name == "NotFoundError":
        return AIError("model_unavailable", f"{label} says model “{model}” was not found or is not available to this account. "
                                            "Refresh the model list or pick another model.", False, status, provider)
    if status == 413 or name == "RequestTooLargeError":
        return AIError("too_large", "The request is too large for this provider. Send fewer sources or a shorter document.", False, status, provider)
    if status == 429 or name == "RateLimitError":
        if body_code == "insufficient_quota":
            return AIError("quota", f"{label} reports the account's quota or spend limit is exhausted.", False, status, provider)
        return AIError("rate_limit", f"{label} rate limit reached. Wait a minute and try again.", True, status, provider)
    if status == 400:
        low = msg.lower()
        if body_code == "context_length_exceeded" or "context" in low and "length" in low or "prompt is too long" in low or "too many tokens" in low:
            return AIError("context_limit", "The input is longer than this model's context window. Send fewer sources or use a model with a larger context.", False, status, provider)
        if any(s in low for s in ("json_schema", "response_format", "text.format", "output_config", "structured", "reasoning", "effort", "not supported", "unsupported")):
            return AIError("incompatible_model", f"Model “{model}” rejected a required feature (structured output, reasoning effort, or an input type). "
                                                 f"Choose a different model for this task. Provider message: {msg[:300]}", False, status, provider)
        return AIError("bad_request", f"{label} rejected the request: {msg[:300]}", False, status, provider)
    if status in (500, 502, 503, 504, 529) or name in ("InternalServerError", "OverloadedError", "ServiceUnavailableError", "DeadlineExceededError"):
        return AIError("provider_unavailable", f"{label} is temporarily unavailable or overloaded. Try again shortly.", True, status, provider)
    return AIError("unknown", f"Unexpected error from {label}: {msg[:300]}", False, status, provider)


def _dump(obj) -> dict:
    for attr in ("to_dict", "model_dump"):
        fn = getattr(obj, attr, None)
        if fn:
            try:
                return fn()
            except TypeError:
                pass
    return dict(obj) if isinstance(obj, dict) else {}


def _parse_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise AIError("bad_output", "The model returned output that is not valid JSON for this task. Try again or choose another model.")


# ---------------------------------------------------------------- OpenAI

def default_openai_client(api_key: str, timeout: float):
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=1)


class OpenAIAdapter:
    name = "openai"

    def __init__(self, api_key: str, timeout: float = 120, client_factory: Callable | None = None):
        self.client = (client_factory or default_openai_client)(api_key, timeout)

    @staticmethod
    def describe(m: dict) -> dict:
        mid = m.get("id", "")
        non_text = any(h in mid for h in OPENAI_NON_TEXT_HINTS)
        return {"id": mid, "display_name": mid, "provider": "openai", "created": m.get("created"), "owned_by": m.get("owned_by"),
                "capability_source": "not_reported",
                "capabilities": {"structured_outputs": None, "image_input": None, "pdf_input": None, "effort_levels": None,
                                 "max_input_tokens": None, "max_output_tokens": None},
                "likely_text_model": not non_text,
                "note": ("OpenAI's model list does not report capabilities. Structured output, image input and reasoning effort "
                         "are checked when a request runs.") + (" The id suggests this is not a text-generation model." if non_text else "")}

    async def list_models(self) -> list[dict]:
        try:
            out = [self.describe(_dump(m)) async for m in self.client.models.list()]
        except Exception as e:
            raise normalise_error(e, "openai")
        return sorted(out, key=lambda m: (not m["likely_text_model"], -(m.get("created") or 0)))

    async def retrieve_model(self, model_id: str) -> dict:
        try:
            return self.describe(_dump(await self.client.models.retrieve(model_id)))
        except Exception as e:
            raise normalise_error(e, "openai", model_id)

    async def generate(self, req: GenerateRequest) -> GenerateResult:
        content: list[dict] = [{"type": "input_text", "text": req.text}]
        for mime, data in req.images:
            content.append({"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(data).decode()}"})
        if req.pdfs:
            raise AIError("incompatible_model", "PDF input is not enabled for OpenAI in this app; attach page images instead.")
        kwargs: dict[str, Any] = {
            "model": req.model, "instructions": req.instructions, "input": [{"role": "user", "content": content}],
            "max_output_tokens": req.max_output_tokens, "store": False,
        }
        if req.schema:
            kwargs["text"] = {"format": {"type": "json_schema", "name": req.schema_name, "schema": req.schema, "strict": True}}
        if req.effort:
            kwargs["reasoning"] = {"effort": req.effort}
        try:
            r = await self.client.responses.create(**kwargs)
        except Exception as e:
            raise normalise_error(e, "openai", req.model)
        status = getattr(r, "status", None)
        if status == "incomplete":
            reason = getattr(getattr(r, "incomplete_details", None), "reason", None)
            raise AIError("output_limit" if reason == "max_output_tokens" else "incomplete",
                          "The model stopped before finishing (output limit reached). Raise the output limit or send less input."
                          if reason == "max_output_tokens" else f"The response was incomplete ({reason}).")
        text = getattr(r, "output_text", "") or ""
        usage = getattr(r, "usage", None)
        return GenerateResult(text, _parse_json(text) if req.schema else None,
                              getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None), status, getattr(r, "model", req.model))


# ---------------------------------------------------------------- Anthropic

def default_anthropic_client(api_key: str, timeout: float):
    from anthropic import AsyncAnthropic
    return AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=1)


def _supported(node) -> bool | None:
    if isinstance(node, dict):
        return node.get("supported")
    return None


class AnthropicAdapter:
    name = "anthropic"

    def __init__(self, api_key: str, timeout: float = 120, client_factory: Callable | None = None):
        self.client = (client_factory or default_anthropic_client)(api_key, timeout)

    @staticmethod
    def describe(m: dict) -> dict:
        caps = m.get("capabilities")
        if isinstance(caps, dict):
            eff = caps.get("effort") or {}
            levels = [lvl for lvl in ("low", "medium", "high", "xhigh", "max") if _supported(eff.get(lvl))] if _supported(eff) else []
            c = {"structured_outputs": _supported(caps.get("structured_outputs")), "image_input": _supported(caps.get("image_input")),
                 "pdf_input": _supported(caps.get("pdf_input")), "effort_levels": levels,
                 "max_input_tokens": m.get("max_input_tokens"), "max_output_tokens": m.get("max_tokens")}
            src = "provider"
        else:
            c = {"structured_outputs": None, "image_input": None, "pdf_input": None, "effort_levels": None,
                 "max_input_tokens": m.get("max_input_tokens"), "max_output_tokens": m.get("max_tokens")}
            src = "not_reported"
        return {"id": m.get("id"), "display_name": m.get("display_name") or m.get("id"), "provider": "anthropic",
                "created": str(m.get("created_at")) if m.get("created_at") else None, "capability_source": src, "capabilities": c,
                "likely_text_model": True, "note": None if src == "provider" else "Capabilities not reported for this model."}

    async def list_models(self) -> list[dict]:
        try:
            out = [self.describe(_dump(m)) async for m in self.client.models.list(limit=1000)]
        except Exception as e:
            raise normalise_error(e, "anthropic")
        return out

    async def retrieve_model(self, model_id: str) -> dict:
        try:
            return self.describe(_dump(await self.client.models.retrieve(model_id)))
        except Exception as e:
            raise normalise_error(e, "anthropic", model_id)

    async def generate(self, req: GenerateRequest) -> GenerateResult:
        content: list[dict] = []
        for data in req.pdfs:
            content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}})
        for mime, data in req.images:
            content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(data).decode()}})
        content.append({"type": "text", "text": req.text})
        output_config: dict[str, Any] = {}
        if req.schema:
            output_config["format"] = {"type": "json_schema", "schema": req.schema}
        if req.effort:
            output_config["effort"] = req.effort
        kwargs: dict[str, Any] = {"model": req.model, "max_tokens": req.max_output_tokens, "system": req.instructions,
                                  "messages": [{"role": "user", "content": content}]}
        if output_config:
            kwargs["output_config"] = output_config
        try:
            r = await self.client.messages.create(**kwargs)
        except Exception as e:
            raise normalise_error(e, "anthropic", req.model)
        stop = getattr(r, "stop_reason", None)
        if stop == "refusal":
            raise AIError("refusal", "The model declined this request. Nothing was changed.")
        if stop == "max_tokens":
            raise AIError("output_limit", "The model stopped before finishing (output limit reached). Raise the output limit or send less input.")
        if stop == "model_context_window_exceeded":
            raise AIError("context_limit", "The input plus requested output exceeds this model's context window. Send fewer sources.")
        text = "".join(getattr(b, "text", "") for b in getattr(r, "content", []) if getattr(b, "type", None) == "text")
        usage = getattr(r, "usage", None)
        return GenerateResult(text, _parse_json(text) if req.schema else None,
                              getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None), stop, getattr(r, "model", req.model))


ADAPTERS = {"openai": OpenAIAdapter, "anthropic": AnthropicAdapter}


def make_adapter(provider: str, api_key: str, timeout: float, factories: dict | None = None):
    if provider not in ADAPTERS:
        raise AIError("unknown_provider", f"Unknown provider {provider}")
    factory = (factories or {}).get(provider)
    return ADAPTERS[provider](api_key, timeout, factory)


def elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
