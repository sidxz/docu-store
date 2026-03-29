COMPOSE := docker-compose -f docker-compose.yml -f docker-compose-langfuse.yml -f docker-compose-umami.yml

.PHONY: help install dev-install run run-read-models run-all stop-all test lint format clean docker-up docker-down docker-clean langfuse-seed

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies using uv
	uv sync

dev-install: ## Install development dependencies using uv
	uv sync --dev

run: ## Run the FastAPI application
	uv run uvicorn interfaces.api.main:app --host $(or $(HOST),0.0.0.0) --port $(or $(PORT),8000) --reload

run-read-models: ## Run the MongoDB read model projector
	uv run python -m infrastructure.read_worker

run-workflow-worker: ## Run the Temporal workflow orchestration worker
	uv run python -m infrastructure.pipeline_worker

run-temporal-worker: ## Run the Temporal CPU/IO workflow worker
	uv run python -m infrastructure.temporal.worker

run-llm-worker: ## Run the Temporal LLM workflow worker
	uv run python -m infrastructure.temporal.llm_worker

run-plugin-consumer: ## Run the plugin consumer (Kafka → plugin Temporal workflows)
	uv run python -m infrastructure.plugins.plugin_consumer

run-all: stop-all ## Start all services (API, read models, workflow worker, temporal workers, plugin consumer)
	@echo "Starting all services..."
	@bash -c '\
		trap "kill 0" SIGINT SIGTERM; \
		uv run uvicorn interfaces.api.main:app --host 0.0.0.0 --port 8000 --reload & \
		uv run python -m infrastructure.read_worker & \
		uv run python -m infrastructure.pipeline_worker & \
		uv run python -m infrastructure.temporal.worker & \
		uv run python -m infrastructure.temporal.llm_worker & \
		uv run python -m infrastructure.plugins.plugin_consumer & \
		echo "All services started. Press Ctrl+C to stop all."; \
		wait'

stop-all: ## Stop all services started by run-all
	@echo "Stopping all services..."
	@-pkill -f "uvicorn interfaces.api.main:app" 2>/dev/null
	@-pkill -f "infrastructure\.read_worker" 2>/dev/null
	@-pkill -f "infrastructure\.pipeline_worker" 2>/dev/null
	@-pkill -f "infrastructure\.temporal\.worker" 2>/dev/null
	@-pkill -f "infrastructure\.temporal\.llm_worker" 2>/dev/null
	@-pkill -f "infrastructure\.plugins\.plugin_consumer" 2>/dev/null
	@sleep 2
	@-pkill -9 -f "uvicorn interfaces.api.main:app" 2>/dev/null
	@-pkill -9 -f "infrastructure\.read_worker" 2>/dev/null
	@-pkill -9 -f "infrastructure\.pipeline_worker" 2>/dev/null
	@-pkill -9 -f "infrastructure\.temporal\.worker" 2>/dev/null
	@-pkill -9 -f "infrastructure\.temporal\.llm_worker" 2>/dev/null
	@-pkill -9 -f "infrastructure\.plugins\.plugin_consumer" 2>/dev/null
	@-lsof -ti:8000 | xargs kill -9 2>/dev/null
	@echo "All services stopped."

lint: ## Run linting checks
	uv run ruff check application/ domain/ infrastructure/ interfaces/ 

format: ## Format code with ruff
	uv run ruff format application/ domain/ infrastructure/ interfaces/ 
	uv run ruff check --fix application/ domain/ infrastructure/ interfaces/ 

clean: ## Clean up generated files
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
	rm -rf dist build *.egg-info

docker-up: ## Start all infrastructure services (core + Langfuse v3) and seed prompts
	$(COMPOSE) up -d
	@echo "Waiting for services to be healthy..."
	@sleep 5
	@echo "Services ready!"
	@echo "  - EventStoreDB UI: http://localhost:2113"
	@echo "  - Kafka: PLAINTEXT://localhost:9092"
	@echo "  - Kafka UI: http://localhost:5051"
	@echo "  - MongoDB: mongodb://localhost:27017"
	@echo "  - Temporal Server: localhost:7233"
	@echo "  - Temporal UI: http://localhost:8233"
	@echo "  - Qdrant UI: http://localhost:6333/dashboard"
	@echo "  - Langfuse UI: http://localhost:3000  (dev@docustore.local / devpassword)"
	@echo "  - Umami Analytics: http://localhost:3001  (admin / umami)"
	@$(MAKE) langfuse-seed

langfuse-seed: ## Seed Langfuse with default prompts from infrastructure/llm/default_prompts/
	uv run python scripts/seed_langfuse_prompts.py

docker-down: ## Stop all infrastructure services
	$(COMPOSE) down

nuke: ## Stop all services and remove volumes
	$(COMPOSE) down -v

dev: docker-up dev-install ## Set up development environment
	@echo "Development environment ready!"
	@echo "Run 'make run' to start the API server"

test: ## Run tests with pytest
	uv run pytest tests/ -v --cov=application --cov=domain --cov=infrastructure --cov-report=xml --cov-report=term-missing

test-quick: ## Run tests without coverage
	uv run pytest tests/ -v

docker-build: ## Build backend Docker image locally
	docker build -t sidxz/docu-store:dev .

docker-build-web: ## Build frontend Docker image locally
	docker build -t sidxz/docu-store-web:dev ../web/