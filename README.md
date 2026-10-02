# AI-Powered Job Interview Coach

A project for Hack Apertus, Track 2a — Academia, based on the **FHGR: AI-Powered Job Interview Coach** challenge.

**Status:** First experiment. An English interview scenario, an Apertus API client, and a local Ollama judge are available. The full application is still to be defined.

## Project idea

TODO: Describe who the coach is for, the problem it addresses, and the proposed approach.

## Features

TODO: Define the core features and the scope of the first prototype.

## Local setup

Create and activate the Conda environment from the repository root:

```bash
conda env create -f environment.yml
conda activate apertus-interview-coach
```

If the environment already exists, only run the activation command.
The environment currently includes Python 3.12 and pip. Project dependencies will be added as the implementation takes shape.

## Running the project

Start with the [first experiment guide](track_2a/docs/first_experiment.md). It includes a sample mode that works before an Apertus API key is available, plus instructions for generating and evaluating Apertus responses. The full application and Docker setup are not implemented yet.

## Repository structure

| Path | Purpose |
| --- | --- |
| `environment.yml` | Conda environment definition |
| `track_2a/README.md` | Implementation outline |
| `track_2a/src/` | Application code |
| `track_2a/data/` | Project data |
| `track_2a/docs/` | Design notes and diagrams |
| `track_2a/Makefile` | Application run command (to be implemented) |
| `track_2a/technical_report.md` | Architecture, evaluation, and limitations |

## Next steps

- Define the target users and interview practice scenario.
- Choose the scope of the first prototype.
- Decide how to use Apertus.
- Define how to evaluate the coach.

## License

See [LICENSE](LICENSE).
