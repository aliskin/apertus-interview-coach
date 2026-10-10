# Interview Coach — Implementation

See the [project overview](../README.md) for the audience, scope, and challenge requirements.

## Docker setup

Start Docker Desktop or a compatible Docker engine. From this directory:

```sh
make web-demo
```

Open **http://localhost:8080**. Stop with Ctrl+C. Demo mode uses fixed example feedback and makes no AI calls.

For personalised coaching, create `data/.env` locally:

```sh
mkdir -p data
```

Add your provider configuration to that file:

```dotenv
LLM_API_KEY=your-key
LLM_BASE_URL=https://your-provider.example/v1
LLM_NAME=your-apertus-model-id
```

Use the provider's actual API base URL, including its API prefix. The server appends `/chat/completions`. Use HTTPS for remote authenticated endpoints. The `.env` file is ignored by Git.

Launch the coach:

```sh
make web
```

`make run` also launches the web app. The launcher loads `data/.env`, builds the image, and binds the published port to loopback. It detects Docker Desktop's bundled CLI on macOS and reports when the engine is unavailable.

## Other launch options

Change the host port:

```sh
make web-demo WEB_PORT=8082
```

For development with an already-installed model served by Ollama on the host:

```sh
make web COACH_PROVIDER=ollama COACH_MODEL=llama3:8b
```

The container reaches host Ollama through `host.docker.internal:11434`. Set `DOCKER_OLLAMA_BASE_URL` to override it. This development model is not the final Apertus submission.

The legacy stateless API accepts a reviewed prompt profile supplied with `PROFILE=data/profiles/name.json`. Profiles are local JSON files and do not override the new session controller prompts; the application uses the small `prompt_profile.py` loader, without depending on the local human-review tool.

Without Docker, use Python 3.12 and run:

```sh
python src/web.py --provider demo
```

For direct Apertus use, export the provider variables in your shell first, then use `--provider apertus`. For direct Ollama use, use `--provider ollama --model llama3:8b`; its default endpoint is `http://127.0.0.1:11434`. No third-party Python packages are required.

## Architecture and session flow

```mermaid
flowchart LR
    UI[Web interface] --> API[Python session API]
    API --> Controller[Interview controller]
    Bank[Public question bank and posting] --> Controller
    Controller --> Model[Apertus: transition / optional follow-up]
    Model --> Controller
    Controller --> Feedback[Apertus: final evidenced feedback]
    Controller --> Store[Local session JSON]
    Controller --> UI
```

The server chooses a bank-question plan and owns stage, subtype, topic coverage and counters. Each answer triggers one interview request; code validates the response and either permits one follow-up or advances the plan. Finishing the plan or requesting recap triggers a separate whole-session feedback request. The same configured model handles both tasks; no judge is part of the live interview.

Current prompts are the German, French and Italian `src/prompts/session/interviewer.<language>.txt` and `feedback.<language>.txt`; English retains `interviewer.txt` and `feedback.txt`. `guidance.<language>.json` supplies translated rubric/feedback rules, while `instructions.json` localises controller reminders and corrections. The controller supplies public company facts, question metadata, state and actual dialogue. Final feedback also receives the public eleven-criterion rubric and feedback guidelines. Simulator personas, reference annotations and scenario success criteria are excluded from coach input. Older `prompts/web/` are retained only for the legacy stateless API.

## Data and privacy

Server-owned sessions, transcripts and request traces are persisted locally in ignored `data/sessions/`. The browser currently starts a fresh session on refresh; persisted sessions are not a login or share-link feature. Clear local session files when no longer needed. Answers are sent to the configured model provider. API keys remain server-side and model text is rendered as text, not HTML.

The bundled server is intended for local use. Public authenticated hosting needs additional deployment work. Public runtime resources are in `data/interview/`; experimental tools and generated runs remain Git-ignored.

## Tests and development results

From this directory, run:

```sh
make test
```

All 33 application tests pass. They cover progression bounds, conditional question selection, language-specific prompts, evidence validation, server-owned revisions/persistence and the retained legacy API. Model responses are mocked in these tests; passing tests does not establish coaching quality.

The latest local development run completed all 28 organiser scenarios with a separate Apertus candidate simulator. It recorded 417 candidate answers and 471 coach calls, including corrections and final feedback: 1.13 calls per answer. Whole-session assistant reviews are drafts awaiting user validation. Language consistency improved, while grounding, candidate-question handling and follow-up selection remain weak. See [technical_report.md](technical_report.md) for details.

Simulation/evaluation tools, generated runs and manual-review data are deliberately Git-ignored. A fresh clone includes the application, public runtime resources and application tests, but not those local experiments. Commands for private experiment scripts are therefore not part of the submission deployment instructions.

## Session behaviour and limits

Browser sessions start through `/api/session/start`. Clients send a session ID, revision and answer to `/api/answer` or `/api/recap`. Code stores the question plan, current stage/subtype, covered topics, main-question/follow-up counts, transcript and request traces. It updates stage context as the interview progresses.

The browser plan has thirteen main questions, including interview closing, followed by feedback across all eleven FHGR criteria. Each eligible main question permits at most one follow-up; small talk, candidate questions and closing do not. Completing the plan triggers final feedback automatically. Recap ends early and asks the model to acknowledge unavailable evidence. An unsent answer can be included when requesting recap.

The displayed answer ceiling is a conservative bound of twice the plan length (26); eligible-question restrictions make the actual maximum smaller. `MAX_ANSWERS` and `--max-answers` belong to the retained stateless API and do not change the browser controller's plan. The controller currently returns no generated hint, so the interface uses its translated fallback guidance. The first-job scenario label currently selects an apprenticeship posting and the same question plan, rather than a separate first-job interview.

One normal turn makes one model call, with at most one validation correction. The final answer can also trigger a feedback task with up to two calls. Early recap makes only the feedback task. Invalid German/French/Italian interviewer output can fall back to the next bank question after two attempts; invalid English interviewer output and failed feedback are reported as errors. User retries after transport failures can add calls and must be counted. No live judge is used.

## Docker packaging and practicality

`src/run.sh` copies the versioned public resources from `data/interview/` into ignored `src/interview_data/` before building. The image bundles the Python runtime, application, static interface, prompts and these resources. It excludes credentials, experiments, simulation profiles, annotations and generated outputs. Session files persist in the host's ignored `data/sessions/` directory through a bind mount. Run `make web` or `make web-demo` to prepare the build context; a bare Docker build from a fresh clone lacks the staged resource directory.

The image is an application client; it does not install or serve Apertus weights. Hosted inference does not verify the under-32-GB VRAM requirement. A consumer-hardware Apertus deployment, quantisation/context settings and measured memory usage remain outstanding. The recorded hosted development run meets the call-efficiency threshold, but does not establish the complete practicality gate.

## Local manual review (not included in a fresh clone)

The developer's local portal runs on port 8081 and groups individual-answer v1/v2 and whole-interview v5/v6. It preserves each version's labels separately, displays category summaries and draft/validated status, and links exact coach evidence to guideline notes. Originals are expanded by default, with collapsible AI-assisted English reading aids underneath. Both complete-interview versions now have cached English transcript translations; originals remain authoritative.

The portal and its data remain under ignored `src/experiments/` and `data/manual_review/`. The local `make review` target requires those files and is not a supported command for a clean submission checkout. The previous individual review servers have been replaced by this single portal.

## Voice integration contract

The application is text-only, with adapter hooks for future speech recognition (ASR) and text-to-speech (TTS). No microphone, audio upload, speech SDK, playback or model-token streaming is enabled. The existing text interface needs no voice adapter and makes the same coach calls.

Controlled session responses (`/api/session/start`, `/api/answer` and `/api/recap` with a session ID) include a `speech` field. The legacy stateless API does not. `src/voice.py` converts the opening or delivered reply into ordered sentence/paragraph chunks of at most 240 characters. This segmentation uses code rather than another LLM call. The original visible response is unchanged; speech chunks normalise boundary whitespace. The contract is:

```json
{
  "version": 1,
  "session_id": "server-generated-session-id",
  "turn_id": "server-generated-session-id:1:interview",
  "language": "de-CH",
  "kind": "interview",
  "segments": [
    {"id": "server-generated-session-id:1:interview:0", "text": "Danke."},
    {"id": "server-generated-session-id:1:interview:1", "text": "Erzähl uns etwas über dich."}
  ],
  "streaming": false
}
```

Language tags are `en-GB`, `de-CH`, `fr-CH` and `it-CH`. `kind` is `opening`, `interview` or `feedback`. These labels identify output turns, not separately classified acknowledgement/question segments. `turn_id` uses session ID, answer revision and kind, so early recap without another answer has a different ID from the preceding interview turn. Segment IDs allow a TTS adapter to deduplicate and play in array order. The envelope is produced after the complete model response has been validated; generation is not streamed. An adapter can synthesise and play short segments incrementally after receiving it. Future low-latency model streaming requires a separate transport/validation design.

The browser publishes these events on `window`:

| Event | Detail | Adapter responsibility |
| --- | --- | --- |
| `coach:output` | The `speech` envelope | Enqueue speech in order, track the session/turn IDs, ignore duplicate or stale output. |
| `coach:cancel` | `{session_id}` | Stop playback and cancel pending synthesis/recognition; discard late callbacks. Fired on restart, language/scenario reset, answer/recap submission and page exit. This does not cancel an in-flight coach request. |
| `coach:transcription` | `{session_id, language, final, text}` supplied by ASR | Send only a final transcript for the current session; `language` uses the UI code (`en`, `de`, `fr`, `it`). |

A future ASR adapter can populate the answer draft using:

```javascript
window.dispatchEvent(new CustomEvent('coach:transcription', {
  detail: {
    session_id: currentSessionId,
    language: 'de',
    final: true,
    text: 'Ich interessiere mich für Technik.'
  }
}));
```

The browser rejects interim, stale-session, wrong-language, empty and over-4,000-character transcripts, and transcripts arriving while a request is pending or the session is complete. It does not overwrite an existing draft or submit automatically. The user reviews/edits the recognised text and presses Send. Only that confirmed text reaches the coach through the existing answer API; audio, confidence, accent and inferred voice traits are not sent or assessed.

An audio adapter must obtain user permission before using the microphone or sending speech text to an additional service. It must register its listeners before session start, handle cancellation and choose a compatible voice for the language tag. The current server policy allows same-origin connections; using an external browser speech service needs an explicit deployment/privacy and content-security-policy decision. Voice adapters are not implemented or enabled by this change.
