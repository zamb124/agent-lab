.PHONY: flows-worker-up flows-worker-down flows-worker-logs flows-worker-restart flows-worker-build
.PHONY: taskiq taskiq-reload taskiq-prod
.PHONY: taskiq-scheduler taskiq-scheduler-reload

# Docker flows_worker
flows-worker-up:
	docker-compose -f docker-compose-prod.yaml up -d flows_worker

flows-worker-down:
	docker-compose -f docker-compose-prod.yaml stop flows_worker

flows-worker-logs:
	docker-compose -f docker-compose-prod.yaml logs -f flows_worker

flows-worker-restart:
	docker-compose -f docker-compose-prod.yaml restart flows_worker

flows-worker-build:
	docker-compose -f docker-compose-prod.yaml build flows_worker

# TaskIQ worker
# ВАЖНО: --workers 1 обязателен для taskiq-postgres, иначе NOTIFY дублирует задачи


