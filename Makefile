# Простые команды для Agents Lab

# Сборка образов
build:
	docker-compose build

# Запустить
up:
	docker-compose up -d

# Перезапустить с пересборкой
rebuild:
	docker-compose up -d --build

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
