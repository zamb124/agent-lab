.PHONY: worker-up worker-down worker-logs worker-restart worker-build
.PHONY: taskiq taskiq-reload taskiq-prod

# Docker worker (старый TaskProcessor)
worker-up:
	docker-compose up -d worker

worker-down:
	docker-compose stop worker

worker-logs:
	docker-compose logs -f worker

worker-restart:
	docker-compose restart worker

worker-build:
	docker-compose build worker

# TaskIQ worker (новый)
taskiq:
	uv run taskiq worker core.tasks.worker:broker

taskiq-reload:
	uv run taskiq worker core.tasks.worker:broker --reload

taskiq-prod:
	uv run taskiq worker core.tasks.worker:broker --workers 4

