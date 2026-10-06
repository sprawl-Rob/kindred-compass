# OpenAI + Anthropic integration reference (researched 2026-10-05)

All facts below were fetched from official sources on 2026-10-05. The URL is given next to each section.
Caveat: some OpenAI pages were read through a summarizer (platform.openai.com returned 403, so I used developers.openai.com plus the openai-python source on GitHub). Where the SDK source and the docs agree, that is noted.

---

## OPENAI

### 1. Model listing
Sources: https://developers.openai.com/api/reference/resources/models/methods/list ,
https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/model.py ,
https://raw.githubusercontent.com/openai/openai-python/main/src/openai/resources/models.py

- `GET https://api.openai.com/v1/models` returns `{"object": "list", "data": [Model, ...]}`
- Model fields: `id` (str), `created` (unix seconds, int), `object` ("model"), `owned_by` (str), `shutdown_date` (str | null, new: set if a shutdown has been announced)
- **There is no capability info**: no context window, modalities, structured-output or reasoning support. The list also includes non-chat models (embeddings, tts, image, moderation, and others), so filtering has to be heuristic or a curated allow-list.
- **No pagination**. The SDK `client.models.list()` returns `SyncPage[Model]` (not a cursor page) and takes no `limit`/`after` parameters.
- `GET /v1/models/{model}` lets you validate a manually entered id: `client.models.retrieve("gpt-5.5")`. An unknown id or one you can't access raises `NotFoundError` (404).

```python
from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=key, timeout=60.0, max_retries=2)
page = await client.models.list()
ids = [m.id for m in page.data]          # m.id, m.created, m.owned_by, m.shutdown_date
m = await client.models.retrieve("gpt-5.5")  # NotFoundError if bad/no access
```

### 2. Generation API: Responses (recommended)
Sources: https://developers.openai.com/api/docs/guides/migrate-to-responses ("Responses is recommended for all new projects"; Chat Completions still supported, not deprecated),
https://raw.githubusercontent.com/openai/openai-python/main/README.md ,
https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_create_params.py ,
.../responses/response_format_text_json_schema_config_param.py , .../shared_params/reasoning.py , .../shared/reasoning_effort.py , .../responses/response_usage.py ,
https://developers.openai.com/api/docs/guides/structured-outputs , https://developers.openai.com/api/docs/guides/reasoning

Request params on `POST /v1/responses` / `client.responses.create(...)`:
- `model`: str
- `input`: str, or a list of input items (`[{"role": "user", "content": "..."}]`)
- `instructions`: str. This is the system/developer message, and it is not carried over when you chain with `previous_response_id`. You can also put `{"role": "developer", ...}` items inside `input`.
- `max_output_tokens`: int. It caps output **including reasoning tokens**.
- `text`: `{"format": {...}, "verbosity": "low"|"medium"|"high"}`
  - Structured output: `text={"format": {"type": "json_schema", "name": "<a-zA-Z0-9_- ≤64>", "schema": {...}, "strict": True, "description": "optional"}}`. `type`, `name` and `schema` are required.
  - Strict schema rules: every object must have `additionalProperties: false` and list **all** fields in `required`. `$ref` and recursion are supported.
  - Other formats: `{"type": "text"}` (the default) and `{"type": "json_object"}` (legacy JSON mode)
- `reasoning`: `{"effort": ..., "summary": "auto"|"concise"|"detailed"}` (it also has `mode`: "standard"|"pro" and `context`)
  - The SDK type allows these `effort` values: `"none","minimal","low","medium","high","xhigh","max"`. Support differs by model, per the reasoning guide:
    - gpt-6-astra: minimal..max, and `none` returns HTTP 400
    - gpt-6.1-sol: medium, high, xhigh, max (default medium)
    - gpt-5.6 family, gpt-5.5: minimal..max (default medium)
    - Reasoning models listed: gpt-6-astra, gpt-6.1-sol, gpt-6-sol, gpt-6-luna, gpt-5.6-{terra,luna,sol}, gpt-5.5, gpt-5.4
  - Chat Completions uses a flat `reasoning_effort` instead.
- Other params: `temperature`, `top_p`, `store` (defaults to true; set `store=False` to avoid server retention), `truncation` ("auto"|"disabled"), `previous_response_id`, `service_tier`, `safety_identifier`, `prompt_cache_key`.

Response:
- `response.output_text`: SDK convenience that concatenates the text output
- `response.status`: "completed" | "incomplete" | "in_progress" | ...; `response.incomplete_details.reason`, e.g. `"max_output_tokens"`. The reasoning guide warns this can happen before any visible text is produced.
- `response.output`: list of items (reasoning, message, tool calls). A refusal appears as a `refusal` content part instead of schema output.
- `response.usage`: `input_tokens`, `input_tokens_details.cached_tokens`, `input_tokens_details.cache_write_tokens`, `output_tokens`, `output_tokens_details.reasoning_tokens`, `total_tokens`
- `response.error`: an error object, or null

```python
resp = await client.responses.create(
    model="gpt-5.5",
    instructions="You are ...",
    input="user text",
    max_output_tokens=4000,
    reasoning={"effort": "low"},           # only for reasoning models
    text={"format": {"type": "json_schema", "name": "result", "strict": True,
                     "schema": {"type": "object", "properties": {"a": {"type": "string"}},
                                "required": ["a"], "additionalProperties": False}}},
    store=False,
)
if resp.status == "incomplete": reason = resp.incomplete_details.reason
text = resp.output_text
u = resp.usage  # u.input_tokens, u.output_tokens, u.output_tokens_details.reasoning_tokens,
                # u.input_tokens_details.cached_tokens, u.total_tokens
```
SDK helper: `client.responses.parse(..., text_format=PydanticModel)` gives you `resp.output_parsed`.

Chat Completions equivalents: `messages=[{"role":"developer"|"system",...},{"role":"user",...}]`, `max_completion_tokens`, `response_format={"type":"json_schema","json_schema":{name,schema,strict}}`, `reasoning_effort`. Output is in `choices[0].message.content`, and usage is in `usage.prompt_tokens`, `usage.completion_tokens`, `usage.total_tokens`. Per the reasoning guide, Chat Completions doesn't support function calling on gpt-6-astra or gpt-6.1-sol.

### 3. Errors
Sources: https://developers.openai.com/api/docs/guides/error-codes , https://raw.githubusercontent.com/openai/openai-python/main/src/openai/_exceptions.py , README

| HTTP | Meaning | SDK class |
|---|---|---|
| 400 | malformed / invalid params; **context too long** (`code: "context_length_exceeded"`, `type: "invalid_request_error"`) | `BadRequestError` |
| 401 | invalid/incorrect API key, not member of org, IP not allowlisted | `AuthenticationError` (subclass `OAuthError`) |
| 403 | unsupported country/region; no access to resource | `PermissionDeniedError` |
| 404 | resource or **model not found / no access** (`code` typically `model_not_found`) | `NotFoundError` |
| 409 | conflict | `ConflictError` |
| 422 | unprocessable | `UnprocessableEntityError` |
| 429 | rate limit reached, **or** quota/credits exhausted, or org/project spend limit reached (look at `e.code`, e.g. `insufficient_quota`, to tell them apart; quota errors are not worth retrying) | `RateLimitError` |
| ≥500 / 503 | server error / model overloaded | `InternalServerError` |
| — | network failure | `APIConnectionError` |
| — | timeout | `APITimeoutError` (subclass of APIConnectionError) |

- Base classes: `openai.APIError` → `APIStatusError` (has `.status_code`, `.response`, `.request_id`, `.body`, `.code`, `.param`, `.type`).
- `context_length_exceeded` is confirmed by observed API payloads (for example https://github.com/langchain-ai/langchain/issues/16781 and https://github.com/openai/codex/issues/48870). The official error-codes page doesn't enumerate it, so match on `e.code` defensively.

### 4. SDK version / config
Sources: https://pypi.org/pypi/openai/json , README
- Latest **openai 3.24.0**, `requires_python >=3.10`, classifiers 3.10 through **3.14** (so 3.14 is supported).
- Defaults are `timeout` = 10 minutes and `max_retries` = 2. Connection errors, 408, 409, 429 and 5xx are retried with backoff.
- `OpenAI(timeout=20.0, max_retries=0)`; per request: `client.with_options(timeout=5.0, max_retries=5).responses.create(...)`. `timeout` also accepts an `httpx2.Timeout` (the SDK's HTTP layer is now `httpx2`, as the signatures in resources/models.py show).

### 5. Pricing
- Official page: https://developers.openai.com/api/docs/pricing (https://openai.com/api/pricing also exists). **No machine-readable pricing API/JSON/CSV** (confirmed). The page only offers a `.md` rendering, and the Models API has no price fields.

---

## ANTHROPIC

### 6. Model listing
Sources: https://platform.claude.com/docs/en/api/models/list , https://platform.claude.com/docs/en/api/models/retrieve

- `GET https://api.anthropic.com/v1/models`. Headers: `x-api-key: <key>`, `anthropic-version: 2023-06-01`. Optional: `anthropic-workspace-id`. The `anthropic-beta` header is deprecated on this endpoint.
- Query params (cursor pagination): `limit` (default 20, range 1–1000), `after_id`, `before_id`. Newest models come first.
- Response: `{"data": [ModelInfo], "first_id", "last_id", "has_more"}`. For the next page, pass `after_id=last_id` while `has_more` is true. The SDK auto-paginates: `for m in client.models.list(limit=100)` / `async for`.
- **ModelInfo fields (capability info now exists):**
  - `type` ("model"), `id`, `display_name`, `created_at` (RFC 3339; may be epoch if unknown)
  - `line`: "haiku"|"sonnet"|"opus"|"fable"|"mythos"|null. Don't infer it from the id.
  - `max_input_tokens`: int|null, the context window
  - `max_tokens`: int|null, the max allowed value of the `max_tokens` request param
  - `capabilities`: object|null. Each leaf is `{"supported": bool}`:
    - `batch`, `citations`, `code_execution`, `image_input`, `pdf_input`, `structured_outputs`
    - `context_management`: `{supported, clear_thinking_20251015, clear_tool_uses_20250919, compact_20260112}` (the sub-fields may be null)
    - `effort`: `{supported, low, medium, high, max, xhigh (nullable)}`
    - `thinking`: `{supported, types: {adaptive: {supported}, enabled: {supported}}}`
- `GET /v1/models/{model_id}` returns a single ModelInfo. It **accepts aliases** too ("resolve a model alias to a model ID"), and an unknown id gives a 404 `not_found_error` (`anthropic.NotFoundError`). Use it to validate a manually entered id.

```python
from anthropic import AsyncAnthropic
client = AsyncAnthropic(api_key=key, timeout=60.0, max_retries=2)
async for m in client.models.list(limit=100):
    caps = m.capabilities  # may be None
    supports_effort = bool(caps and caps.effort.supported)
    effort_levels = [lvl for lvl in ("low","medium","high","xhigh","max")
                     if caps and getattr(caps.effort, lvl) and getattr(caps.effort, lvl).supported]
    adaptive = bool(caps and caps.thinking.types.adaptive.supported)
    so = bool(caps and caps.structured_outputs.supported)
    ctx, max_out = m.max_input_tokens, m.max_tokens
info = await client.models.retrieve("claude-opus-5-5")   # NotFoundError if bad
```

### 7. Messages API
Sources: https://platform.claude.com/docs/en/api/messages/create , https://platform.claude.com/docs/en/build-with-claude/effort , https://platform.claude.com/docs/en/build-with-claude/thinking-troubleshooting , https://platform.claude.com/docs/en/build-with-claude/structured-outputs , https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons , https://platform.claude.com/docs/en/build-with-claude/context-windows

- `POST /v1/messages`. Required: `model`, `max_tokens` (int), `messages` (`[{"role":"user"|"assistant","content": str | blocks}]`). `system` is a **top-level** param (a str or a list of text blocks), not a message role.
- **Thinking** (`thinking` param):
  - `{"type": "adaptive", "display": "summarized"|"omitted"}`: the current mode
  - `{"type": "enabled", "budget_tokens": N}` (N ≥ 1024 and < max_tokens): legacy extended thinking
  - `{"type": "disabled"}`
  - `{"type": "between_tools"}`: Sonnet 5.5 only
  - Per-model support (from thinking-troubleshooting):
    - Fable 5.1, Mythos 5.1, Fable 5, Mythos 5, Opus 5.5: adaptive only, always on. `enabled` and `disabled` → 400.
    - Opus 5: adaptive only, on by default. `enabled` → 400. `disabled` is accepted only at effort ≤ high.
    - Opus 4.8, 4.7: adaptive only, off by default. `enabled` → 400.
    - Sonnet 5.5: adaptive + between_tools, on. `enabled` and `disabled` → 400.
    - Sonnet 5: adaptive only, on. `enabled` → 400.
    - Opus 4.6, Sonnet 4.6: adaptive or enabled (deprecated), off.
    - Opus 4.5, Sonnet 4.5, Haiku 4.5: enabled only, off. `adaptive` → 400.
  - **Simplest safe approach:** omit `thinking` entirely and control depth with effort. Use the `/v1/models` `capabilities.thinking.types` and `capabilities.effort` to decide what to send.
  - Thinking tokens count toward `max_tokens`. On newer models `display` defaults to "omitted", so thinking blocks come back with empty `thinking` text.
- **Effort**: `output_config={"effort": "low"|"medium"|"high"|"xhigh"|"max"}`. It is GA and needs no beta header.
  - Supported models: fable-5-1, mythos-5-1, fable-5, mythos-5, mythos-preview, opus-5-5, opus-5, opus-4-8, opus-4-7, opus-4-6, opus-4-5-20251101, sonnet-5-5, sonnet-5, sonnet-4-6. **Haiku 4.5 is not supported.**
  - `max` is not on Opus 4.5. `xhigh` is only on Fable 5.x, Mythos 5.x, Opus 5.5, Opus 5, Opus 4.8, Opus 4.7, Sonnet 5.5 and Sonnet 5.
  - Default is `high`, except Opus 5.5, where it is `medium`.
- **Structured outputs**: GA, no beta header. `output_config={"format": {"type": "json_schema", "schema": {...}}}`, which can be combined with `effort` in the same `output_config`.
  - Every object needs `additionalProperties: false`.
  - Not supported: recursive schemas, `minimum`/`maximum`/`multipleOf`, `minLength`/`maxLength`; `minItems` only 0 or 1.
  - The JSON comes back as the text of the `text` content block.
  - The old top-level `output_format` is deprecated: it only works with the beta header `structured-outputs-2025-11-13`, and returns 400 without it.
  - SDK helper: `client.messages.parse(..., output_format=PydanticModel)` gives you `resp.parsed_output`.
  - On a refusal (`stop_reason == "refusal"`, still HTTP 200), the output may not match the schema.
- Prefill (a final assistant message) is rejected with 400 on Claude 4.6+ models (errors page). Don't use it.
- **Response**: `content` (a list of blocks with `type` "text" | "thinking" | "redacted_thinking" | "tool_use" | ...), `stop_reason`, `usage`, `model`, `id`.
  - Text: `"".join(b.text for b in msg.content if b.type == "text")`
  - `usage`: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` (plus optional `server_tool_use`). Thinking is billed inside `output_tokens`.
  - `stop_reason` values: `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn`, `refusal`, `model_context_window_exceeded`.
- **Context overflow** (context-windows doc):
  - If the input alone exceeds the window, you get a **400 `invalid_request_error`** ("prompt is too long") on every model.
  - On Claude 4.5+ models, if input + max_tokens exceeds the window, the request is accepted, and if it runs out it stops with `stop_reason: "model_context_window_exceeded"` (HTTP 200).

```python
msg = await client.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    system="You are ...",
    messages=[{"role": "user", "content": "user text"}],
    output_config={"effort": "medium",
                   "format": {"type": "json_schema",
                              "schema": {"type": "object", "properties": {"a": {"type": "string"}},
                                         "required": ["a"], "additionalProperties": False}}},
)
text = "".join(b.text for b in msg.content if b.type == "text")
u = msg.usage  # input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens
if msg.stop_reason in ("max_tokens", "model_context_window_exceeded", "refusal"): ...
```

### 8. Errors
Sources: https://platform.claude.com/docs/en/api/errors , https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python , https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/_exceptions.py

Error body: `{"type":"error","error":{"type":"<error_type>","message":"..."},"request_id":"req_..."}`. The response header is `request-id`, and SDK objects expose `._request_id`.

| HTTP | `error.type` | Python SDK class |
|---|---|---|
| 400 | `invalid_request_error` (also "prompt is too long", and spend-limit reached) | `BadRequestError` |
| 401 | `authentication_error` | `AuthenticationError` |
| 402 | `billing_error` | (no dedicated class; `APIStatusError`) |
| 403 | `permission_error` | `PermissionDeniedError` |
| 404 | `not_found_error` (bad model id) | `NotFoundError` |
| 409 | `conflict_error` | `ConflictError` |
| 413 | `request_too_large` (32 MB Messages limit) | `RequestTooLargeError` |
| 422 | — | `UnprocessableEntityError` |
| 429 | `rate_limit_error` (also tier spend cap: **no `retry-after` header**, so don't retry it) | `RateLimitError` |
| 500 | `api_error` | `InternalServerError` |
| 503 | — | `ServiceUnavailableError` |
| 504 | `timeout_error` | `DeadlineExceededError` |
| 529 | `overloaded_error` | `OverloadedError` |
| — | network | `APIConnectionError` |
| — | client timeout | `APITimeoutError` |

- Base classes: `anthropic.APIError` → `APIStatusError` (`.status_code`, `.response`, `.body`).
- **Timeouts and retries:** the default timeout is 10 min, and `max_retries` defaults to 2. Connection errors, 408, 409, 429 and ≥500 are retried, honoring `retry-after`.
  - `Anthropic(timeout=20.0, max_retries=0)` or `httpx2.Timeout(60.0, read=5.0, write=10.0, connect=2.0)`; per request: `client.with_options(timeout=5.0, max_retries=5).messages.create(...)`.
  - A non-streaming request with a very large `max_tokens` raises `ValueError` ("expected to take longer than ~10 minutes") unless you pass `stream=True` or set an explicit `timeout`.
- The SDK uses **`httpx2`**, not `httpx`. A custom `http_client` must be an httpx2 client; passing an `httpx` client raises `TypeError`. Tools that patch `httpx` (respx, pytest-httpx) don't see SDK requests unless you call `httpx2.alias_httpx()` at startup. **This matters for test mocking.**

### 9. SDK version
Source: https://pypi.org/pypi/anthropic/json , Python SDK doc
- Latest **anthropic 1.11.0**, `requires_python >=3.10`, classifiers 3.10 through **3.14** (so 3.14 is supported). The SDK is v1, and there is a migration guide from 0.x: https://github.com/anthropics/anthropic-sdk-python/blob/main/MIGRATION.md
- The SDK sends `anthropic-version: 2023-06-01` automatically.

### 10. Pricing pages (reference only; there is no machine-readable source)
- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing (and https://claude.com/pricing). There is no pricing API, and `/v1/models` has no price fields.
- OpenAI: https://developers.openai.com/api/docs/pricing . There is no pricing API.
