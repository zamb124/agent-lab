"""
Центральный менеджер переводов для всего приложения.
Поддерживает автоматическую генерацию ключей из кода и файлов.
"""

import json
import re
import ast
import logging
import threading
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
import asyncio
from core.models.i18n_models import (
    Language, TranslationKey, TranslationFile, TranslationStats, I18nConfig
)
from core.context import get_context

logger = logging.getLogger(__name__)


class TranslationManager:
    """
    Центральный менеджер переводов.
    Управляет загрузкой, генерацией и предоставлением переводов.
    """
    
    _instance: Optional['TranslationManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.config = I18nConfig()
        self.translations_dir = Path(self.config.translations_directory)
        
        # Кеш переводов: {language: {key: value}}
        self._translations_cache: Dict[Language, Dict[str, str]] = {}
        
        # Найденные ключи: {key: TranslationKey}  
        self._discovered_keys: Dict[str, TranslationKey] = {}
        
        self._initialized = True
        
        # Пытаемся загрузить существующие переводы при создании экземпляра
        
        loop = None
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                def load_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        new_loop.run_until_complete(self._load_existing_translations())
                    finally:
                        new_loop.close()
                
                thread = threading.Thread(target=load_in_thread)
                thread.start()
                thread.join()
            else:
                # Если цикл не запущен, запускаем синхронно
                loop.run_until_complete(self._load_existing_translations())
        except RuntimeError:
            # Если нет цикла событий, создаем новый
            asyncio.run(self._load_existing_translations())

    
    async def _load_existing_translations(self):
        """Загружает существующие переводы при создании экземпляра"""
        try:
            await self._ensure_directories()
            await self._load_translations()
            logger.debug(f"Загружено переводов: {sum(len(t) for t in self._translations_cache.values())} ключей")
        except Exception as e:
            logger.debug(f"Ошибка загрузки переводов: {e}")
    
    async def initialize(self):
        """Инициализация менеджера переводов"""
        try:
            logger.info("🌐 Инициализация системы переводов...")
            
            # Создаем директории если их нет
            await self._ensure_directories()
            
            # Загружаем существующие переводы
            await self._load_translations()
            
            # Если включена автогенерация - сканируем код
            if self.config.auto_generate_on_startup:
                await self._auto_generate_translations()
            
            logger.info(f"✅ Система переводов инициализирована. Поддерживаемые языки: {[lang.value for lang in Language]}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации системы переводов: {e}")
            raise
    
    async def _ensure_directories(self):
        """Создает необходимые директории"""
        directories = [
            self.translations_dir / "translations",
            self.translations_dir / "keys", 
            self.translations_dir / "generated"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    async def _load_translations(self):
        """Загружает переводы из модульных файлов в кеш"""
        translations_path = self.translations_dir / "translations"
        
        for language in Language:
            lang_dir = translations_path / language.value
            
            # Проверяем модульную структуру
            if lang_dir.exists() and lang_dir.is_dir():
                try:
                    translations = await self._load_modular_translations(lang_dir)
                    self._translations_cache[language] = translations
                    logger.debug(f"Загружено {len(translations)} переводов для языка {language.value} (модульная структура)")
                except Exception as e:
                    logger.error(f"Ошибка загрузки модульных переводов для {language.value}: {e}")
                    self._translations_cache[language] = {}
            else:
                # Fallback на старую монолитную структуру
                old_file_path = translations_path / f"{language.value}.json"
                if old_file_path.exists():
                    try:
                        with open(old_file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        translations = {}
                        self._extract_nested_translations(data, translations, prefix="")
                        translations = {k: v for k, v in translations.items() if not k.startswith("meta.")}
                        
                        self._translations_cache[language] = translations
                        logger.debug(f"Загружено {len(translations)} переводов для языка {language.value} (монолитная структура)")
                    except Exception as e:
                        logger.error(f"Ошибка загрузки переводов для {language.value}: {e}")
                        self._translations_cache[language] = {}
                else:
                    logger.warning(f"Переводы для {language.value} не найдены")
                    self._translations_cache[language] = {}
    
    async def _load_modular_translations(self, lang_dir: Path) -> Dict[str, str]:
        """Загружает переводы из модульной структуры"""
        translations = {}
        
        # Загружаем модули верхнего уровня (*.json файлы в корне директории языка)
        for json_file in lang_dir.glob("*.json"):
            # Пропускаем служебные файлы
            if json_file.name.startswith("_"):
                continue
            
            module_name = json_file.stem
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    module_data = json.load(f)
                
                # Добавляем переводы с префиксом модуля
                self._extract_nested_translations(module_data, translations, prefix=module_name)
            except Exception as e:
                logger.warning(f"Ошибка загрузки модуля {json_file}: {e}")
        
        # Загружаем models/* (поддиректория)
        models_dir = lang_dir / "models"
        if models_dir.exists() and models_dir.is_dir():
            for json_file in models_dir.glob("*.json"):
                if json_file.name.startswith("_"):
                    continue
                
                model_name = json_file.stem
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        model_data = json.load(f)
                    
                    # Добавляем переводы с префиксом models.model_name
                    self._extract_nested_translations(model_data, translations, prefix=f"models.{model_name}")
                except Exception as e:
                    logger.warning(f"Ошибка загрузки модели {json_file}: {e}")
        
        return translations
    
    def _extract_nested_translations(self, data: dict, result: dict, prefix: str = ""):
        """Рекурсивно извлекает переводы из вложенной структуры"""
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                self._extract_nested_translations(value, result, full_key)
            else:
                result[full_key] = str(value)
    
    async def _auto_generate_translations(self):
        """Автоматическая генерация переводов из кода"""
        logger.info("Сканирование кода для автогенерации переводов...")
        
        # Сканируем различные источники
        await self._scan_pydantic_models()
        await self._scan_html_templates()
        await self._scan_javascript_files()
        
        # Обновляем файлы переводов
        await self._update_translation_files()
        
        # Генерируем JS модули для фронтенда
        await self._generate_js_modules()
        
        logger.info(f"✅ Автогенерация завершена. Найдено {len(self._discovered_keys)} ключей")
    
    async def _scan_pydantic_models(self):
        """Сканирует Pydantic модели для извлечения ключей переводов"""
        logger.debug("Сканирование Pydantic моделей...")
        
        # Сканируем директории с моделями
        model_dirs = [Path("apps/flows/models"), Path("apps/frontend")]
        
        for model_dir in model_dirs:
            if model_dir.exists():
                for py_file in model_dir.rglob("*.py"):
                    if py_file.name.startswith("__"):
                        continue
                    
                    try:
                        await self._scan_python_file(py_file)
                    except Exception as e:
                        logger.warning(f"Ошибка сканирования файла {py_file}: {e}")
    
    async def _scan_python_file(self, file_path: Path):
        """Сканирует Python файл для поиска Field() с title, description и т.д."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Парсим AST
            tree = ast.parse(content)
            
            # Ищем классы-наследники BaseModel
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and self._is_pydantic_model(node):
                    model_name = node.name.lower()
                    
                    # Ищем поля с аннотациями
                    for field_node in node.body:
                        if isinstance(field_node, ast.AnnAssign) and field_node.value:
                            field_name = field_node.target.id if hasattr(field_node.target, 'id') else None
                            
                            if field_name and isinstance(field_node.value, ast.Call):
                                # Извлекаем параметры Field()
                                field_params = self._extract_field_params(field_node.value)
                                
                                # Создаем ключи для title, description, placeholder
                                for param_name, param_value in field_params.items():
                                    if param_name in ['title', 'description', 'placeholder', 'help_text'] and param_value:
                                        key = f"models.{model_name}.fields.{field_name}.{param_name}"
                                        
                                        self._discovered_keys[key] = TranslationKey(
                                            key=key,
                                            context=f"Model {node.name}, field {field_name}, parameter {param_name}",
                                            source_file=str(file_path),
                                            default_value=param_value,
                                            category="models"
                                        )
                                        
        except Exception as e:
            logger.debug(f"Ошибка парсинга {file_path}: {e}")
    
    def _is_pydantic_model(self, node: ast.ClassDef) -> bool:
        """Проверяет, является ли класс наследником BaseModel"""
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in ['BaseModel']:
                return True
            elif isinstance(base, ast.Attribute) and base.attr in ['BaseModel']:
                return True
        return False
    
    def _extract_field_params(self, call_node: ast.Call) -> Dict[str, str]:
        """Извлекает параметры из вызова Field()"""
        params = {}
        
        if isinstance(call_node.func, ast.Name) and call_node.func.id == 'Field':
            # Извлекаем keyword arguments
            for keyword in call_node.keywords:
                if keyword.arg in ['title', 'description', 'placeholder', 'help_text']:
                    if isinstance(keyword.value, ast.Constant):
                        params[keyword.arg] = str(keyword.value.value)
        
        return params
    
    async def _scan_html_templates(self):
        """Сканирует HTML шаблоны для поиска вызовов t() и других функций перевода"""
        logger.debug("Сканирование HTML шаблонов...")
        
        template_dirs = [
            Path("apps/frontend/shared/templates"),
            Path("apps/frontend/modules")
        ]
        
        for template_dir in template_dirs:
            if template_dir.exists():
                for html_file in template_dir.rglob("*.html"):
                    try:
                        await self._scan_html_file(html_file)
                    except Exception as e:
                        logger.warning(f"Ошибка сканирования шаблона {html_file}: {e}")
    
    async def _scan_html_file(self, file_path: Path):
        """Сканирует HTML файл для поиска вызовов функций перевода"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ищем вызовы t('key') и t("key") - только как вызов функции
            t_pattern = r'\bt\([\'"]([^\'"]+)[\'"]\)'
            matches = re.findall(t_pattern, content)
            
            for match in matches:
                key = match.strip()
                if key and key not in self._discovered_keys:
                    self._discovered_keys[key] = TranslationKey(
                        key=key,
                        context="HTML template function call",
                        source_file=str(file_path),
                        default_value="",  # Пустое значение по умолчанию, чтобы не заменять существующие переводы
                        category="templates"
                    )
                    
        except Exception as e:
            logger.debug(f"Ошибка сканирования HTML {file_path}: {e}")
    
    async def _scan_javascript_files(self):
        """Сканирует JavaScript файлы для поиска вызовов app.i18n.t()"""
        logger.debug("Сканирование JavaScript файлов...")
        
        js_dirs = [Path("apps/frontend/shared/static")]
        
        for js_dir in js_dirs:
            if js_dir.exists():
                for js_file in js_dir.rglob("*.js"):
                    try:
                        await self._scan_js_file(js_file)
                    except Exception as e:
                        logger.warning(f"Ошибка сканирования JS файла {js_file}: {e}")
    
    async def _scan_js_file(self, file_path: Path):
        """Сканирует JS файл для поиска вызовов функций перевода"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ищем различные паттерны вызовов
            patterns = [
                r'app\.i18n\.t\([\'"]([^\'"]+)[\'"]\)',  # app.i18n.t('key')
                r'\.t\([\'"]([^\'"]+)[\'"]\)',            # .t('key')
                r'i18n\.t\([\'"]([^\'"]+)[\'"]\)'         # i18n.t('key')
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content)
                
                for match in matches:
                    key = match.strip()
                    if key and key not in self._discovered_keys:
                        self._discovered_keys[key] = TranslationKey(
                            key=key,
                            context="JavaScript function call",
                            source_file=str(file_path),
                            default_value=key,
                            category="frontend"
                        )
                        
        except Exception as e:
            logger.debug(f"Ошибка сканирования JS {file_path}: {e}")
    
    async def _update_translation_files(self):
        """Обновляет файлы переводов новыми найденными ключами"""
        if not self._discovered_keys:
            return
        
        logger.info(f"Обновление файлов переводов ({len(self._discovered_keys)} новых ключей)...")
        
        translations_path = self.translations_dir / "translations"
        
        for language in Language:
            lang_dir = translations_path / language.value
            
            # Определяем используется ли модульная структура
            if lang_dir.exists() and lang_dir.is_dir():
                await self._update_modular_translations(lang_dir, language)
            else:
                # Fallback на монолитную структуру
                await self._update_monolithic_translations(translations_path, language)
        
        # Перезагружаем кеш
        await self._load_translations()
    
    async def _update_modular_translations(self, lang_dir: Path, language: Language):
        """Обновляет переводы в модульной структуре"""
        # Группируем ключи по модулям
        modules_data = {}
        
        for key, translation_key in self._discovered_keys.items():
            # Определяем модуль по ключу
            parts = key.split('.')
            if len(parts) < 2 or parts[0] == "":
                module_name = "misc"
                relative_key = key
            elif parts[0] == "models":
                # models.agent.fields.name -> models/agent.json, key: fields.name
                if len(parts) < 2:
                    continue
                module_name = f"models/{parts[1]}"
                relative_key = '.'.join(parts[2:]) if len(parts) > 2 else parts[1]
            else:
                # common.save -> common.json, key: save
                module_name = parts[0]
                relative_key = '.'.join(parts[1:])
            
            if module_name not in modules_data:
                modules_data[module_name] = {}
            
            # Определяем значение
            if language == Language.RU:
                value = translation_key.default_value
            else:
                value = f"[TODO: {key}]"
            
            modules_data[module_name][relative_key] = value
        
        # Обновляем файлы модулей
        for module_path, keys_data in modules_data.items():
            if "/" in module_path:
                # Это models/
                subdir, module_name = module_path.split("/")
                module_dir = lang_dir / subdir
                module_dir.mkdir(exist_ok=True)
                file_path = module_dir / f"{module_name}.json"
            else:
                file_path = lang_dir / f"{module_path}.json"
            
            # Загружаем существующий модуль
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    module_data = json.load(f)
            else:
                module_data = {}
            
            # Добавляем новые ключи
            updated = False
            for relative_key, value in keys_data.items():
                if not self._key_exists_in_data(relative_key, module_data):
                    self._set_nested_key(module_data, relative_key, value)
                    updated = True
            
            if updated:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(module_data, f, ensure_ascii=False, indent=2)
                logger.info(f"  ✅ Обновлен модуль: {file_path.relative_to(lang_dir.parent)}")
    
    async def _update_monolithic_translations(self, translations_path: Path, language: Language):
        """Обновляет переводы в монолитной структуре (для обратной совместимости)"""
        file_path = translations_path / f"{language.value}.json"
        
        # Загружаем существующий файл или создаем новый
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {
                "meta": {
                    "language": language.value,
                    "version": "1.0.0",
                    "last_updated": datetime.now().isoformat(),
                    "completeness": 0,
                    "total_keys": 0,
                    "translated_keys": 0
                }
            }
        
        # Добавляем новые ключи
        updated = False
        for key, translation_key in self._discovered_keys.items():
            if not self._key_exists_in_data(key, data):
                if language == Language.RU:
                    default_value = translation_key.default_value
                else:
                    default_value = f"[TODO: {key}]"
                
                self._set_nested_key(data, key, default_value)
                updated = True
        
        if updated:
            # Обновляем метаданные
            data["meta"]["last_updated"] = datetime.now().isoformat()
            
            # Подсчитываем статистику
            all_translations = {}
            self._extract_nested_translations(data, all_translations)
            all_translations = {k: v for k, v in all_translations.items() if not k.startswith("meta.")}
            
            total_keys = len(all_translations)
            translated_keys = sum(1 for v in all_translations.values() if not str(v).startswith("[TODO:"))
            
            data["meta"]["total_keys"] = total_keys
            data["meta"]["translated_keys"] = translated_keys
            data["meta"]["completeness"] = (translated_keys / total_keys * 100) if total_keys > 0 else 0
            
            # Сохраняем файл
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ Обновлен файл переводов: {language.value}.json ({translated_keys}/{total_keys} переводов)")
    
    def _key_exists_in_data(self, key: str, data: dict) -> bool:
        """Проверяет существование ключа в данных"""
        keys = key.split('.')
        current = data
        
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return False
        
        return True
    
    def _set_nested_key(self, data: dict, key: str, value: str):
        """Устанавливает значение по вложенному ключу"""
        keys = key.split('.')
        current = data
        
        # Проходим по всем частям ключа кроме последней
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        # Устанавливаем значение
        current[keys[-1]] = value
    
    async def _generate_js_modules(self):
        """Генерирует JavaScript модули для фронтенда"""
        logger.debug("Генерация JavaScript модулей...")
        
        # Генерируем только в static директорию для веб-доступа
        frontend_static_path = Path("apps/frontend/shared/static/i18n/generated")
        frontend_static_path.mkdir(parents=True, exist_ok=True)
        
        for language in Language:
            translations = self._translations_cache.get(language, {})
            
            if translations:
                js_content = f"""// Автогенерированный файл переводов для {language.value}
// Не редактируйте вручную - изменения будут перезаписаны

(function() {{
    window.translations = window.translations || {{}};
    window.translations.{language.value} = {json.dumps(translations, ensure_ascii=False, indent=2)};
    console.log('✅ Переводы для {language.value} загружены: ' + Object.keys(window.translations.{language.value}).length + ' ключей');
}})();
"""
                
                # Сохраняем в static директорию
                static_js_file = frontend_static_path / f"{language.value}.js"
                with open(static_js_file, 'w', encoding='utf-8') as f:
                    f.write(js_content)
        
        logger.debug(f"Сгенерированы JS модули для {len(Language)} языков")
    
    def t(self, key: str, language: Language = None, **kwargs) -> str:
        """
        Основная функция перевода
        
        Args:
            key: Ключ перевода
            language: Язык (если не указан, берется из контекста)
            **kwargs: Параметры для подстановки в строку
        
        Returns:
            Переведенная строка
        """
        # Определяем язык
        if language is None:
            context = get_context()
            language = context.language if context else self.config.default_language
        
        # Получаем перевод
        translations = self._translations_cache.get(language, {})
        translation = translations.get(key)
        
        # Fallback на основной язык если перевод не найден
        if translation is None and language != self.config.fallback_language:
            fallback_translations = self._translations_cache.get(self.config.fallback_language, {})
            translation = fallback_translations.get(key)
        
        # Если перевод все еще не найден, возвращаем ключ
        if translation is None:
            translation = key
            logger.warning(f"Перевод не найден для ключа: {key} (язык: {language})")
        
        # Подставляем параметры
        if kwargs:
            try:
                translation = translation.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Ошибка подстановки параметров в перевод '{key}': {e}")
        
        return translation
    
    def get_translations(self, language: Language) -> Dict[str, str]:
        """Возвращает все переводы для указанного языка"""
        return self._translations_cache.get(language, {}).copy()
    
    def get_stats(self) -> TranslationStats:
        """Возвращает статистику переводов"""
        languages_stats = {}
        
        for language in Language:
            translations = self._translations_cache.get(language, {})
            total_keys = len(translations)
            translated_keys = sum(1 for v in translations.values() if not str(v).startswith("[TODO:"))
            
            languages_stats[language] = TranslationFile(
                language=language,
                total_keys=total_keys,
                translated_keys=translated_keys,
                completeness=(translated_keys / total_keys * 100) if total_keys > 0 else 0
            )
        
        return TranslationStats(
            total_languages=len(Language),
            total_keys=len(self._translations_cache.get(Language.RU, {})),
            languages_stats=languages_stats
        )


# Глобальный экземпляр менеджера
_translation_manager: Optional[TranslationManager] = None


def get_translation_manager() -> TranslationManager:
    """Получить глобальный экземпляр менеджера переводов"""
    global _translation_manager
    if _translation_manager is None:
        _translation_manager = TranslationManager()
    return _translation_manager


def t(key: str, language: Language = None, **kwargs) -> str:
    """Глобальная функция перевода"""
    manager = get_translation_manager()
    return manager.t(key, language, **kwargs)
