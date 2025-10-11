# Makefile

Система команд для управления сервисами Agent Lab.

## Основные команды

```bash
make build    # Собрать образы
make up       # Запустить все сервисы
make down     # Остановить все сервисы
make logs     # Логи всех сервисов
make clean    # Удалить все (включая volumes)
make help     # Показать все команды
```

## Отдельные сервисы

Каждый сервис имеет набор команд: `up`, `down`, `logs`, `restart`, `build`

```bash
# База данных
make db-up
make db-logs
make db-restart
make db-clean

# Приложение
make app-up
make app-logs
make app-restart
make app-build

# Worker
make worker-up
make worker-logs
make worker-restart
make worker-build

# SGR сервис
make sgr-up
make sgr-logs
make sgr-restart
make sgr-build
```

## Тесты

Запуск тестов в docker-compose:

```bash
# По умолчанию в 4 воркерах (без интеграционных тестов)
make test

# Все тесты включая интеграционные
make test-all

# Указать количество воркеров
make test WORKERS=8
make test-all WORKERS=2

# Только запустить окружение
make test-up

# Только остановить окружение
make test-down
```

## Структура

```
Makefile         # Главный файл с основными командами
mk/
  ├── db.mk      # Команды для БД
  ├── app.mk     # Команды для приложения
  ├── worker.mk  # Команды для worker
  ├── sgr.mk     # Команды для SGR
  └── test.mk    # Команды для тестов
```

Все модули подключены в главный `Makefile` через `include`.

