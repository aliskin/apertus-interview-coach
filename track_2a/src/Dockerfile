FROM python:3.12-slim
WORKDIR /app/track_2a
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY model_client.py prompt_profile.py interview_context.py interview_controller.py web.py ./src/
COPY static/ ./src/static/
EXPOSE 8080
COPY prompts/web/ ./src/prompts/web/
COPY prompts/session/ ./src/prompts/session/
COPY interview_data/ ./data/interview/
ENTRYPOINT ["python", "src/web.py", "--host", "0.0.0.0"]
