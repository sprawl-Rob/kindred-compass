# OpenAI Responses API agent loop (Python, openai 3.24, AsyncOpenAI): verified 2026-10-05

Sources checked on 2026-10-05:
- Function calling guide: https://developers.openai.com/api/docs/guides/function-calling (platform.openai.com/docs/guides/function-calling now 301-redirects here)
- Structured outputs, supported schemas: https://developers.openai.com/api/docs/guides/structured-outputs#supported-schemas
- Reasoning guide: https://developers.openai.com/api/docs/guides/reasoning (section "Preserve reasoning without stored responses")
- Conversation state guide: https://developers.openai.com/api/docs/guides/conversation-state
- Web search guide: https://developers.openai.com/api/docs/guides/tools-web-search
- API reference: https://developers.openai.com/api/reference/resources/responses/methods/create
- openai-python source, `main` branch, `_version.py` = "3.24.0" (v3.24.0 tagged 2026-10-02):
  - `src/openai/resources/responses/responses.py`: create() signature and docstrings
  - `src/openai/types/responses/function_tool_param.py`
  - `src/openai/types/responses/response_function_tool_call.py`
  - `src/openai/types/responses/response_input_item_param.py` (FunctionCallOutput)
  - `src/openai/types/responses/response_reasoning_item.py`
  - `src/openai/types/responses/web_search_tool_param.py`, `web_search_preview_tool_param.py`
  - `src/openai/types/responses/response_function_web_search.py`
  - `src/openai/types/responses/response_output_text.py` (AnnotationURLCitation)
  - `src/openai/types/responses/response.py` (status, IncompleteDetails)
  - `src/openai/types/responses/response_includable.py`
  - `src/openai/types/shared/reasoning.py`

Model names below (gpt-6-astra, gpt-5.5, gpt-6.1-sol, gpt-5.6) are copied from the docs' current examples. Confirm availability on your account.

---

## 1. Function tool definition

SDK `FunctionToolParam` (function_tool_param.py): `type: "function"` (Required), `name` (Required), `parameters: dict | None` (Required), `strict: bool | None` (Required key, may be None), and optionally `description`. Newer optional fields also exist: `defer_loading`, `allowed_callers`, `output_schema`, `async`. The tool is flat, with no nested `"function": {...}` wrapper as in Chat Completions.

```python
tools = [{
    "type": "function",
    "name": "get_weather",
    "description": "Get current weather for a location.",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {"type": "string"},
            "units": {"type": ["string", "null"], "enum": ["c", "f", None]},
        },
        "required": ["location", "units"],
        "additionalProperties": False,
    },
    "strict": True,
}]
```

### Strict mode
From the function calling guide:
- The guide recommends always enabling strict mode, which uses Structured Outputs.
- `additionalProperties` must be `false` for every object in `parameters`.
- Every field in `properties` must be listed in `required`. To make a field optional, allow `null` as a type, for example `"type": ["string","null"]`.
- Default when `strict` is omitted: Responses API requests "attempt to normalize your schema into strict mode when possible, and will fall back to non-strict, best-effort" calling. Set `strict` explicitly. The SDK TypedDict marks the key Required anyway.
- Function definitions are injected into the system message, so they count toward the context window and are billed as input tokens.

From structured-outputs "Supported schemas":
- Supported types: string, number, boolean, integer, object, array, enum, anyOf.
- Supported string keywords: `pattern`, and `format` (date-time, time, date, duration, email, hostname, ipv4, ipv6, uuid).
- Supported number keywords: `multipleOf`, `maximum`, `exclusiveMaximum`, `minimum`, `exclusiveMinimum`.
- Supported array keywords: `minItems`, `maxItems`.
- The root must be an object and must not use `anyOf`.
- Definitions (`$defs`/`$ref`) and recursive schemas (`#`) are supported.
- Limits:
  - Up to 5000 object properties in total, with up to 10 levels of nesting.
  - Total string length of names, enum values and consts is at most 120,000 characters.
  - At most 1000 enum values. When a single string enum has more than 250 values, its values may total at most 15,000 characters.
- Not supported: `allOf`, `not`, `dependentRequired`, `dependentSchemas`, `if`/`then`/`else`. Fine-tuned models also lose minLength/maxLength/pattern/format, min/max/multipleOf, patternProperties and minItems/maxItems.
- With `strict: true`, an unsupported schema makes the API return an error.
- Output keys come back in the same order as the schema keys.

## 2. Function call output items and returning results

`ResponseFunctionToolCall` (response_function_tool_call.py):
```
{"type": "function_call", "id": "fc_...", "call_id": "call_...", "name": "get_weather",
 "arguments": "{\"location\":\"Paris\"}", "status": "completed"}
```
- `arguments` is a JSON string. Parse it with `json.loads`.
- `id` is Optional in the SDK.
- Newer optional fields: `namespace`, `caller`, `async`.
- Use `call_id`, not `id`, to pair the call with its output.

Return the result with an input item of type `function_call_output` (response_input_item_param.py `FunctionCallOutput`):
```python
{"type": "function_call_output", "call_id": item.call_id, "output": "<string>"}
```
`output` can be a string, or a list of text, image or file parts. The guide says it "should typically be a string" (JSON, error codes, plain text).

### Continuing without server storage (store=False)
- Re-send the whole history on every call: the prior inputs, every item in `response.output`, then your `function_call_output` items. Conversation-state guide: "For stateless reasoning-model requests, preserve every item in the response's `output` array."
- Reasoning items: "pass back all reasoning items, function call items, and function call output items, since the last `user` message" (reasoning guide). Function calling guide: reasoning items returned with tool calls "must also be passed back with tool call outputs."
- `include=["reasoning.encrypted_content"]` is NO LONGER REQUIRED. Reasoning guide: "When you create a response in stateless mode, reasoning items in the response's `output` array include an `encrypted_content` property by default." Also: "The API still accepts the legacy `reasoning.encrypted_content` value in `include` for compatibility, but doesn't require it." The SDK `ResponseReasoningItem.encrypted_content` docstring agrees: "populated by default".
  - Caveat: the SDK `create()` docstring for `include` still describes `reasoning.encrypted_content` as the way to enable stateless reasoning. That text is outdated relative to the guide.
  - Passing it anyway is harmless and protects you against older models or behavior. Recommendation: pass it.
- Streaming caveat (SDK docstring): take `encrypted_content` from the reasoning item in `response.output_item.done`. The copy in `output_item.added` may be incomplete.
- New `reasoning.context` setting (shared/reasoning.py and the reasoning guide):
  - Values: `"auto" | "current_turn" | "all_turns"`.
  - The gpt-5.6 family defaults to `all_turns`. Earlier models default to `current_turn`.
  - `all_turns` renders reasoning from earlier turns into later samples on models that support it.
  - Within one tool loop (same user turn), reasoning is carried either way.
- Official Python sample (conversation-state guide) appends the pydantic output objects directly: `history += response.output`. The JS SDK has a helper `toResponseInputItems`. **No Python equivalent was found** in `src/openai/lib`.
  - Unconfirmed alternative: `item.model_dump(exclude_none=True)`. It gives you plain dicts if you need to serialize or persist history. Untested here.

```python
import json
from openai import AsyncOpenAI
client = AsyncOpenAI()

async def run_agent(user_msg: str, tools, handlers, model="gpt-5.5", max_turns=10):
    history: list = [{"role": "user", "content": user_msg}]
    for _ in range(max_turns):
        resp = await client.responses.create(
            model=model,
            instructions="...",
            input=history,
            tools=tools,
            store=False,
            include=["reasoning.encrypted_content"],  # legacy/optional now; harmless
            parallel_tool_calls=True,
            max_tool_calls=8,             # caps BUILT-IN tool calls only (see 4)
            max_output_tokens=25_000,
        )
        if resp.status == "incomplete":
            # resp.incomplete_details.reason in {"max_output_tokens","max_messages","content_filter","steered"}
            ...
        history += resp.output            # keep reasoning, function_call, web_search_call, message items
        calls = [it for it in resp.output if it.type == "function_call"]
        if not calls:
            return resp                   # resp.output_text + annotations
        for c in calls:
            try:
                result = await handlers[c.name](**json.loads(c.arguments))
                out = json.dumps(result)
            except Exception as e:
                out = json.dumps({"error": str(e)})
            history.append({"type": "function_call_output", "call_id": c.call_id, "output": out})
    raise RuntimeError("turn limit reached")
```

## 3. Built-in web search

- Tool type string:
  - `"web_search"` is the current one. The SDK Literal also accepts the dated `"web_search_2025_08_26"`.
  - `"web_search_preview"` and `"web_search_preview_2025_03_11"` are legacy. They are still accepted, but they do not support `filters` or `return_token_budget`, and they ignore `external_web_access`.
  - Guide: "For new Responses API integrations, use `{ "type": "web_search" }`."
- Options:
  - `search_context_size`: `"low"`, `"medium"` (default) or `"high"`. This is guidance only, not an exact token count.
  - `user_location`: `{"type":"approximate","country":"US","city":"...","region":"...","timezone":"America/New_York"}`. When omitted it defaults to the US. Pass `{"type":"approximate"}` with no fields to avoid that fallback.
  - `filters`: `{"allowed_domains": [...], "blocked_domains": [...]}`. Each list takes up to 100 domains, without `http(s)://`, and subdomains are included.
    - **Discrepancy:** the SDK 3.24 `Filters` TypedDict only declares `allowed_domains`. `blocked_domains` is documented in the guide, and the Go sample adds it through `SetExtraFields`. In Python the dict passes through at runtime, but a type checker will complain.
  - `external_web_access`: bool, default true. False means cache-only.
  - `search_content_types`: `["text","image"]` per the guide.
  - `image_settings` per the guide.
  - `return_token_budget`: `"default"` or `"unlimited"`. GPT-5+ reasoning models only.
- Models:
  - The guide recommends `gpt-5.5` for new integrations. Docs examples use `gpt-6-astra`.
  - `gpt-4.1`, `gpt-4.1-mini` and `o4-mini` are listed with search context capped at 128k. o4-mini shuts down 2026-10-23.
  - Not supported: `gpt-5` with `minimal` reasoning.
  - `gpt-5.4` with effort `none` may give lower-quality results.
  - The search context window is 128k for every model.
- With `tool_choice: "auto"`, search is optional. Use `"required"` or a specific tool choice to force it.
- Output item (`ResponseFunctionWebSearch`):
  ```
  {"type":"web_search_call","id":"ws_...","status":"in_progress|searching|completed|failed|incomplete",
   "action": {"type":"search","query":"...","queries":[...],"sources":[{"type":"url","url":"..."}]}
          | {"type":"open_page","url":"..."}
          | {"type":"find_in_page","url":"...","pattern":"..."}}
  ```
  - `sources` is only populated when you pass `include=["web_search_call.action.sources"]`. It lists all consulted URLs, usually more than are cited, and may include `oai-sports`, `oai-weather` and `oai-finance` feeds.
- Citations: in the `message` item, under `content[i]` (type `output_text`), `.annotations[]`:
  ```
  {"type":"url_citation","url":"...","title":"...","start_index":int,"end_index":int}
  ```
  - The indexes are character offsets into `.text`.
  - The guide requires that inline citations shown to end users be clearly visible and clickable.
- Fetch / open page:
  - There is no standalone "fetch URL" tool. Reasoning models can open pages and search within them as part of web_search (`open_page` and `find_in_page` actions, "Supported in reasoning models").
  - Unconfirmed: whether you can force the model to open a specific URL you supply. Nothing in the docs states this.
  - For a guaranteed fetch of a specific URL, write your own function tool.
- Billing: the guide says search actions incur a tool-call cost. It does not say whether open_page or find_in_page actions are billed, so treat that as unconfirmed.

## 4. Limiting tool calls

- `max_tool_calls: int` (SDK docstring): "The maximum number of total calls to built-in tools that can be processed in a response. This maximum number applies across all built-in tool calls, not per individual tool. Any further attempts to call a tool by the model will be ignored."
  - It covers built-in tools only. It does not limit function calls across your loop, so enforce your own turn and call budget.
- `parallel_tool_calls: bool`: false means zero or one tool call per turn.
  - The guide notes: "Built-in tools cannot be included in a parallel function-call batch."
- `tool_choice`:
  - `"auto"` (default), `"required"` or `"none"`.
  - Force one function: `{"type":"function","name":"..."}`.
  - Force a built-in tool: `{"type":"web_search"}` (a ToolChoiceTypesParam; the exact literal list was not re-checked).
  - Restrict to a subset: `{"type":"allowed_tools","mode":"auto"|"required","tools":[{"type":"function","name":"..."}, ...]}`.
  - The SDK union also includes mcp, custom, programmatic, apply_patch and shell choice types.

## 5. Errors and edge cases

- `Response.status` is one of `completed`, `failed`, `in_progress`, `cancelled`, `queued`, `incomplete`.
- `incomplete_details.reason` is one of `"max_output_tokens"`, `"max_messages"`, `"content_filter"`, `"steered"` (response.py).
- `max_output_tokens` includes reasoning tokens.
  - When it is hit you get `status == "incomplete"` with reason `max_output_tokens`. This can happen before any visible output, and the reasoning is still billed.
  - OpenAI recommends reserving at least 25,000 tokens when you start out (reasoning guide).
  - In a tool loop, check status before acting. An incomplete response may hold partial or no `function_call` items. Unconfirmed: whether a truncated function_call can carry invalid JSON `arguments`. Guard `json.loads` anyway.
- Item-level `status` on function_call and reasoning items can be `in_progress`, `completed` or `incomplete`.
- web_search_call status can be `failed` or `incomplete`.
- `truncation`: `"auto"` or `"disabled"`.
- `previous_response_id` cannot be combined with `conversation`. With store=False you replay input instead.
- `store` defaults to true when omitted. Stored data is kept for at least 30 days (SDK docstring).

## 6. Pricing URL (web search tool calls)

https://developers.openai.com/api/docs/pricing#built-in-tools (anchor confirmed present; prices not copied)
