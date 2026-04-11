#!/usr/bin/env python3
"""
Перемещает docs/scenarios/** в docs/scenarios/ru/** и копирует в docs/scenarios/en/**.
Нужно для i18n структуры Fumadocs с parser: 'dir'.
"""

import shutil
from pathlib import Path


def get_project_root() -> Path:
    """Возвращает корень репозитория (где лежит pyproject.toml)."""
    here = Path(__file__).resolve().parent
    for parent in here.parents:
        if (parent / 'pyproject.toml').exists():
            return parent
    raise RuntimeError('pyproject.toml не найден')


def main() -> None:
    root = get_project_root()
    scenarios_dir = root / 'docs' / 'scenarios'
    ru_dir = scenarios_dir / 'ru'
    en_dir = scenarios_dir / 'en'

    if not scenarios_dir.exists():
        raise FileNotFoundError(f'Папка {scenarios_dir} не найдена')

    # Перемещаем всё из scenarios/ в scenarios/ru/
    print(f'Перемещение {scenarios_dir} → {ru_dir}')
    ru_dir.mkdir(parents=True, exist_ok=True)
    
    for item in scenarios_dir.iterdir():
        if item.name in ('ru', 'en'):
            continue
        dest = ru_dir / item.name
        if item.is_dir():
            shutil.move(str(item), str(dest))
        else:
            shutil.move(str(item), str(dest))

    # Копируем ru/ → en/
    print(f'Копирование {ru_dir} → {en_dir}')
    if en_dir.exists():
        shutil.rmtree(en_dir)
    shutil.copytree(ru_dir, en_dir)

    print('Готово! Структура:')
    print(f'  {ru_dir}/ — оригинальные сценарии (RU)')
    print(f'  {en_dir}/ — копия для перевода (EN)')


if __name__ == '__main__':
    main()
