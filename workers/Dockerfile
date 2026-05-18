FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY ingest.py etl.py train_model.py predict.py ./

RUN pip install --upgrade pip && pip install -e .

CMD ["python", "ingest.py", "--help"]
