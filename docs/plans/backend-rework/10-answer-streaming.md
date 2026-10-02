# 10: Answer token streaming

**Depends on:** 05 · **Area:** backend

## Goal

The final answer arrives token by token. Only `generate_answer()` is touched; no tool parsing is
involved, so this is the safe half of token streaming.

## Changes

- New `util/think_splitter.py`: an incremental splitter that routes deltas to `thinking` or
  `answer`. It tracks whether it is inside a `<think>` block and holds back an incomplete tag
  prefix at a delta boundary (`<thi` | `nk>`). `flush()` at the end releases held-back
  text. It does **not** handle the "text before a lone `</think>`" case: that text has already
  gone out as `answer` deltas when the tag arrives and cannot be taken back. Live, the frontend's
  `lib/thinking.ts` covers it on the accumulated text. For persistence, `split_think(text)` in
  the same module (whole-text, same rules as `lib/thinking.ts`) runs once over the accumulated
  answer before `finish_message`, so `content` and `thinking` are stored correctly.
- `LLMService.generate_answer_stream(...) -> AsyncIterator[tuple[kind, delta]]` with
  `stream=True`, fed through the splitter. Models that send reasoning in a separate
  `reasoning_content` delta field are routed to `thinking` as well. Errors are wrapped in
  `LLMServiceException` as today; an empty stream raises `LLMNoContentException`.
- `ChatService.run()`: yields `thinking` / `answer` events as they arrive and accumulates both for
  `finish_message`. `generate_answer()` (non-streaming) is removed if nothing else uses it.
- `util/config.py`: `persist_thinking: bool = True`. `False` only skips writing
  `messages.thinking`; the events are still streamed.
- An abort mid-answer stores the partial answer with `status="aborted"`.

## Out of scope

- The frontend already appends `answer` deltas (ticket 06). Its scroll-follow does not react to
  a growing answer yet; that is fixed in ticket 12.

## Tests

- New `tests/test_util/test_think_splitter.py`: no think block, one block, tag split across
  deltas at every position, unterminated block, `flush`; `split_think` with a lone `</think>`.
- `test_llm_service.py`: streamed answer, `reasoning_content`, empty stream.
- `test_chat_service.py`: several `answer` events; `persist_thinking=False` still emits `thinking`
  but stores none; an answer with a lone `</think>` is stored split.

## Docs

- `docs/configuration.md`: `PERSIST_THINKING`. `docs/api.md`: `thinking` event semantics.
