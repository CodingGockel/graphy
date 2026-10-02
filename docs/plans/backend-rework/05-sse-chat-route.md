# 05: SSE chat route

**Depends on:** 04 · **Area:** backend · **lands together with 06**

## Goal

`POST /api/v1/chat` returns `text/event-stream`. The JSON adapter from 04 is deleted.

## Changes (`api/v1/chat.py`, `api/dependencies.py`)

- **Before the first byte:** if `session_id` is given, check existence with a short-lived DB
  session and answer `404` as normal JSON. After that the status is always 200.
- **DB session inside the stream.** The route depends on the *sessionmaker*
  (`get_db_sessionmaker`), not on `get_db_session`: FastAPI closes yield-dependencies before the
  body is streamed.
- **Producer task + queue.** A task runs `service.run(...)` inside `async with sessionmaker()` and
  puts events on an `asyncio.Queue`. The response generator reads with a 15 s timeout and emits
  `SSE_PING` when it expires.
- **In-band errors.** The producer catches the domain exceptions and emits an `error` event with
  the matching `kind` (mapping next to the HTTP mapping in `exception_handlers.py`, so both stay in
  sync); anything else is logged and becomes `kind="internal"`. The HTTP handlers keep working for
  all other routes.
- **Abort.** When the client disconnects, the response generator ends and its `finally` cancels
  the producer task. Depending on the ASGI version the generator is either cancelled or, once the
  next send fails, closed (`GeneratorExit`); the `finally` must work for both. In the second case
  the disconnect is only noticed at the next event or ping, so up to 15 s late.
  The producer catches `CancelledError`, opens a **fresh** DB session and marks the assistant
  message `aborted` with the partial answer from `TurnState` (steps so far stay), shielded from
  the cancellation, then re-raises. Not through the run's own session: a cancellation that hits
  a running DB operation leaves that connection unusable.
- **Headers:** `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- `ChatResponse` is removed from `models/schemas.py`.

## Out of scope

- nginx / compose (`proxy_buffering off` etc.) stays a deployment topic; `docs/deployment.md` gets
  a warning box only.

## Tests

Rewrite `test_chat_router.py`:

- event sequence and SSE framing over `TestClient` streaming; `404` for an unknown session as JSON.
- a domain exception in the service → `error` event with the right `kind`, stream ends.
- heartbeat: a slow fake service with a shortened ping interval yields `: ping`.
- abort: cancelling the producer marks the message `aborted` through a second DB session, with
  the partial answer from `TurnState`; closing the response generator cancels the producer.

## Docs

- `docs/api.md`: `POST /chat` as SSE, the event table from 03, error handling, 404 for unknown IDs.
- `docs/architecture.md`: request flow. `docs/deployment.md`: proxy-buffering warning.
- `CLAUDE.md`: chat router and `ChatService` description.
