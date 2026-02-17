# Agent pipeline: order and steps

## Research vs Quick (and intent)

- **Quick mode** (frontend: "Quick"): Backend runs **simple chat only**—one LLM call, no search. Use for greetings, small talk, or fast Q&A.
- **Research mode** (frontend: "Research"): Backend first runs **intent classification**:
  - If the message is **chat** (e.g. "Hello", "How are you?"), it responds with simple chat.
  - If the message is a **research question** (e.g. "What do you know about X?", "Compare A and B"), it runs the full pipeline below.
- **Source limit**: The worker collects many results from tools but **ranks by credibility**, dedupes by URL, and keeps only the **top 10** for synthesis and display (config: `app.max_sources_used`). So the user sees at most 10 references, not 20–30.

## How the agents work together

The research graph runs in a fixed order. Each step can stream progress to the frontend via SSE.

| Order | Node        | What it does | SSE events (examples) |
|-------|-------------|--------------|------------------------|
| 1     | **Planner** | Turns the user query into 3–5 sub-queries (e.g. academic, news, reference). | `steps` (sub-queries as “steps”) |
| 2     | **Worker**  | For each sub-query: runs search (ArXiv, Tavily, Wikipedia, SerpAPI), collects documents. | `steps` (per-query status), `sources` |
| 3     | **Synthesizer** | Builds one draft report from all documents; streams text; detects conflicts. | `steps` (“Synthesizing…”), `answer` (streaming text) |
| 4     | **Critic**  | Scores the draft; decides “refine” or “done”. | `steps` (“Self-critiquing…”, score) |
| 5     | (conditional) | If refine and iterations left: back to **Planner** (1) with critique; else **done**. | — |

So: **Planner → Worker → Synthesizer → Critic → (loop to Planner or end)**. The single “last output” is the **final report** from the last **Synthesizer** run when **Critic** accepts (or max iterations reached).

## Frontend “steps” (right side)

- **Steps** come from backend events `steps`, `sources`, `answer`.
- The UI shows an “Agent Reasoning” panel: **N Steps** (e.g. “3/5 Steps”). Each step has a **text** (e.g. “[academic] What are…”) and **status** (PENDING / COMPLETED).
- Backend sends multiple `steps` payloads (planner’s list, then worker updates per query, then synthesizer/critic). The frontend merges by event type; if the last event overwrites the steps array, you may see one aggregated “step” block. To show **distinct phases** (Planning, Searching, Synthesizing, Critiquing), the frontend would map event types or step `id`s to those labels instead of treating every “steps” update the same.

## Why it feels slow

- The pipeline is **inherently heavy**: many LLM calls (planner, synthesizer, critic) and several search calls (worker) per iteration; with refinement there can be 2–3 iterations.
- **SSE is not the bottleneck**; it only delivers events. The slowness is from the research work (API calls, token generation).
- To improve perceived speed: stream more granular events (e.g. “Searching 2/5…”), show a clear “Planning / Searching / Synthesizing / Critiquing” phase, and optionally cache or shorten iterations.

## JSON showing after the response

- If you see **the same content twice** (once as normal text, once as JSON), it’s likely either:
  - The **steps** panel expanding **sub-steps** and rendering `sub.data` with `JSON.stringify` when it’s an object (see `research-steps.tsx`), or
  - Some part of the UI rendering `threadItem.object` or raw event data.
- That’s **not required** for the research flow. You can change the UI to hide raw JSON (e.g. only show `sub.data` when it’s a short string, or render a summary instead of `JSON.stringify`).
