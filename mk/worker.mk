.PHONY: worker-up worker-down worker-logs worker-restart worker-build

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

