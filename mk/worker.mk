.PHONY: worker-up worker-down worker-logs worker-restart worker-build
.PHONY: taskiq taskiq-reload taskiq-prod
.PHONY: taskiq-scheduler taskiq-scheduler-reload

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

# TaskIQ worker
# ВАЖНО: --workers 1 обязателен для taskiq-postgres, иначе NOTIFY дублирует задачи


