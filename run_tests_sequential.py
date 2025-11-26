#!/usr/bin/env python3
"""
Скрипт для последовательного запуска всех тестов по файлам.
Показывает прогресс и результаты каждого файла.
"""

import subprocess
import sys
from pathlib import Path

def find_test_files():
    """Находит все тестовые файлы"""
    test_dir = Path("tests")
    test_files = []
    
    for test_file in test_dir.rglob("test_*.py"):
        if test_file.is_file() and not test_file.name.startswith("__"):
            test_files.append(str(test_file.relative_to(Path.cwd())))
    
    return sorted(test_files)

def run_test_file(test_file):
    """Запускает один тестовый файл"""
    print(f"\n{'='*80}")
    print(f"Запуск: {test_file}")
    print(f"{'='*80}")
    
    result = subprocess.run(
        ["uv", "run", "pytest", test_file, "-v", "--tb=line"],
        capture_output=True,
        text=True
    )
    
    # Парсим результаты
    output_lines = result.stdout.split('\n')
    passed = 0
    failed = 0
    errors = 0
    skipped = 0
    
    for line in output_lines:
        if "passed" in line.lower() and "failed" not in line.lower():
            # Ищем строку типа "5 passed"
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "passed":
                    try:
                        passed = int(parts[i-1])
                    except:
                        pass
        if "failed" in line.lower():
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "failed":
                    try:
                        failed = int(parts[i-1])
                    except:
                        pass
        if "error" in line.lower() and "failed" not in line.lower():
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "error" or part == "errors":
                    try:
                        errors = int(parts[i-1])
                    except:
                        pass
        if "skipped" in line.lower():
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "skipped":
                    try:
                        skipped = int(parts[i-1])
                    except:
                        pass
    
    status = "✅ PASSED" if result.returncode == 0 else "❌ FAILED"
    print(f"\n{status}: {passed} passed, {failed} failed, {errors} errors, {skipped} skipped")
    
    if result.returncode != 0:
        # Показываем последние строки ошибок
        error_lines = [l for l in output_lines if "FAILED" in l or "ERROR" in l or "Error" in l]
        if error_lines:
            print("\nОшибки:")
            for line in error_lines[-5:]:  # Последние 5 ошибок
                print(f"  {line}")
    
    return {
        "file": test_file,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "success": result.returncode == 0
    }

def main():
    test_files = find_test_files()
    print(f"Найдено {len(test_files)} тестовых файлов")
    
    results = []
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0
    
    for test_file in test_files:
        result = run_test_file(test_file)
        results.append(result)
        total_passed += result["passed"]
        total_failed += result["failed"]
        total_errors += result["errors"]
        total_skipped += result["skipped"]
    
    # Итоговая статистика
    print(f"\n{'='*80}")
    print("ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'='*80}")
    print(f"Всего файлов: {len(test_files)}")
    print(f"Успешно: {sum(1 for r in results if r['success'])}")
    print(f"С ошибками: {sum(1 for r in results if not r['success'])}")
    print(f"\nВсего тестов:")
    print(f"  ✅ Passed: {total_passed}")
    print(f"  ❌ Failed: {total_failed}")
    print(f"  ⚠️  Errors: {total_errors}")
    print(f"  ⏭️  Skipped: {total_skipped}")
    
    # Список упавших файлов
    failed_files = [r for r in results if not r["success"]]
    if failed_files:
        print(f"\n❌ Файлы с ошибками ({len(failed_files)}):")
        for r in failed_files:
            print(f"  - {r['file']}: {r['failed']} failed, {r['errors']} errors")
    
    return 0 if total_failed == 0 and total_errors == 0 else 1

if __name__ == "__main__":
    sys.exit(main())




