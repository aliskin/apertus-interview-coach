# Manual review tool

A local browser tool for reviewing the coach, not grading the candidate. It uses the same public feedback guidelines as the coach. It does not call a model or generate labels automatically. Reviewers choose **Meets**, **Violates**, **Not sure** or **Not applicable**, write their reasoning, cite exact coach passages, and save each example as a draft or validated review.

## Start from a fresh checkout

Python 3.12 or newer is sufficient; no third-party packages are required. From the repository root:

```sh
make -C track_2a review-demo
```

Open **http://127.0.0.1:8081**. The demonstration is fictional, makes no model calls and is not an evaluation dataset. Stop with Ctrl+C. For an existing local dataset, use:

```sh
make -C track_2a review
```

Change the port with `REVIEW_PORT=8082`. The coach and review tool are separate servers; this target starts only the review tool.

## Import completed interviews

From `track_2a`, import server-owned session JSON or experiment records containing a `session` object:

```sh
python3 src/review/prepare.py --run data/sessions \
  --version practice-v1 --title "Practice interviews"
make review
```

Only complete sessions with feedback are included. The importer expects a transcript, language and posting with occupation metadata. Keep separate source directories if you want to replace failed scenarios with successful reruns:

```sh
python3 src/review/prepare.py \
  --run data/runs/initial data/runs/retry \
  --version evaluation-v1 --title "Evaluation interviews"
```

Later successful records override earlier records with the same scenario ID. Failed records never replace a success. The sample stores source paths and hashes and lists omitted records; it does not hide failures from the experiment records. These directories and generated labels remain Git-ignored. To review modified outputs, create a new version: existing samples and their labels cannot silently be reused for different text.

## Review and save

- Select a version and interview in the left panel. The top summary counts saved guideline assignments, affected examples, uncertainty and validation status; it is not a candidate score or benchmark result.
- Original text is expanded by default. French/Italian English reading aids are collapsed below it; German stays untranslated. Judge language, tone and evidence using originals.
- Use the stage field and explain it. Full sessions use **Whole interview**; an introductory excerpt does not need full-session feedback.
- Use **Not applicable** when a rule has no relevant trigger or observable input. Explain, for example: “Not applicable: cannot assess from this excerpt. No voice or gesture is available.” Use **Not sure** for genuine uncertainty.
- Exact evidence quotes must occur in the coach's original output. Highlights link the passage to its guideline. Notes can explain missing elements and quote candidate input; do not put candidate/reference text in the coach-evidence field.
- Click **Save example** after editing. Mark **I have validated these labels** only when you have checked the draft. Concurrent stale saves are rejected instead of overwriting a newer review.
- **Export saved labels** downloads that version's labels. Files are saved atomically on the computer running the server.

## Optional English reading aids

Translations are a separate opt-in Apertus request; they are not part of the coach's measured call budget. Export the provider configuration in your shell first. For a newly imported version:

```sh
python3 src/review/translate.py --version practice-v1 \
  --sample versions/practice-v1/sample.json --languages fr it --workers 4
```

This caches English translations under `data/manual_review/versions/`. The prompt asks to preserve repeated wording, mistakes and unsupported claims. Hash checks ensure the translations belong to the actual source turns; they do not guarantee translation quality. Use the translation-issue checkbox if an English rendering changes the meaning. The original transcript and labels are not rewritten. Model configuration uses the same server-side `LLM_API_KEY`, `LLM_BASE_URL` and `LLM_NAME` as the coach.

## Archive a version

Stop the review server before moving data:

```sh
python3 src/review/prepare.py --archive practice-v1
make review
```

The version moves into the collapsed **Archive** section, retaining its labels and reading aids. The portal discovers `versions/*/version.json` and `archive/*/version/version.json`; it has no hard-coded experiment list. Start with `--default-version VERSION` if several active versions exist. `--data-root PATH` selects a separate data directory; all configured sample, translation and label paths must stay inside it.

## Docker

The application image also contains the review code and static files, but its default entrypoint starts the coach. After building the application image using the project instructions, a fresh review demonstration can be prepared and served without model credentials:

```sh
mkdir -p data/manual_review
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/data/manual_review:/app/track_2a/data/manual_review" \
  --entrypoint python apertus-interview-coach src/review/prepare.py --demo
docker run --rm --user "$(id -u):$(id -g)" \
  -p 127.0.0.1:8081:8081 \
  -v "$PWD/data/manual_review:/app/track_2a/data/manual_review" \
  --entrypoint python apertus-interview-coach \
  src/review/portal.py --host 0.0.0.0 --port 8081
```

Run these from `track_2a`. Existing review datasets use only the second command. The host port stays bound to loopback. The tool is for local review, with no login or public-sharing feature. The Docker image contains neither your datasets nor saved labels.

## Files

`portal.py` serves the interface and discovers versions; `store.py` validates annotations and saves them; `prepare.py` imports/demoes/archives datasets; `translate.py` optionally prepares reading aids; `static/` contains the browser interface. All generated review data stays under ignored `track_2a/data/manual_review/`. Tests run with the application suite via `make -C track_2a test`.
