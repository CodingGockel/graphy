# 11: Tool-loop streaming and thinking

**Depends on:** 10 · **Area:** backend

## Goal

The model's reasoning during the tool loop is visible live. Rule: **stream for display, parse on
the buffer.** Tool detection keeps working on the complete message exactly as today.

## Backend

- `LLMService.chat_with_tools()` becomes an async generator with `stream=True`: it yields
  thinking deltas and, as its last item, the `LLMTurn`. (Not a callback: a callback cannot yield
  from `ChatService.run()`.)
  - `content` deltas go through the splitter from 10; only the **thinking** part is emitted live.
    Non-thinking content is buffered: it may be a text-encoded tool call or, when no query ran, the
    final answer.
  - `tool_calls` deltas are accumulated by `index` (id, name, argument fragments).
  - At the end, a `ChatCompletionMessage` is rebuilt from the buffers and the **existing** logic
    runs unchanged on it: structured tool call → `_recover_tool_call_from_content` → plain answer →
    `LLMNoContentException`.
- `util/config.py`: `llm_stream_tool_loop: bool = True`. Off → the loop call runs without
  `stream` as before and yields only the `LLMTurn`. Some OpenAI-compatible servers parse tool
  calls less reliably when streaming; this is the switch for such a model.
- `ChatService.run()`: forwards the thinking deltas as `thinking` events. When the loop ends
  without data, the buffered loop text is emitted as a single `answer` event (with the think part
  already split off).
- Persistence: the reasoning of a loop turn that ends in a tool call is passed to
  `start_step(..., thinking=...)`. The reasoning of the turn that ends the loop goes into
  `messages.thinking`, in front of the answer call's reasoning. `persist_thinking = False` skips
  both; the events are still streamed.

## Frontend

Nothing to do here: the trace from ticket 12 already places `thinking` deltas between the steps
and reads `steps.thinking` on reload.

## Tests

- `test_llm_service.py`: tool call split over many deltas; two tool calls in one message (first
  one wins, as today); text-encoded tool call recovered from the buffered stream; thinking deltas
  emitted while the tool call is still detected; flag off → no deltas, same `LLMTurn`.
- `test_chat_service.py`: `thinking` events between steps; no-data answer emitted once; loop
  reasoning stored on the step, final reasoning on the message; nothing stored with
  `persist_thinking = False`.

## Docs

- `docs/api.md`: when `thinking` appears. `docs/architecture.md`: the streaming rule.
  `docs/configuration.md`: `PERSIST_THINKING` now covers `steps.thinking` too;
  `LLM_STREAM_TOOL_LOOP`.
