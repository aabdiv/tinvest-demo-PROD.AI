FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && groupadd --gid 10001 demo \
    && useradd --uid 10001 --gid demo --no-create-home demo \
    && mkdir /state && chown demo:demo /state

COPY --chown=demo:demo backend/ backend/
COPY --chown=demo:demo frontend/ frontend/
COPY --chown=demo:demo scripts/ scripts/
COPY --chown=demo:demo data/universe.json data/universe.json

USER demo
EXPOSE 8000
CMD ["python", "-m", "scripts.serve_demo"]
