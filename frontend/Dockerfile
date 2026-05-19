FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY Home.py api_client.py dashboard_support.py ./
COPY pages ./pages

RUN pip install --upgrade pip && pip install -e .

EXPOSE 8501

CMD ["streamlit", "run", "Home.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
