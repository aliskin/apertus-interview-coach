# AI-Powered Job Interview Coach

An Apertus-based interview practice app for teenagers preparing for their first job or apprenticeship. Built for HackApertus 2026, Track 2A — FHGR.

**Status:** Runnable Docker web prototype with a complete interview controller and multilingual final feedback. Development simulations cover all 28 organiser scenarios. Coaching quality has known limitations; the official benchmark and consumer-hardware VRAM validation remain outstanding.

## Features

- English, German, French and Italian interface and coaching instructions.
- A thirteen-question browser interview covering introduction, motivation, strengths/weaknesses, situational questions, candidate questions and closing, followed by feedback.
- Questions selected from the supplied FHGR bank, with at most one follow-up per eligible main question.
- Early recap, feedback across eleven criteria and conversation downloads.
- German hybrid practice: visible evidence, one learning exercise, answer revision and a saved learning target.
- A neutral answer placeholder with optional help. The current controller does not generate contextual hints; the interface uses its translated fallback guidance.
- Responsive desktop/mobile layouts and demo mode without model calls.
- Voice adapter hooks: ordered speech output and confirmed-transcript input; actual audio services are not included.

The scenario dropdown offers IT, retail, hospitality, technical and first-job practice labels. Currently all options use an apprenticeship question plan and a fictional apprenticeship posting; the first-job option does not yet have a dedicated non-apprenticeship flow.

## Quick start

Install and start Docker Desktop or a compatible Docker engine. From the repository root:

```sh
make -C track_2a web-demo
```

Open **http://localhost:8080**. Demo mode advances through bank questions and ends with fixed example feedback; it provides no personalised AI coaching. Stop with Ctrl+C.

For Apertus, create the ignored `track_2a/data/.env` file:

```dotenv
LLM_API_KEY=your-key
LLM_BASE_URL=https://your-provider.example/v1
LLM_NAME=swiss-ai/Apertus-v1.5-8B
```

Use the model identifier and API base URL accepted by your serving endpoint. Then run:

```sh
make -C track_2a web
```

`make run` is an alias for the web app. See the [implementation README](track_2a/README.md) for deployment and local Python instructions. The Docker image contains the application and public runtime resources; Apertus weights and model serving are separate.

## Architecture and visual overview

```mermaid
flowchart LR
    Answer[Candidate answer] --> Analysis[Apertus: quoted evidence and intent]
    Analysis --> Controller[State machine: action and bank question]
    Controller --> Interviewer[Apertus: acknowledgement or clarification]
    Controller --> Company[Select explicit posting facts]
    Controller --> Support[Code: supportive response]
    Controller --> Evaluator[Recap: rubric and eligible transcript evidence]
    Evaluator --> Learning[One exercise, reflection and optional revision]
    Learning --> History[Saved learning target for next session]
```

German sessions use the hybrid controller in `src/hybrid.py`. Code owns question selection, progression and termination; Apertus handles analysis, short conversational replies, fact selection, assessment and learning support. Company replies show selected original posting facts. Strong self-doubt has a conservative text-trigger fallback and a supportive response. Final feedback displays source quotations and question IDs, followed by one learning exercise and reflection. German users can revise an answer and carry their last learning target into another session for the same profession.

English, French and Italian retain the earlier v8 pipeline. Main questions keep bank wording; competency availability is tracked, but automatic skipping and mastery-based selection are deferred. Experience/difficulty settings are supplied as context; their effectiveness has not been evaluated. Each task permits at most one correction. Code caps counted calls below five per accepted interview/practice answer across the session. A full German recap normally uses three small evaluator groups and one learning call; early recaps use fewer groups to fit the budget. Exact quotations and fact selection do not guarantee correct interpretation or relevance.

For future voice support, responses expose language-tagged speech segments and turn IDs. Browser events support playback cancellation and recognised text as an editable answer draft. No microphone or audio playback is enabled; model responses arrive in full rather than streaming. See the [voice integration contract](track_2a/README.md#voice-integration-contract).

Sessions are owned and saved by the server. The browser keeps a display copy and sends a session ID, revision and answer. Refresh starts a new session; login and share links are not implemented. API credentials remain server-side. In AI mode, answers go to the configured model provider.

## Development and evaluation

Python 3.12 is the Docker runtime. No third-party Python packages or frontend build tools are required.

```sh
conda env create -f environment.yml
conda activate apertus-interview-coach
cd track_2a
make test
python src/web.py --provider demo
```

All 59 application tests pass. The latest German hybrid comparison reuses 77 saved candidate answers from six scenarios, with the exact preceding v8 conversation for each independent response: 188 coach calls, averaging 2.44 per answer (highest case average 2.77). This is a fixed-context response comparison, not a coherent new full interview or a validated benchmark. Six reviews remain drafts. Support and visible evidence improve, but repetitive transitions, incomplete company replies and unsupported assessment interpretations persist. The earlier v7/v8 runs and labels are preserved.

The challenge weights performance at 50%, consistency at 25% and innovation at 25%, with practicality as a required gate. Recorded call efficiency is below five calls per answer, but hosted inference does not establish operation below 32 GB VRAM. Grounding, candidate-question handling, repetition and follow-up selection remain weaknesses. See the [technical report](track_2a/technical_report.md) for measurements, review findings and limitations.

## Repository

| Path | Purpose |
| --- | --- |
| [track_2a/README.md](track_2a/README.md) | Setup, deployment and session behaviour |
| `track_2a/src/` | Web server, controller, model clients, prompts, interface and tests |
| `track_2a/data/interview/` | Public runtime questions, fictional postings, rubric and guidelines |
| `track_2a/Makefile` | Web launch and test commands |
| [track_2a/technical_report.md](track_2a/technical_report.md) | Approach, visual architecture and development results |
| `environment.yml` | Optional Conda environment |

Credentials, sessions, experimental tooling, generated runs and manual-review labels remain local and are excluded from the published application. The local review interface is not a submission dependency.

## License

See [LICENSE](LICENSE). Bundled organiser resources retain their upstream attribution and usage conditions; see [data provenance](track_2a/data/interview/README.md).
