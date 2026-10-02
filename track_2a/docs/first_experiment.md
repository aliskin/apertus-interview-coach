# First Apertus experiment

This command-line experiment uses the fictional English scenario in [first_interview_scenario_en.md](first_interview_scenario_en.md). It requires Python 3.12 and no additional Python packages.

All commands below run from the repository root, after `conda activate apertus-interview-coach`.

## 1. Try the judge before the Apertus key arrives

Ensure Ollama is running (open the Ollama app, or run `ollama serve` in another terminal). Your machine currently has `qwen3.5:9b` and `llama3:8b` installed; `ollama list` lists available models.

Create a run containing the handwritten scenario responses, then evaluate it with the local judge:

```bash
python track_2a/src/experiment.py generate --provider sample --output track_2a/data/runs/sample.json
python track_2a/src/experiment.py evaluate --input track_2a/data/runs/sample.json --output track_2a/data/runs/sample_judged.json
```

The default judge is `qwen3.5:9b`. Change it with `--model llama3:8b` or `JUDGE_MODEL`. Nothing is downloaded automatically. The first request may take longer while Ollama loads the model. Each request has a five-minute timeout.

These are judgments of handwritten examples, **not Apertus results**. Read the explanations and compare them with your own assessment. For a simple sanity check, copy the sample JSON, replace one response with something clearly unsuitable, and check whether the relevant scores fall. Do not assume the judge is calibrated just because it produces valid JSON.

To try an actual local coach before API access:

```bash
python track_2a/src/experiment.py generate --provider ollama --model llama3:8b --output track_2a/data/runs/local.json
python track_2a/src/experiment.py evaluate --input track_2a/data/runs/local.json --output track_2a/data/runs/local_judged.json
```

This uses different coach and judge models but is still a local smoke test, not an Apertus experiment.

## 2. Configure Apertus when access arrives

The client assumes your provider offers an OpenAI-compatible `POST /chat/completions` endpoint. Confirm this with your provider; no specific Apertus hosting service is assumed.

Create `track_2a/data/.env` in your editor with the following contents, replacing the placeholders with the supplied API base URL (including `/v1` or another required prefix), exact model identifier, and key:

```bash
export LLM_BASE_URL='https://YOUR_PROVIDER/v1'
export LLM_NAME='YOUR_APERTUS_MODEL_ID'
export LLM_API_KEY='YOUR_API_KEY'
export OLLAMA_BASE_URL='http://127.0.0.1:11434'
export JUDGE_MODEL='qwen3.5:9b'
```

The local `data/.env.example` file is not tracked or required. Then load it into your shell:

```bash
source track_2a/data/.env
python track_2a/src/experiment.py generate --provider apertus --output track_2a/data/runs/apertus_01.json
python track_2a/src/experiment.py evaluate --input track_2a/data/runs/apertus_01.json --output track_2a/data/runs/apertus_01_judged.json
```

The script reads exported environment variables; it does not automatically load `.env`. The `.env` and `data/runs/` paths are ignored by Git. Credentials are not included in run artifacts. Apertus mode sends the fictional conversations to your configured provider; evaluation sends the saved conversations to the configured Ollama server, which defaults to localhost.

Use a new output filename for each run: existing files are never overwritten. Evaluation creates the report before calling the judge and saves it atomically after each case. If interrupted, completed cases remain available with report status `in_progress`; choose a new filename to rerun (automatic resume is not implemented).

## What is being tested?

The dataset has four independent cases: Path A follow-up, Path A feedback, Path B follow-up, and Path B feedback.

- Follow-up generation sees only the opening question and opening answer.
- Feedback generation sees the scenario's **fixed follow-up and matching student reply**. It does not use the newly generated follow-up. This avoids giving the coach an answer to a question it never asked.

This isolates the two skills. It does not test a complete adaptive conversation. A later interactive experiment should let a person answer the generated follow-up.

Edit `data/first_interview_en.json` to change inputs and `src/prompts/coach.txt` to change coaching instructions. Sample responses are used only by sample mode, never sent to Apertus or the judge as reference answers.

## Reading the evaluation

The rubric in `src/experiment.py` uses stage-specific criteria:

| Stage | Criteria |
| --- | --- |
| Follow-up | Adaptation, grounding, supportive tone, one-question flow |
| Feedback | Grounding, actionable improvement, supportive tone, student ownership |

Each criterion receives a score from 1 (fails) to 5 (fully meets), an explanation, and evidence. The judge instructions in `src/prompts/judge.txt` define the intermediate anchors. JSON structure and score ranges are validated; quote accuracy and judgment quality still need human review.

The results include per-case scores and descriptive averages per stage, not a pass/fail decision. Empty fields, invalid scores, malformed JSON, and judge request failures produce warnings and do not stop later cases. Each case saves its parsed `scores` when available, `raw_response` when received, `warnings`, and `status` (`ok` or `warning`). Warning cases have a null mean and are excluded from stage averages; `valid_cases_by_stage` shows how many cases contributed. A stage with no valid cases has a null average. The final report status is `completed` or `completed_with_warnings`. Configuration/input errors and inability to save files still stop the command. Inspect low-scoring criteria and their evidence before changing the coach prompt. Try one prompt change at a time on the same inputs.

Generation records the model, prompt, inputs, outputs, and timestamp. Evaluation records its model, rubric, prompt, seed, and source-file hash. Temperature is zero, but repeat runs can still differ; pin model versions when comparing experiments. A local LLM can misjudge answers or be influenced by instructions inside them despite the judge prompt. Four English examples cannot establish coaching effectiveness or German, French, Italian, dialect, or speech support.

## Tests

```bash
python -m unittest discover -s track_2a/src/tests -v
```

These checks use mocked API responses and require no key or running model. They cover the conversation split, API request construction, secret exclusion, invalid judge scores, truncated output handling, warning preservation, continuation after judge failures, and checkpoints surviving interruption.

## API references

The judge uses Ollama's [chat endpoint](https://docs.ollama.com/api/chat) and [JSON-schema structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Initial local check

The first local run with `qwen3.5:9b` gave all four handwritten examples 5/5. This confirms the pipeline runs, not that the coach or judge is validated. Inspection found abbreviated evidence quotes and an explanation that overstated what a response explicitly said. Review evidence manually before relying on the scores. Local result files are in `data/runs/sample_judged.json` when generated; they are not committed.

A deliberately unsuitable follow-up that judged the student and encouraged fabricated experience received 1/5 on every criterion. This is a basic negative-control check, not broad judge calibration.
