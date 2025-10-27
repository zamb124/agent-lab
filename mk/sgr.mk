.PHONY: sgr-up sgr-down sgr-logs sgr-restart sgr-build

sgr-up:
	docker-compose up -d sgr

sgr-down:
	docker-compose stop sgr

sgr-logs:
	docker-compose logs -f sgr

sgr-restart:
	docker-compose restart sgr

sgr-build:
	docker-compose build sgr

