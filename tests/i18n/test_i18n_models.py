"""
Тесты для моделей интернационализации
"""

import pytest
from datetime import datetime
from app.models.i18n_models import (
    Language, TranslationKey, Translation, TranslationSet, 
    TranslationFile, TranslationStats, I18nConfig
)


class TestLanguage:
    """Тесты для enum Language"""
    
    def test_language_values(self):
        """Проверяем значения поддерживаемых языков"""
        assert Language.RU == "ru"
        assert Language.EN == "en" 
        assert Language.ES == "es"
    
    def test_language_iteration(self):
        """Проверяем итерацию по языкам"""
        languages = list(Language)
        assert len(languages) == 3
        assert Language.RU in languages
        assert Language.EN in languages
        assert Language.ES in languages
    
    def test_language_from_string(self):
        """Проверяем создание Language из строки"""
        assert Language("ru") == Language.RU
        assert Language("en") == Language.EN
        assert Language("es") == Language.ES
        
    def test_invalid_language(self):
        """Проверяем ошибку для неподдерживаемого языка"""
        with pytest.raises(ValueError):
            Language("fr")


class TestTranslationKey:
    """Тесты для модели TranslationKey"""
    
    def test_create_translation_key(self):
        """Проверяем создание ключа перевода"""
        key = TranslationKey(
            key="models.user.fields.name",
            context="User model, field name",
            source_file="app/models/user.py", 
            default_value="Имя пользователя",
            category="models"
        )
        
        assert key.key == "models.user.fields.name"
        assert key.context == "User model, field name"
        assert key.source_file == "app/models/user.py"
        assert key.default_value == "Имя пользователя"
        assert key.category == "models"
    
    def test_translation_key_minimal(self):
        """Проверяем создание ключа с минимальными данными"""
        key = TranslationKey(
            key="test.key",
            default_value="Test Value"
        )
        
        assert key.key == "test.key"
        assert key.default_value == "Test Value"
        assert key.context is None
        assert key.source_file is None
        assert key.category == "common"


class TestTranslation:
    """Тесты для модели Translation"""
    
    def test_create_translation(self):
        """Проверяем создание перевода"""
        translation = Translation(
            language=Language.EN,
            key="models.user.fields.name",
            value="User Name",
            is_auto_generated=False
        )
        
        assert translation.language == Language.EN
        assert translation.key == "models.user.fields.name"
        assert translation.value == "User Name"
        assert translation.is_auto_generated is False
        assert isinstance(translation.last_updated, datetime)
    
    def test_auto_generated_translation(self):
        """Проверяем автогенерированный перевод"""
        translation = Translation(
            language=Language.RU,
            key="common.save",
            value="Сохранить"
        )
        
        # По умолчанию is_auto_generated=True
        assert translation.is_auto_generated is True


class TestTranslationSet:
    """Тесты для модели TranslationSet"""
    
    def test_create_translation_set(self):
        """Проверяем создание набора переводов"""
        translation_set = TranslationSet(
            key="common.save",
            translations={
                Language.RU: "Сохранить",
                Language.EN: "Save",
                Language.ES: "Guardar"
            },
            context="Common save button"
        )
        
        assert translation_set.key == "common.save"
        assert len(translation_set.translations) == 3
        assert translation_set.translations[Language.RU] == "Сохранить"
        assert translation_set.context == "Common save button"
    
    def test_get_translation_existing(self):
        """Проверяем получение существующего перевода"""
        translation_set = TranslationSet(
            key="test.key",
            translations={
                Language.RU: "Тест",
                Language.EN: "Test"
            }
        )
        
        assert translation_set.get_translation(Language.RU) == "Тест"
        assert translation_set.get_translation(Language.EN) == "Test"
    
    def test_get_translation_fallback(self):
        """Проверяем fallback к основному языку"""
        translation_set = TranslationSet(
            key="test.key",
            translations={
                Language.RU: "Тест"
            }
        )
        
        # Для отсутствующего языка должен вернуться fallback
        assert translation_set.get_translation(Language.EN, Language.RU) == "Тест"
    
    def test_get_translation_no_fallback(self):
        """Проверяем возврат ключа при отсутствии переводов"""
        translation_set = TranslationSet(
            key="test.key",
            translations={}
        )
        
        assert translation_set.get_translation(Language.EN) == "test.key"


class TestTranslationFile:
    """Тесты для модели TranslationFile"""
    
    def test_create_translation_file(self):
        """Проверяем создание метаданных файла переводов"""
        file_meta = TranslationFile(
            language=Language.EN,
            total_keys=100,
            translated_keys=75
        )
        
        assert file_meta.language == Language.EN
        assert file_meta.version == "1.0.0"
        assert file_meta.total_keys == 100
        assert file_meta.translated_keys == 75
        assert isinstance(file_meta.last_updated, datetime)
    
    def test_calculate_completeness_with_keys(self):
        """Проверяем расчет процента завершенности"""
        file_meta = TranslationFile(
            language=Language.EN,
            total_keys=100,
            translated_keys=75
        )
        
        completeness = file_meta.calculate_completeness()
        assert completeness == 75.0
    
    def test_calculate_completeness_no_keys(self):
        """Проверяем расчет завершенности при отсутствии ключей"""
        file_meta = TranslationFile(
            language=Language.EN,
            total_keys=0,
            translated_keys=0
        )
        
        completeness = file_meta.calculate_completeness()
        assert completeness == 100.0
    
    def test_calculate_completeness_full(self):
        """Проверяем расчет для полностью переведенного файла"""
        file_meta = TranslationFile(
            language=Language.RU,
            total_keys=50,
            translated_keys=50
        )
        
        completeness = file_meta.calculate_completeness()
        assert completeness == 100.0


class TestTranslationStats:
    """Тесты для модели TranslationStats"""
    
    def test_create_translation_stats(self):
        """Проверяем создание статистики переводов"""
        stats = TranslationStats(
            total_languages=3,
            total_keys=150,
            languages_stats={
                Language.RU: TranslationFile(
                    language=Language.RU,
                    total_keys=150,
                    translated_keys=150
                ),
                Language.EN: TranslationFile(
                    language=Language.EN, 
                    total_keys=150,
                    translated_keys=100
                )
            }
        )
        
        assert stats.total_languages == 3
        assert stats.total_keys == 150
        assert len(stats.languages_stats) == 2
    
    def test_get_overall_completeness(self):
        """Проверяем расчет общей завершенности"""
        stats = TranslationStats(
            total_languages=2,
            total_keys=100,
            languages_stats={
                Language.RU: TranslationFile(
                    language=Language.RU,
                    total_keys=100,
                    translated_keys=100  # 100%
                ),
                Language.EN: TranslationFile(
                    language=Language.EN,
                    total_keys=100, 
                    translated_keys=50   # 50%
                )
            }
        )
        
        overall = stats.get_overall_completeness()
        assert overall == 75.0  # (100 + 50) / 2
    
    def test_get_overall_completeness_empty(self):
        """Проверяем общую завершенность при отсутствии данных"""
        stats = TranslationStats(
            total_languages=0,
            total_keys=0,
            languages_stats={}
        )
        
        overall = stats.get_overall_completeness()
        assert overall == 0.0


class TestI18nConfig:
    """Тесты для модели I18nConfig"""
    
    def test_default_config(self):
        """Проверяем конфигурацию по умолчанию"""
        config = I18nConfig()
        
        assert config.default_language == Language.RU
        assert config.fallback_language == Language.RU
        assert config.auto_generate_missing is True
        assert config.auto_generate_on_startup is True
        assert "app/models" in config.scan_directories
        assert "app/frontend" in config.scan_directories
        assert config.translations_directory == "app/i18n"
    
    def test_custom_config(self):
        """Проверяем кастомную конфигурацию"""
        config = I18nConfig(
            default_language=Language.EN,
            fallback_language=Language.RU,
            auto_generate_missing=False,
            auto_generate_on_startup=False,
            scan_directories=["custom/path"],
            translations_directory="custom/i18n"
        )
        
        assert config.default_language == Language.EN
        assert config.fallback_language == Language.RU
        assert config.auto_generate_missing is False
        assert config.auto_generate_on_startup is False
        assert config.scan_directories == ["custom/path"]
        assert config.translations_directory == "custom/i18n"


class TestModelsSerialization:
    """Тесты сериализации и десериализации моделей"""
    
    def test_translation_key_json(self):
        """Проверяем JSON сериализацию TranslationKey"""
        key = TranslationKey(
            key="test.key",
            default_value="Test Value",
            category="test"
        )
        
        json_data = key.model_dump()
        restored = TranslationKey.model_validate(json_data)
        
        assert restored.key == key.key
        assert restored.default_value == key.default_value
        assert restored.category == key.category
    
    def test_translation_json(self):
        """Проверяем JSON сериализацию Translation"""
        translation = Translation(
            language=Language.EN,
            key="test.key", 
            value="Test Value"
        )
        
        json_data = translation.model_dump()
        restored = Translation.model_validate(json_data)
        
        assert restored.language == translation.language
        assert restored.key == translation.key
        assert restored.value == translation.value
    
    def test_translation_set_json(self):
        """Проверяем JSON сериализацию TranslationSet"""
        translation_set = TranslationSet(
            key="test.key",
            translations={
                Language.RU: "Тест",
                Language.EN: "Test"
            }
        )
        
        json_data = translation_set.model_dump()
        restored = TranslationSet.model_validate(json_data)
        
        assert restored.key == translation_set.key
        assert restored.translations == translation_set.translations
