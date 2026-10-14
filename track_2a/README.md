# Interview Coach — Implementation

See the [project overview](../README.md) for the audience, features and challenge constraints.

## Current architecture

New sessions use `conversation_policy="baseline"`: the v8 conversation controller with the v10 verified multilingual recap and optional practice. Later `fixed` and `connected` policies remain experimental; saved sessions retain their stored policy.

Code owns the question plan, stage, subtype, covered topics, main-question and follow-up counts. Apertus first analyses each answer for quoted evidence, completeness, a necessary missing detail, self-doubt and company-information requests. Code validates quotes and selects the action. A separate speaker request writes the contextual reaction or permitted clarification; code appends the next bank question when advancing. Company and support replies also use the speaker model. The same configured Apertus endpoint handles all roles.

Browser interviews contain thirteen main questions. Eligible questions allow at most one clarification; small talk, candidate questions and closing do not. Recap can finish early. Recap in every language evaluates criterion-scoped transcript evidence, checks proposed gaps against complete question–answer pairs, and offers voluntary practice topics grounded in questions actually answered. An exercise is generated only after the user chooses a topic. Gap verification alone cannot assign an exercise. Independent evidence-backed positive assessments survive rejection of an unrelated gap; negative or dependent assessments are withheld. The verifier is another request to the same model, not an independent human judge. Literal quote checks do not establish correct interpretation.

Question context includes actual spoken wording and separate planned wording. Older sessions recover preceding coach text if separate wording is unavailable. Invalid analysis supplies no fabricated evidence; invalid speaker output falls back to bank wording. Every attempted request and correction consumes the session budget. Code keeps the average below five coach calls per accepted interview/practice answer; recap request grouping adapts to the remaining budget. Transport and final-feedback failures are reported rather than presented as successful coaching.

All scenario choices currently use an apprenticeship plan, including the first-job label. The answer hint uses translated fallback guidance. Automatic mastery-based question selection is deferred.

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

## Deployment packaging

`src/run.sh` copies public runtime resources from `data/interview/` into the ignored Docker staging directory before building. The image contains Python application code, prompts, browser assets, public question/rubric resources and the optional review tool. It excludes credentials, model weights, generated sessions, experimental scripts, reports and review labels. For a direct build from this directory:

```sh
mkdir -p src/interview_data
cp data/interview/*.json data/interview/*.jsonl src/interview_data/
docker build -t apertus-interview-coach -f src/Dockerfile src
```

Apertus is served separately through the configured remote API. This packaging does not verify the challenge's under-32-GB model-serving gate. Python 3.12 is the container runtime; no third-party Python or frontend packages are required.

## Persistence and privacy

The server owns sessions. Clients send session IDs, revisions and answers; browser copies are for display. Sessions and traces are stored under ignored `data/sessions/`. Requests whose responses are lost or unreadable are retried once automatically. The latest accepted answer, recap attempt, practice selection or revision response is persisted with a request fingerprint; an exact retry replays that response without another model call or state change, including after a server restart. Other stale revisions remain rejected. Refresh starts a new session; login and shared conversation links are not implemented. Browser storage is optional: denied reads or writes do not interrupt practice. A failed write rolls back conversation state while retaining spent model-call accounting in memory and attempting an atomic accounting write. Persistent disk failure followed by a crash can still lose that accounting.

Practice assignments, revised answers and revision feedback are included in the saved transcript and manual-review import. Practice turns are marked separately and excluded from original-interview evidence. Revision assessment receives the assigned exercise, the original answer and the most recent accepted answer; accepting a revision updates that comparison answer.

If every attempted recap evaluation group fails, the interview answers remain saved and `complete` stays false. The interview itself has ended: retry only the recap, without resubmitting answers. Each attempt advances the session revision, so an explicit retry is distinct from replaying a lost response. Retries use the remaining session call budget; when exhausted, the interface disables recap retries and keeps download/restart available. A valid unassessed result is not a technical failure. If only some groups fail, the recap remains available with those criteria explicitly marked unavailable (`recap_status: partial`).

API credentials stay server-side. Answers are sent to the configured provider. The bundled server is intended for local use; authenticated public hosting requires additional work.

## Prompts and review

The [prompt map](src/prompts/session/README.md) explains task files and their inputs. Public rules are under `data/interview/`; organiser scenario personas and reference annotations are not coach inputs.

The [manual review tool](src/review/README.md) supports version navigation, whole-interview guideline labels, exact evidence highlights, draft/validated reviews, optional French/Italian translations and archiving. Run `make review-demo` for a fictional example or `make review` for existing imported data. Review code is published; generated datasets and labels remain ignored. Experimental inference runners remain local and are not deployment dependencies.

## Verification and observed limits

```sh
make test
```

Tests cover progression, evidence validation, actual-question context, persistence, lost-response recovery, conversation guards, optional practice, voice contracts and portable review storage. Dependency-free browser regression tests for denied storage and response retries can also be run with `node src/tests/browser_session.test.js` when Node.js is available. Model responses are mocked; tests do not prove coaching quality.

The current evaluation regenerates only final recaps for the 28 supplied German/French/Italian scenarios, reusing exactly the saved candidate answers and interviewer replies. English is available in the practice interface for debugging but is excluded from the review cohort. Conversation request costs are reused for equivalent session budgeting; newly generated recap calls are recorded separately. Simulator calls are not repeated. Reviews remain drafts; literal quote checks do not establish semantic correctness. Official benchmark scores and consumer-hardware VRAM remain unverified.

English question translations are stored separately in `src/prompts/session/questions.en.json`; the original organiser bank is unchanged. Translations need human review. Practice history is separated by language and scenario; a previous session in another language cannot supply its learning target.

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
