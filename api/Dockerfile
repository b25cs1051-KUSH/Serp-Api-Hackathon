# PharmaWatch API (FastAPI + semantic cache). Build from the repo root:
#   docker compose up --build        (or: docker build -f api/Dockerfile .)
# Keys are never baked in: docker-compose.yml passes .env at runtime.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf

WORKDIR /app

# CPU-only PyTorch first: the default wheel pulls ~2 GB of CUDA libraries this API never uses.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt ./
COPY api/requirements.txt ./api/
RUN pip install -r requirements.txt

# Non-root from here on; owning the model dir up front avoids a second copy from a later chown.
RUN useradd --create-home --uid 10001 app && mkdir -p /opt/hf && chown app /opt/hf
USER app

# Download the embedding model at build time, so the first search doesn't wait for it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY serpapi_cache ./serpapi_cache
COPY pharmawatch ./pharmawatch
COPY notes/postal_codes_delivery_rules.json ./notes/
COPY api ./api

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
