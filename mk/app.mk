.PHONY: app-up app-down app-logs app-restart app-build

app-up:
	docker-compose up -d app

app-down:
	docker-compose stop app

app-logs:
	docker-compose logs -f app

app-restart:
	docker-compose restart app

app-build:
	docker-compose build app

