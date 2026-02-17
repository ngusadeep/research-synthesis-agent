# Research Chat: Thread, Queue & Streaming Workflow

## Summary

- **Threads** are created and stored in the **frontend** (IndexedDB). The backend receives `thread_id` and `thread_item_id` when you start a research task and **uses them for the whole session**.
- **Tasks** are queued with **Celery + Redis** when `REDIS_URL` is set. The API enqueues; a worker runs the agent.
- **Chat updates** use **SSE (Server-Sent Events)**, not WebSockets. One-way server → client for streaming progress.

---

## 1. How request/response connect to the backend (SSE only)

All chat flow uses **one HTTP POST** and **one SSE stream**—no WebSockets.

| Step | Who | What |
|------|-----|------|
| 1 | Frontend | Creates thread/chat ID (if new), creates thread item ID. |
| 2 | Frontend | **POST /api/research** with `query`, `thread_id`, `thread_item_id`, `max_iterations`. |
| 3 | Backend | Uses that `thread_id` for the **entire session**: task meta in Redis, Celery task args, LangGraph checkpoint config. Uses `thread_item_id` so SSE events echo it. |
| 4 | Backend | Returns `task_id`, `thread_id`, `thread_item_id`, `status: "started"`. |
| 5 | Frontend | Opens **GET /api/research/stream/{task_id}** (EventSource). |
| 6 | Backend | Streams SSE events; each event payload includes `threadId` and `threadItemId` so the frontend can match updates to the right chat/item. |

So: **thread/chat ID is sent from client → backend and is used for that session everywhere** (task, stream, checkpoints).

---

## 2. Thread creation (frontend)

1. User opens `/chat` (no thread) or `/chat/{threadId}`.
2. On first message, if there is no `threadId`, the frontend:
   - Generates a new ID (e.g. UUID).
   - Navigates to `/chat/{threadId}`.
   - Calls `createThread(threadId, { title })` → stored in IndexedDB + Zustand.
3. That **thread_id** and **thread_item_id** (for the new message) are sent to the backend when starting research.

Backend does **not** create or list threads; it receives and uses these IDs for the run and echoes them in responses and SSE.

---

## 3. Start research (task in queue)

**Endpoint:** `POST /api/research`

**Body:** `{ query, mode?, max_iterations?, thread_id?, thread_item_id? }`

- **mode**: `"research"` (default) or `"quick"`.
  - **quick**: Simple chat only (no multi-source research). Use for greetings, small talk, or fast answers.
  - **research**: Full pipeline with **intent detection**: the backend first classifies the message as "research" or "chat". If "chat" (e.g. "Hello", "How are you?"), it responds with simple chat. If "research" (e.g. "What do you know about quantum computing in ML?"), it runs Planner → Worker → Synthesizer → Critic.

- **thread_id**: Optional. If sent, the backend uses it for the whole session (task meta, Redis, worker, LangGraph `configurable.thread_id`). If omitted, backend generates one.
- **thread_item_id**: Optional. If sent, backend uses it so SSE events contain the same id the frontend expects for that message.
- If **`REDIS_URL` is set** (Celery mode):
  - API generates `task_id`; uses request `thread_id` / `thread_item_id` or generates them.
  - Enqueues a Celery task with those ids.
  - Writes task metadata (including thread_id, thread_item_id) to Redis for the stream.
  - Returns immediately.
- If **no Redis** (single-process): API runs the agent in-process and uses an in-memory queue for SSE.

**Response:** `{ task_id, thread_id, thread_item_id, status: "started" }`

So the **task is in a queue** when using Celery, and the **session is tied to the client’s thread_id** when provided.

---

## 4. Streaming progress (SSE) (SSE, not WebSockets)

**Endpoint:** `GET /api/research/stream/{task_id}`  
**Protocol:** **SSE (EventSource)**, not WebSockets.

- Frontend opens: `new EventSource(API_URL + "/api/research/stream/" + task_id)`.
- With **Celery**:
  - API subscribes to Redis channel `research:stream:{task_id}`.
  - Worker publishes events (e.g. `plan`, `documents`, `draft`, `done`, `error`) to that channel.
  - API reads from Redis and forwards each message as an SSE event to the browser.
- With **no Celery**: API reads from an in-memory queue filled by the in-process agent.

**Why SSE and not WebSockets?**

- Updates are **one-way** (server → client).
- SSE is simpler (single HTTP connection, auto-reconnect in browsers).
- No need for client → server messages over the same channel for this flow.

So **chatting uses SSE for live updates**, not WebSockets; the “conversation” is: one HTTP POST to start, one EventSource to stream events.

---

## 5. End-to-end flow (with Celery)

```
[Browser]                    [Nginx]              [API]                [Redis]            [Celery Worker]
    |                           |                    |                      |                      |
    | POST /api/research         |                    |                      |                      |
    | { query, thread_id,       |                    |                      |                      |
    |   thread_item_id }   --->|------------------->|                      |                      |
    |                            |                    | .delay(...) -------->| enqueue task         |
    |                            |                    | set meta in Redis -->|                      |
    |<-- 200 { task_id,          |<-------------------|                      |                      |
    |      thread_id,            |                    |                      |<--- pick task        |
    |      thread_item_id }      |                    |                      |                      |
    |                            |                    |                      |                      |
    | GET /api/research/stream/{task_id} (SSE)       |                      |                      |
    |-------------------------->|------------------->| subscribe channel -->|                      |
    |                            |                    |<-- events -----------| publish events       |
    |<-- SSE: plan, documents,   |<-------------------|   (from worker)      |<-- run agent,        |
    |     draft, done            |                    |                      |    send_event()      |
```

---

## 6. Optional improvements

- **Backend thread store**: If you want threads to be shared across devices or durable on the server, add a “threads” API and DB table; frontend would still create/update local state and sync with the backend.
- **WebSockets**: Only needed if you want the server to push to the client on other channels (e.g. typing, presence) or true bidirectional chat; for “start task + stream task events,” SSE is enough and is what you have.
- **Idempotency**: For “create thread and run” in one go, you can have the frontend send a generated `thread_id` in the first `POST /api/research` and use that consistently (you already support `thread_id` in the body).

Your current design—threads on the client, task in Celery queue, chat over SSE—is a good fit for this research agent flow.
