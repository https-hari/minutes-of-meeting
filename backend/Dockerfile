# Backend image. Build from this folder:  docker build -t minutes-api backend/
# (Render builds without Docker, see ../render.yaml.) ~300 MB RAM at runtime.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8000
WORKDIR /app

COPY requirements-server.txt .
RUN pip install -r requirements-server.txt

COPY app ./app
COPY main.py .

# bake the two models into the image so the first request isn't slow
ENV MODEL_CACHE_DIR=/app/models_cache
RUN python -m app.warmup

RUN useradd -m -u 1000 user && chown -R user /app
USER user

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.api.routes:app --host 0.0.0.0 --port ${PORT}"]
