.PHONY: db-up db-down db-logs db-restart db-clean

db-up:
	docker-compose up -d postgres

db-down:
	docker-compose stop postgres

db-logs:
	docker-compose logs -f postgres

db-restart:
	docker-compose restart postgres

db-clean:
	docker-compose down postgres -v

