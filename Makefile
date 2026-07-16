.PHONY: install install-azure run demo test lint docker-build docker-up

install:
	pip install -r requirements-dev.txt

install-azure:
	pip install -r requirements.txt -r requirements-azure.txt

run:
	uvicorn app.main:app --reload --port 8000

demo:
	python scripts/demo.py

test:
	pytest -q

lint:
	ruff check app ingestion scripts tests

docker-build:
	docker build -t knowledgeforge:local .

docker-up:
	docker compose up --build
