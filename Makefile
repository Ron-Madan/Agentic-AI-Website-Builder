.PHONY: install dev test lint format clean run

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

# Development
dev:
	python scripts/run_dev.py

# Testing
test:
	python scripts/run_tests.py

test-quick:
	python -m pytest tests/ -v

# Code quality
lint:
	flake8 src/ tests/
	mypy src/

format:
	black src/ tests/ scripts/
	isort src/ tests/ scripts/

format-check:
	black --check src/ tests/ scripts/
	isort --check-only src/ tests/ scripts/

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/

# Run application
run:
	uvicorn src.agentic_web_app_builder.api.main:app --reload

# Database (for future use)
db-upgrade:
	alembic upgrade head

db-downgrade:
	alembic downgrade -1

db-revision:
	alembic revision --autogenerate -m "$(message)"