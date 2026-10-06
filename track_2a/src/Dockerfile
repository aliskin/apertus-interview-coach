FROM python:3.12-slim
WORKDIR /app/track_2a
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY experiment.py prompt_profile.py web.py ./src/
COPY static/ ./src/static/
EXPOSE 8080
COPY prompts/ ./src/prompts/
ENTRYPOINT ["python", "src/web.py", "--host", "0.0.0.0"]
