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

A reviewed prompt profile can be supplied with `PROFILE=data/profiles/name.json`. Profiles are local JSON files; the application uses the small `prompt_profile.py` loader, without depending on the local human-review tool.

Without Docker, use Python 3.12 and run:

```sh
python src/web.py --provider demo
```

For direct Apertus use, export the provider variables in your shell first, then use `--provider apertus`. For direct Ollama use, use `--provider ollama --model llama3:8b`; its default endpoint is `http://127.0.0.1:11434`. No third-party Python packages are required.

## Architecture and session flow

```mermaid
flowchart LR
    Browser[Browser: conversation and controls] --> Server[Python HTTP server in Docker]
    Server --> Provider[Apertus endpoint or local Ollama]
    Provider --> Server
    Server --> Browser
```

`src/web.py` serves the static interface and validates language, scenario, transcript roles, and message lengths. `src/experiment.py` contains the provider adapters and separate batch evaluation workflow. The image contains neither the local review tool nor the terminal app.

| Stage | Behaviour | Model calls |
| --- | --- | --- |
| Select language/scenario | Prepared opening and optional motivation hint | 0 |
| Submit an answer | Feedback, one useful adaptive question, and its hint | 1 |
| Coach recommends wrapping up | Recommendation returned with the same answer response; user can continue if a meaningful question remains | 0 additional |
| Get recap | Recap of all submitted answers; a typed draft is included as the final answer | 1 |
| Answer/context safeguard reached | Produce the recap in the current answer call | 0 additional |
| Download/restart | Export text or clear the conversation | 0 |

Practice is no longer limited to three answers. Use Get recap whenever you are ready. If no meaningful follow-up remains, the coach can set `can_continue=false` and recommend a recap instead of asking filler questions. A recommendation alone does not complete the session; the recap action does.

The default answer safeguard is 12, configurable with `make web MAX_ANSWERS=20` or `--max-answers 20` for direct Python (allowed range: 2–50). The server requests a recap when the submitted conversation reaches 16,000 characters, reserving space for an intervening reply and another answer. Histories above 24,000 characters are rejected without a model call; history is not silently truncated. These character limits bound growth but are not a measured token/VRAM guarantee.


The coach is asked to accept school, hobby, and home examples, avoid fabricated achievements, and avoid personality or employability judgments. Response JSON contains `reply`, `hint`, `suggest_recap` and `can_continue`; missing hints or plain-text replies receive neutral fallback guidance without another model call. Demo follow-ups and hints are fixed examples across scenarios; after its example bank is exhausted it recommends a recap. Changing language or scenario restarts practice, with confirmation if answers or a draft exist.

## Model prompt organisation

Web coaching prompt files live in `src/prompts/web/`:

| File | Use |
| --- | --- |
| `shared.txt` | Role, supportive tone, evidence grounding, and safety rules for every call |
| `output.txt` | The reply, hint and wrap-up decision JSON contract for every call |
| `after_first_answer.txt` | Feedback on the opening answer, one adaptive question, and its hint |
| `followup.txt` | Feedback and adaptive questions after any subsequent answer; optional wrap-up recommendation |
| `final_recap.txt` | User-requested or safeguard-triggered recap; no question and an empty hint |

`build_messages()` in `src/web.py` selects the task from the validated answer count, explicit recap action, answer limit and context safeguard. It assembles shared rules, optional `coach.interaction` profile guidance, scenario context from `src/static/scenarios.json`, the selected language, the output contract, and only the current stage instructions into one system message. The conversation follows as assistant/user messages. Stage instructions are placed last to make the current task explicit.

All coaching and recap calls use the same configured Apertus or Ollama model; there is no planner or judge call within the coaching session. Demo mode bypasses prompt construction and uses fixed responses. `src/prompts/coach.txt` and `judge.txt` remain separate batch-experiment prompts. Prompt files are loaded when the server starts; rebuild/restart Docker after changing them.

## Data and privacy

The web conversation lives in tab memory and is lost on refresh or restart unless downloaded. The server does not save web transcripts to disk. Answers are sent to the configured model provider, whose retention policy applies. Avoid personal details. There is no login, session database, or shareable conversation link.

The bundled server is intended for local use; authenticated public hosting would require additional deployment work. API keys remain server-side, and model output is displayed as text rather than HTML.

## Tests and batch evaluation

Run tests in a Python environment:

```sh
make test
```

The batch experiment uses four authored English example cases in `data/first_interview_en.json`, not an official benchmark. To generate sample responses and evaluate the coach with a host Ollama judge:

```sh
mkdir -p data/runs
python src/experiment.py generate --provider sample --output data/runs/sample.json
python src/experiment.py evaluate --input data/runs/sample.json --output data/runs/sample_judged.json
```

Ollama must have the judge model installed; the default is `qwen3.5:9b`. Output paths must be new. Judge reports include scores, explanations, and evidence. Invalid judgments are saved for review and excluded from averages. Judging remains separate from browser practice and does not score candidate ability.

## Practicality and limitations

The web app uses one model call per answer plus one when the user explicitly requests a recap (at most two calls per answer on average for a completed session without retries) and adds no model weights or GPU requirement. The selected Apertus model, quantisation, context length, and serving configuration still require verification against the under-32-GB VRAM gate. Interface translations do not establish multilingual coaching quality; model responses, feedback usefulness, learning gains, and consistency require further evaluation.

See [technical_report.md](technical_report.md) for the technical report.
