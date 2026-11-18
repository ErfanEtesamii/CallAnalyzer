FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ARG WITH_WHISPER=0
RUN if [ "$WITH_WHISPER" = "1" ]; then pip install --no-cache-dir faster-whisper; fi
COPY backend/ ./backend
COPY rubric/ ./rubric
COPY config/ ./config
WORKDIR /app/backend
ENV RUBRIC_DIR=/app/rubric SELLERS_FILE=/app/config/sellers.json
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
