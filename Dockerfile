FROM python:3.12-slim

WORKDIR /srv/knowledgeforge

# Install dependencies first so code changes do not bust the layer cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY ingestion/ ingestion/
COPY sample_docs/ sample_docs/
COPY scripts/ scripts/

# Non-root runtime user.
RUN useradd --create-home forge
USER forge

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
