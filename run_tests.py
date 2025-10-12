#!/usr/bin/env python3
"""
Запуск архитектурных тестов.
Перед запуском нужно поднять БД: make up
"""
import subprocess
import sys

def main():
    print("🧪 Запуск архитектурных тестов...")
    print("📋 Убедитесь что БД запущена: make up")
    
    try:
        # Запускаем pytest с архитектурными тестами
        subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/arch/", 
            "-v", 
            "-s",
            "--tb=short"
        ], check=True)
        
        print("✅ Все тесты прошли успешно!")
        return 0
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Тесты завершились с ошибкой: {e}")
        return 1
    except KeyboardInterrupt:
        print("⏹️ Тесты прерваны пользователем")
        return 1

if __name__ == "__main__":
    sys.exit(main())
