# Простые команды для Agents Lab

# Запустить
up:
	docker-compose up -d

# Остановить
down:
	docker-compose down

# Логи
logs:
	docker-compose logs -f

# Очистить все
clean:
	docker-compose down -v

# Тесты
test:
	python run_tests.py
