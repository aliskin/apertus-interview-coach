#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -f data/.env ]; then
    set -a
    . ./data/.env
    set +a
fi
coach_provider="${COACH_PROVIDER:-apertus}"
coach_model="${COACH_MODEL:-llama3:8b}"
case "$coach_provider" in
    apertus)
        : "${LLM_API_KEY:?Set LLM_API_KEY in data/.env or your environment}"
        : "${LLM_BASE_URL:?Set LLM_BASE_URL in data/.env or your environment}"
        : "${LLM_NAME:?Set LLM_NAME in data/.env or your environment}"
        ;;
    ollama) ;;
    demo) ;;
    *) echo 'COACH_PROVIDER must be apertus, ollama, or demo.' >&2; exit 1 ;;
esac
# Docker Desktop may be installed without its CLI symlinks on PATH.
if ! command -v docker >/dev/null 2>&1; then
    for docker_bin in /Applications/Docker.app/Contents/Resources/bin "$HOME/Applications/Docker.app/Contents/Resources/bin" "$HOME/.docker/bin"; do
        if [ -x "$docker_bin/docker" ]; then
            PATH="$docker_bin:$PATH"
            export PATH
            break
        fi
    done
fi
command -v docker >/dev/null 2>&1 || {
    echo 'Docker CLI was not found. Install Docker or add its bin directory to PATH. See README.md for setup instructions.' >&2
    exit 1
}
if ! docker info >/dev/null 2>&1; then
    echo 'Docker is installed, but its engine is unavailable. Start Docker Desktop and wait until the engine is running, then retry. If it is already running, check docker context ls and DOCKER_HOST.' >&2
    exit 1
fi
mkdir -p data/profiles
set -- --provider "$coach_provider" --model "$coach_model"
if [ -n "${PROFILE:-}" ]; then
    case "$PROFILE" in
        data/profiles/*.json) ;;
        *) echo 'PROFILE must be a JSON file under data/profiles/.' >&2; exit 1 ;;
    esac
    case "$PROFILE" in *..*) echo 'PROFILE must not contain ..' >&2; exit 1 ;; esac
    [ -f "$PROFILE" ] || { echo 'Profile file not found.' >&2; exit 1; }
    set -- "$@" --profile "$PROFILE"
fi
docker build -t apertus-interview-coach -f src/Dockerfile src
# In a container, localhost is the container itself, not the host Ollama server.
export OLLAMA_BASE_URL="${DOCKER_OLLAMA_BASE_URL:-http://host.docker.internal:11434}"
docker run --rm --add-host host.docker.internal:host-gateway \
    -p "127.0.0.1:${WEB_PORT:-8080}:8080" \
    --user "$(id -u):$(id -g)" \
    -e LLM_API_KEY -e LLM_BASE_URL -e LLM_NAME -e OLLAMA_BASE_URL -e MAX_ANSWERS \
    -v "$PWD/data/profiles:/app/track_2a/data/profiles:ro" \
    apertus-interview-coach "$@"
