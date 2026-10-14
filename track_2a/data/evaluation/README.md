# FHGR answer-level evaluation set

This is a development evaluation set built from the published Hackapertus resources. Each case is one original question and candidate answer. It evaluates the coach's feedback and follow-up on a fixed input; it does not measure a complete adaptive interview.

## File boundary

| File | Consumer | Contents |
| --- | --- | --- |
| `coach_inputs.jsonl` | Coach runner | Case ID, question ID, language/dialect, occupation, phase, original question, candidate answer |
| `references/annotations.jsonl` | Evaluator only | Matching case ID, full original annotation, withheld answer metadata, question-bank record |
| `references/criteria.json` | Coach and evaluator | Public FHGR candidate assessment rubric (1–4, or null when unobserved) |
| `references/feedback_guidelines.json` | Coach and evaluator | Public constructive-feedback guidelines |
| `manifest.json` | Reporting | Source revision and hashes, counts, preparation choices, reference limitations |

Give the coach runner the `coach_inputs.jsonl` path and, optionally, the two public rubric/guideline files. It must not scan the dataset directory or open `references/annotations.jsonl`. Construct model messages from `question` and `answer`, plus appropriate input context and the current coaching prompts. IDs are bookkeeping and do not need to be sent to the coach model. Save predictions as records containing `case_id` and the generated output. A separate evaluator joins predictions to reference records by `case_id`, never by row position.

Physical file separation makes accidental inclusion avoidable; it is not access control. For enforced isolation, mount or copy only `coach_inputs.jsonl` and the two public rubric/guideline files into the coach runner's container.

## Preparation choices

All 706 published answers are included, with one reference record per case. The exact question attached to the answer takes precedence over the corresponding question-bank text. Eight examples have no bank question ID; their attached question remains usable. Two Swiss German answers have only a German question formulation; these case IDs are recorded in the manifest.

Quality levels, answer classes, source hints, context notes, normalized answers, nonverbal notes, candidate IDs, expected feedback, improved answers, expected follow-ups, and problem flags are withheld from coach inputs. No private candidate profile is added. This is a text-only benchmark: the evaluator must not penalize the coach for failing to observe hidden nonverbal behavior or candidate history. Reference annotations may discuss information unavailable to the coach, so assess only claims supported by visible input.

The current app supports de/fr/it/en, not a dedicated Swiss German mode. Keep the 50 Swiss German cases as a separately reported robustness subset; do not silently claim a supported dialect benchmark. German feedback for dialect cases follows guideline S4. English examples are not present in this source set.

## Comparing predictions with references

Compare supported strengths, important gaps, constructive feedback, and the suitability of the next question. Do not require exact wording, the same follow-up question, or all annotated points. The current coach does not output numerical candidate scores or the annotation's `coach_action` vocabulary; do not treat missing versions of those fields as prediction errors.

The candidate rubric is not a rubric for scoring coach quality. Use feedback guidelines to assess the coach, and candidate scores as contextual references where evidence is available. All published answer annotations are synthetic and marked unreviewed. This set is not the organizers' hidden benchmark, and no evaluation has been run yet.

No train/holdout split is assigned. If examples are later used in prompts or training, reserve separate evaluation groups, keeping related question families and translations together to avoid leakage.

## Run generation and evaluation

From the repository root, load local model configuration without displaying it:

```sh
set -a
. ./track_2a/data/.env
set +a
```

The coach uses the existing `LLM_NAME`, `LLM_BASE_URL`, and `LLM_API_KEY`. The default independent judge uses Ollama at `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`) and `JUDGE_MODEL` (default `qwen3.5:9b`). Start that server and install the selected judge model separately. Evaluation does not require the web server.

First preview a three-case smoke test (one case per de/fr/it; no requests or output file):

```sh
python3 track_2a/src/experiments/evaluate_feedback.py generate --limit 3 --dry-run \
  --output track_2a/data/runs/feedback-smoke.json
```

Then generate predictions and judge the saved outputs:

```sh
python3 track_2a/src/experiments/evaluate_feedback.py generate --limit 3 \
  --output track_2a/data/runs/feedback-smoke.json
python3 track_2a/src/experiments/evaluate_feedback.py judge \
  --predictions track_2a/data/runs/feedback-smoke.json \
  --output track_2a/data/runs/feedback-smoke-scores.json
```

`generate` defaults to `--guidance fhgr`: a compact rendering of all public candidate rubric levels and feedback rules is added to the current app prompts. This is a guideline-assisted variant, not the unchanged baseline. For an existing-instructions baseline, add `--guidance none` and choose a new output filename. Neither mode changes the live app prompts. Both reuse the current app's shared instructions, output requirements, and opening-answer task, adapting that task to a question from any interview phase. They use visible occupation/phase context instead of a browser scenario preset and do not exercise the full session controller.

Coach generation now requests the four-field JSON schema through Apertus `response_format` (`json_schema`, `strict: true`) or Ollama's schema `format`. The schema and mode are saved in the prediction report. This constrains output at the endpoint rather than relying only on prompt wording. Strict local validation still rejects malformed JSON, missing/extra fields, invalid field types, and excessive string lengths. There is no silent unconstrained fallback, automatic coach repair, or extra coach request. An unsupported endpoint, truncated response, or service failure can still fail a case. Existing runs made before schema enforcement are preserved as separate baselines.

After checking the smoke test, use `--limit 60` (the default) or `--limit 0` for all de/fr/it cases. Selection cycles deterministically across languages in source order. It is balanced by language while cases are available, but not by quality level. `--languages gsw` selects the separate dialect robustness subset. `--case-ids ID ...` selects explicit cases, overriding language selection. `--repeats 3` makes three independent coach calls per selected case; repetitions are recorded separately. The report does not yet calculate semantic agreement across repeats.

The judge scores these coach criteria from 1 (fails/harmful) to 5 (fully meets): relevance, grounding, diagnostic usefulness, actionability, constructive tone, follow-up usefulness, hint usefulness, and language/clarity. It compares the saved output with annotations and checks all feedback guidelines. It must cite evidence, record guideline violations and reference limitations, and avoid demanding reference wording. Only follow-up and hint scores may be null when a justified wrap-up has no next question. No numerical candidate-score prediction is required.

### Judge protocol 2: source separation and evidence validation

New judge runs use report schema version 3 and record `judge_protocol_version: 2`. Inputs are separated into `what_coach_saw` (question, candidate answer, visible context/language), `what_coach_generated` (actual generated reply/hint), and `reference_annotations` (explicitly unreviewed guidance, including withheld nonverbal notes). Generic hints inserted by the server are not attributed to the model. The case-specific payload is saved with each judgment for inspection.

Each criterion score and guideline violation includes:

- `evidence_type`: `quote`, `missing`, or `not_applicable`.
- `evidence_source`: `reply`, `hint`, or `none`.
- `evidence`: an exact contiguous substring of that generated field, an explicit `Missing: <element>` statement, or an explicit `Not applicable: <reason>` statement.
- `input_evidence`: exact visible question/answer quotations, with `field` (`question` or `candidate_answer`) and `quote`.

Code rejects fabricated, paraphrased, translated, ellipsized, or reference-only quotations that do not occur in the named generated field. Hint scores must quote the actual hint. Relevance, grounding, diagnostic usefulness, and K1/K3 violations require visible-input citations. Invalid input citations, such as a phone note absent from the candidate answer, are rejected. Missing required elements cannot receive scores above 3. Not-applicable evidence requires a permitted null score and no continuation. Raw rejected judgments remain saved as `judge_failed` and are excluded from averages; no silent quote repair or case-judge retry is performed.

The prompt adds anchors for unsupported praise/research/experience (grounding at most 2), irrelevant corrections to sufficient small talk (relevance/actionability at most 3, or 2 if wholly unrelated), and major visible gaps (diagnostic usefulness at most 3). Phase-specific guidance covers greetings, self-presentation, motivation, knowledge, strengths/development, hypothetical situations, future plans, candidate questions, and closing. The actual question takes precedence over a phase label. A natural transition is distinguished from an unnecessary correction; not every answer requires a past example or every annotation detail.

These guards verify source provenance and quotation integrity, not the semantic truth of all reasons or scores. A judge can still misinterpret a genuine quotation or make an incorrect absence claim. Calibration and human review remain necessary before trusting absolute scores.

To rescore existing coach predictions with the improved judge, without generating new coach answers:

```sh
python3 track_2a/src/experiments/evaluate_feedback.py judge \
  --predictions track_2a/data/runs/feedback-60.json \
  --output track_2a/data/runs/feedback-60-judge-v2.json
```

This evaluates the original saved outputs and retains their seven generation failures. The separate `feedback-json-schema-7.json` run contains replacements generated with JSON constraints; those are a distinct experiment and are not silently merged into the original baseline. `summarize` only updates summaries, so it cannot apply the improved judge to old scores. Existing reports remain readable and unchanged.

Reports include per-criterion averages by language and annotated answer quality, applicable-score counts, guideline violations, critical violations, generation/judge failures, raw outputs, actual coach messages, model IDs, configuration hashes, latency, and separate coach/judge call counts. Failed cases remain visible and are excluded from score averages. There is no conversion to an official challenge score or hardware certification. Output files are checkpointed after each case and existing files cannot be overwritten; automatic retries and resume are not implemented.

## Initial judge calibration selection

The initial selection contains 12 single-answer pairs (24 feedback texts): six German, three French, and three Italian. It covers 11 failure types: harsh tone, overpraise, jargon, hallucinated evidence (two cases), grading instead of coaching, wrong language, ignored distress, vague advice, personality labeling, fear, and no next step. Grounding has extra coverage because it failed in our manual review. Length, comparison, and full-interview examples are outside this first selection.

- `references/calibration_pairs.jsonl`: the 12 original source records, unchanged, including good/poor labels and explanations. Evaluator/human review only.
- `calibration_inputs.jsonl`: the same 12 pairs with neutral A/B feedback labels and neutral pair IDs. This is the file the calibration judge should see.
- `references/calibration_targets.jsonl`: expected winner, original example ID, failure mode, guideline IDs, and explanations. Evaluator only.
- `calibration_manifest.json`: source hash, selected IDs, selection rationale, ordering seed, language/failure counts, and the 18 remaining source IDs.

Preferred responses are shuffled with seed 42 and counterbalanced: six A and six B. Do not give the judge the selected source records, targets, or manifest; these reveal the expected answers. Use a fresh judge conversation per response. Evaluate feedback quality and supported guideline violations; do not penalize these reference feedback texts for lacking the live app's next-question/hint packet. The existing `judge` command evaluates app predictions, not this pairwise calibration format. Use the separate calibration runner:

```sh
python3 track_2a/src/experiments/calibrate_judge.py --model qwen3.5:9b \
  --output track_2a/data/runs/calibration-12-qwen9b.json
```

The runner makes 24 independent feedback judgments (A and B separately for each pair), using six criteria: relevance, grounding, diagnostic usefulness, actionability, constructive tone, and language/clarity. Each request includes only one response, its question/answer context, public guidelines, and the improved judge instructions. No expected preference, failure mode, source ID, reference feedback, or guideline labels are sent. Expected targets are loaded after all model calls and joined by pair ID.

The JSON and Markdown reports show valid-response/pair coverage, good-versus-poor mean scores, ties and incorrect rankings, ranking accuracy on valid pairs and across all selected pairs, expected guideline-violation recall, and good responses flagged for human review. Extra guideline IDs are not automatically classified as false accusations because synthetic reference lists may be incomplete. Quote/source validation uses the same checks as the main judge; failed judgments are preserved and excluded from valid-pair averages. There are no automatic retries, coach calls, or qualitative-recap calls. Choose a new output filename for a repeat run.

Published preferences are synthetic guidance, not certified human labels. If these pairs are used to tune judge prompts, use separately reserved pairs for subsequent validation rather than reporting the calibration score as an independent benchmark.

## Quantitative summary and qualitative recap

### Stage-aware coach rerun (coach prompt version 2)

`src/interview_context.py` maps question metadata to semantic interview stages and subtypes. The prompt policy in `src/prompts/web/stage_policy.txt` handles brief neutral small talk, self-presentation, job/company interest, occupational knowledge, and learning/future goals. It overrides a mandatory strength/improvement on every turn, preserves respectful tone, restricts unsupported skill inferences, and gives stage-specific brevity targets. Knowledge can be probed for missing dimensions without requiring past professional experience. The original public rubric/guidelines are unchanged; the phase policy clarifies their scope in ongoing turns.

From the repository root, load the existing local credentials and rerun the exact baseline inputs:

```sh
set -a
source track_2a/data/.env
set +a
python3 track_2a/src/experiments/evaluate_feedback.py generate \
  --provider apertus --guidance fhgr \
  --baseline track_2a/data/runs/feedback-60.json \
  --output track_2a/data/runs/feedback-60-stage-aware-v2.json
```

`--baseline` overrides normal language/limit selection. It takes every unique input in the baseline's order, including generation failures, and rejects changed or missing inputs. It never includes old outputs, judge scores, annotations, or manual labels in the new model request. This is 60 calls, one per answer, with no retry or judge calls. Outputs are checkpointed, and an existing output filename is rejected rather than overwritten. Each record saves its explicit question context and assembled request; the report records prompt/policy hashes and the baseline hash. The current strict JSON constraints remain enabled; the original baseline predated those constraints, so generation-format improvements cannot be attributed solely to the stage-aware prompt.

After inference, extract the original ten review IDs, repetitions, and order:

```sh
python3 track_2a/src/experiments/sample_feedback_review.py \
  --source track_2a/data/runs/feedback-60-stage-aware-v2.json \
  --template track_2a/data/manual_review/sample-10.json \
  --output track_2a/data/manual_review/sample-10-stage-aware-v2.json
```

The extractor makes no model calls, refuses to substitute a different case if one of the ten failed, and never overwrites an existing sample. New coach replies and hints need new English translations and a separate label file before opening the review interface; old translations and validated labels must not be reused for changed output.

Future session integration: `web.build_messages` and `web.respond` accept a validated `question_context` on each call, independent of turn count. Evaluation supplies this explicitly from question metadata. The existing browser session does not yet persist/update semantic stage metadata: its fallback policy uses the actual dialogue, with context marked unspecified. A future server-side session controller should store the current question's stage/subtype and update them when the next question is accepted, not reclassify an off-topic candidate answer. No additional classifier call is required. Recap requests explicitly use Feedback/session_recap. The six-stage classification is separate from first-answer/follow-up/recap response tasks.

### Judge language and output examples (protocol 3)

Both evaluation and calibration use the same system-prompt builder in `track_2a/src/experiments/evaluate_feedback.py`. `prompts/evaluation_judge.txt` contains English instructions and scoring anchors; the public rubric and feedback guidelines are rendered from their existing English fields by `load_guidance`. Original multilingual source JSON files are preserved. `prompts/evaluation_judge_examples.txt` adds two invented, compact output excerpts: a wrong-language response and a missing next practice step. They are not calibration cases or complete output templates; the supplied schema determines the complete set of required criteria (eight for evaluation, six for calibration).

Judge reasons, reference warnings, and absence explanations must be in English. Questions, answers, coach text, and exact evidence quotes remain in their original language. The coach's required interview language is assessed separately: a predominantly wrong-language response receives at most 2 for language/clarity and a major S4 violation. Any future supplementary translations are reading aids only; originals remain authoritative. This change does not generate or attach supplementary translations yet.

New reports record `judge_protocol_version: 3` and the assembled system prompt. Existing calibration reports are preserved. These changes have not yet been validated by another model run; rerun calibration with a new output filename before comparing results. The examples clarify the evidence format but do not guarantee semantic correctness.

`judge` now saves both the requested JSON report and a readable Markdown report with the same basename. For example, `feedback-smoke-scores.json` has a companion `feedback-smoke-scores.md`. Generated reports stay in the existing ignored `track_2a/data/runs` directory.

The JSON report contains:

- `results`: each case/repetition's eight criterion scores, reasons, evidence, guideline violations, and reference warnings.
- `summary.scores_by_group`: criterion means, unique-case counts, population standard deviation, counts below 3, and normalized 0–100 scores for the overall set, each language, and each reference-quality group.
- `summary.aggregate`: the overall score on the 1–5 scale and normalized 0–100 scale.
- `summary.aggregates_by_group`: overall scores for each language and reference-quality group.
- `summary.language_balanced_score_out_of_5`: equal-weight mean of available de/fr/it language scores, separately from the primary case-based score; dialect is reported separately.
- `summary.case_scores`: each unique case's criterion means and aggregate across its applicable criteria.
- `summary.coverage`: total/scored cases, total/valid judgments, and whether every prediction was successfully judged.
- `qualitative_recap`: judge-produced overview, strengths, weaknesses, critical findings, recommended changes with case IDs, and limitations.

Calculation: average valid repetitions within each case and criterion; then average cases for each criterion; then average the applicable criterion means with equal weights. No applicable score is replaced with zero, and missing judgments are not counted as successes. The 0–100 conversion is `(mean - 1) / 4 * 100`: 1 maps to 0, 3 to 50, 4 to 75, and 5 to 100. It is a normalized quality score, not accuracy or the percentage of successful cases. A partial-coverage score describes only valid judgments. Critical violations are displayed separately, never erased by aggregation.

The qualitative recap runs automatically after all case judgments. Every case judgment and failure is included in bounded batches; large evaluations use batch summaries followed by hierarchical reduction. All numerical calculations remain in Python. The recap model cannot replace scores. Recap calls are counted separately from per-case judging and coaching calls. Evidence in each finding must refer to a case ID in the supplied batch. This validates citations, not the semantic truth of every claim; the recap remains an interpretation of the judge's findings.

Use `judge --no-recap` to skip recap requests and write quantitative JSON/Markdown only. To add or regenerate summaries from an existing completed evaluation without judging the coach outputs again:

```sh
python3 track_2a/src/experiments/evaluate_feedback.py summarize \
  --report track_2a/data/runs/feedback-smoke-scores.json \
  --output track_2a/data/runs/feedback-smoke-summary.json
```

Add `--no-recap` for a fully offline numerical summary, or `--model OTHER_JUDGE` to use a different model for the qualitative recap only. `summarize` reuses validated successful recap batches from the saved report when the judge and batch evidence match; older reports can reuse first-level batches matching the exact case-ID list. Failed batches are regenerated. Switching the recap judge prevents reuse of the previous judge's findings. No coach responses or per-case judgments are regenerated.

Citation choices are restricted to the actual IDs in each batch's JSON schema and explicit allowed-ID list. Aggregate report labels cannot be cited as cases. A malformed recap gets at most one corrective retry; both attempts are saved and counted as offline recap requests. Unsupported findings must be removed, not given invented citations. `--recap-chunk-chars` controls the per-call evidence budget (default 24,000 characters). Judge requests use up to 4,096 output tokens; the Ollama judge is configured with a 16,384-token context and thinking disabled. If the recap fails, quantitative scores and raw recap responses are preserved and the Markdown report explains the failure.

The public candidate rubric (`criteria.json`) explains the teenager's interview skills and 1–4 levels. The public feedback guidelines describe constructive coaching behavior. The eight coach-evaluation criteria above are our own explicit development rubric. These serve different purposes and neither makes our scores the official challenge result.

For an independent OpenAI-compatible judge endpoint, set `JUDGE_BASE_URL`, `JUDGE_API_KEY`, and `JUDGE_MODEL`, then pass `--provider openai-compatible` to `judge`. These are separate from coach credentials; the API base URL must include its prefix. The code appends `/chat/completions` and rejects the same model ID for coach and judge. Judge requests are offline evaluation work and are not counted as live coaching calls. Keys are never written into reports.

## Rebuild

From the project root:

```sh
python3 track_2a/src/experiments/build_evaluation_set.py --source /Users/alisa/Work/Hackapertus
```

The command replaces generated dataset files in `track_2a/data/evaluation/`. It does not call any model or modify the upstream repository. Source revision and individual source-file hashes are recorded for reproducibility.

Repository layout constraint: do not change the directory structure of the repository root or `track_2a`. All data belongs under the existing `track_2a/data` directory, including this evaluation set. Keep evaluation scripts in the existing `track_2a/src` directory; do not create root-level `data` or `scripts` directories.

## Provenance and usage

Source: https://github.com/fhgr/Hackapertus (FHGR Hackapertus challenge resources). Retain upstream attribution and usage conditions. The upstream README provides these resources for the challenge and asks users to contact FHGR for other uses. This derived set grants no additional permission.
