# AI-Powered Job Interview Coach

An Apertus-based interview practice app for teenagers preparing for their first job or apprenticeship. Built for Hack Apertus, Track 2a — Academia, and the FHGR challenge.

**Status:** Runnable web prototype with three-question practice sessions, adaptive coaching, and a final recap. Benchmark datasets and consumer-hardware validation are still pending.

## Features

- English, German, French, and Italian interfaces and coaching instructions.
- Scenarios for IT, retail, hospitality, and technical apprenticeships, plus a first part-time or summer job.
- One strength, one improvement, and an adaptive follow-up after each of the first two answers.
- A neutral answer placeholder and optional guidance matched to the next question.
- Final feedback, transcript downloads, and responsive desktop/mobile layouts.
- One model call per candidate answer; credential-free demo mode makes no calls.

## Quick start

Install and start Docker Desktop or a compatible Docker engine, then run:

```sh
cd track_2a
make web-demo
```

Open **http://localhost:8080**. Demo mode uses fixed example responses; it does not provide personalised AI coaching. Stop with Ctrl+C.

For Apertus credentials, local Ollama testing, deployment options, and batch evaluation, see the [implementation README](track_2a/README.md). `make web` runs the configured coach; `make run` is an alias for the web app.

## Architecture

The browser holds the conversation and sends it to a Python standard-library HTTP server. The server validates each request and calls the configured Apertus endpoint or local Ollama server. Docker packages the web server and static interface; model weights are served separately. API credentials stay on the server.

The opening question is prepared per scenario. Answers one and two each trigger a single call for feedback, an adaptive question, and its optional hint. Answer three triggers a final recap. The app does not automatically judge the coach during web sessions.

## Development

Python 3.12 is the supported Docker runtime. No third-party Python packages or frontend build tools are required. For a local environment:

```sh
conda env create -f environment.yml
conda activate apertus-interview-coach
cd track_2a
make test
python src/web.py --provider demo
```

## Assessment and next steps

The challenge scores performance at 50%, consistency at 25%, and innovation at 25%, with runtime practicality as a required gate. The app uses one model call per answer, but the selected Apertus serving configuration still needs measurement against the under-32-GB VRAM requirement. A remote endpoint or development model does not establish compliance.

Next steps are benchmark datasets, human-reviewed multilingual feedback, consistency measurement, and local Apertus runtime validation. Current example cases and judge scores are provisional and do not measure a student's employability.

## Repository

| Path | Purpose |
| --- | --- |
| [track_2a/README.md](track_2a/README.md) | Setup, deployment, and evaluation instructions |
| `track_2a/src/` | Web server, provider adapters, prompts, and interface |
| `track_2a/data/` | Example cases and ignored local outputs/configuration |
| `track_2a/Makefile` | Web launch and test commands |
| [track_2a/technical_report.md](track_2a/technical_report.md) | Technical report |
| `environment.yml` | Optional Conda environment |

Personal guides and local review/terminal tools are excluded from the published application.

## License

See [LICENSE](LICENSE).
