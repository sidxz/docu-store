.PHONY: help install dev-install run run-read-models test lint format clean docker-up docker-down

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies using uv
	uv sync

dev-install: ## Install development dependencies using uv
	uv sync --dev

run: ## Run the FastAPI application
	uvicorn interfaces.api.main:app --host $(or $(HOST),0.0.0.0) --port $(or $(PORT),8000) --reload

run-read-models: ## Run the MongoDB read model projector
	uv run python -m infrastructure.read_worker

test: ## Run tests with pytest
	pytest tests/ -v

lint: ## Run linting checks
	ruff check application/ domain/ infrastructure/ interfaces/ tests/
	mypy application/ domain/ infrastructure/ interfaces/ tests/

format: ## Format code with ruff
	ruff format application/ domain/ infrastructure/ interfaces/ tests/
	ruff check --fix application/ domain/ infrastructure/ interfaces/ tests/

clean: ## Clean up generated files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
	rm -rf dist build *.egg-info

docker-up: ## Start infrastructure services (EventStoreDB, NATS)
	docker-compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 5
	@echo "Services ready!"
	@echo "  - EventStoreDB UI: http://localhost:2113"
	@echo "  - Kafka: PLAINTEXT://localhost:9092"
	@echo "  - MongoDB: mongodb://localhost:27017"

docker-down: ## Stop infrastructure services
	docker-compose down

docker-clean: ## Stop services and remove volumes
	docker-compose down -v

dev: docker-up dev-install ## Set up development environment
	@echo "Development environment ready!"
	@echo "Run 'make run' to start the API server"

test:
	uv run pytest