# 09: Session titles

**Depends on:** 05, 07 · **Area:** backend + small frontend part

## Goal

A session gets an LLM-generated title on its first turn, without delaying the stream and without
ever failing the turn.

## Backend

- `resources/prompts/title_prompt.md`: static, KG-agnostic, not part of `build_prompt.py`.
- `LLMService.generate_title(question) -> str`: short prompt, few output tokens, `strip_think`,
  trimmed to one line.
- `util/config.py`: `generate_session_titles: bool = True`,
  `session_title_prompt_path`, `session_title_timeout: float = 5.0`.
- `ChatService.run()`, only when `sessions.title IS NULL`:
  1. The `session` event goes out immediately with `title: null`.
  2. The title call starts as an `asyncio.Task`.
  3. Between loop iterations: if `task.done()`, persist the title through the run's own repository
     (an `AsyncSession` must not be used concurrently) and yield `session_title`.
  4. Still running at the end → await it with the timeout. `session_title` is always emitted
     before `done`.
  5. Failure, timeout or `generate_session_titles = False` → fallback: the question cut to ~60
     characters at a word boundary. Logged, never raised. The task is cancelled if the run is.
     With the flag off no task is started: the fallback title is stored before the `session`
     event and sent in it, no `session_title` follows.
- A title with `title_is_manual` is never overwritten.

## Frontend

- `state/chat.ts`: handle `session_title` → `setTitle(id, title)` (local entry only; `renameSession` is the `PATCH`). The local
  `makeTitle` remains the placeholder until the event arrives.

## Tests

- `test_llm_service.py`: `generate_title`.
- `test_chat_service.py`: title event emitted and persisted; failing call → fallback; hanging call
  → fallback after the timeout, turn unaffected; flag off → fallback in the `session` event, no LLM call; `session_title` before
  `done`; second
  turn → no title call; manual title untouched.

## Docs

- `docs/configuration.md`: the three settings. `docs/api.md`: `session_title` event.
