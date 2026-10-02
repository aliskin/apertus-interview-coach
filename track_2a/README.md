# AI-Powered Job Interview Coach — Implementation

Part of Hack Apertus Track 2a — Academia, for the FHGR challenge.
See the [project overview](../README.md) for setup and current status.

## User experience

TODO: Describe the intended interview practice flow.

## Architecture

TODO: Define the application components and how they interact.

## Use of Apertus

The first experiment calls a configurable OpenAI-compatible Apertus endpoint to generate follow-up questions and coaching feedback. Set the provider's endpoint and model identifier when API access is available.

## Data

The first experiment uses four cases derived from the [fictional English scenario](docs/first_interview_scenario_en.md), stored in `data/first_interview_en.json`. Generated responses and evaluation reports are stored locally in `data/runs/`, which is ignored by Git.

## Running the application

Follow the [first experiment guide](docs/first_experiment.md) to run the Python command-line experiment. It requires no additional Python packages. A full application, Docker setup, and `make run` are still to be implemented.

## Evaluation

An Ollama model judges each response against a stage-specific rubric and saves scores, explanations, and evidence. The default judge is `qwen3.5:9b`. See the [guide](docs/first_experiment.md#reading-the-evaluation) for interpretation and limitations.

## Limitations

The experiment tests follow-ups and feedback independently on four English cases. It does not yet test a complete conversation or the target languages. Judge scores require human review and are not a measure of student ability or employability.

## Technical report

Record implementation decisions and results in [technical_report.md](technical_report.md).
