#!/usr/bin/env python3
"""
Перестраивает структуру docs/ для i18n с parser: 'dir'.
Было: docs/guides/{locale}/..., docs/scenarios/{locale}/...
Стало: docs/{locale}/guides/..., docs/{locale}/scenarios/...
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
    docs_dir = root / 'docs'

    ru_dir = docs_dir / 'ru'
    en_dir = docs_dir / 'en'

    # Перемещаем guides/ru → ru/guides
    if (docs_dir / 'guides' / 'ru').exists():
        ru_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(docs_dir / 'guides' / 'ru'), str(ru_dir / 'guides'))
        print('Перемещено: guides/ru → ru/guides')

    if (docs_dir / 'guides' / 'en').exists():
        en_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(docs_dir / 'guides' / 'en'), str(en_dir / 'guides'))
        print('Перемещено: guides/en → en/guides')

    # Перемещаем scenarios/ru → ru/scenarios
    if (docs_dir / 'scenarios' / 'ru').exists():
        ru_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(docs_dir / 'scenarios' / 'ru'), str(ru_dir / 'scenarios'))
        print('Перемещено: scenarios/ru → ru/scenarios')

    if (docs_dir / 'scenarios' / 'en').exists():
        en_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(docs_dir / 'scenarios' / 'en'), str(en_dir / 'scenarios'))
        print('Перемещено: scenarios/en → en/scenarios')

    # Копируем index.mdx из guides/ru в ru/, если нет
    ru_index_src = root / 'docs' / 'guides' / 'ru' / 'index.mdx'
    if not (ru_dir / 'index.mdx').exists() and ru_index_src.exists():
        shutil.copy2(ru_index_src, ru_dir / 'index.mdx')
        print('Скопировано: guides/ru/index.mdx → ru/index.mdx')

    en_index_src = root / 'docs' / 'guides' / 'en' / 'index.mdx'
    if not (en_dir / 'index.mdx').exists() and en_index_src.exists():
        shutil.copy2(en_index_src, en_dir / 'index.mdx')
        print('Скопировано: guides/en/index.mdx → en/index.mdx')

    # Удаляем старые пустые папки guides/
    old_guides_dir = docs_dir / 'guides'
    if old_guides_dir.exists() and not any(old_guides_dir.iterdir()):
        old_guides_dir.rmdir()
        print('Удалена пустая папка: guides/')

    print('\nГотово! Новая структура:')
    for item in sorted(ru_dir.glob('**/*.mdx'))[:10]:
        print(f'  ru/{item.relative_to(ru_dir)}')
    if len(list(ru_dir.glob('**/*.mdx'))) > 10:
        print('  ...')
    print()
    for item in sorted(en_dir.glob('**/*.mdx'))[:10]:
        print(f'  en/{item.relative_to(en_dir)}')
    if len(list(en_dir.glob('**/*.mdx'))) > 10:
        print('  ...')


if __name__ == '__main__':
    main()
