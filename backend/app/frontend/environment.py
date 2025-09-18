"""
Настройка Jinja2 окружения для рендеринга шаблонов
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader


# Определяем путь к шаблонам
current_dir = Path(__file__).parent
templates_dir = current_dir / "templates"

# Создаем директории шаблонов если их нет
templates_dir.mkdir(exist_ok=True)
fields_dir = templates_dir / "fields"
fields_dir.mkdir(exist_ok=True)
wrappers_dir = templates_dir / "wrappers"
wrappers_dir.mkdir(exist_ok=True)

# Создаем Jinja2 окружение
jinja_env = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
    auto_reload=True,  # Автоперезагрузка шаблонов
)

# Добавляем глобальные функции в Jinja2
def _add_global_functions():
    """Добавить глобальные функции в Jinja2"""
    try:
        from app.frontend.field_extensions import render_model_safe
        jinja_env.globals['render_model_safe'] = render_model_safe
    except ImportError:
        pass

_add_global_functions()


def render_template(template_name: str, **context) -> str:
    """Рендерить шаблон"""
    try:
        # Пересоздаем окружение каждый раз для отладки
        global jinja_env
        jinja_env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
            auto_reload=True,
        )
        
        # Добавляем глобальные функции каждый раз
        try:
            from app.frontend.field_extensions import render_model_safe
            jinja_env.globals['render_model_safe'] = render_model_safe
        except ImportError:
            pass

        template = jinja_env.get_template(template_name)
        return template.render(**context)
    except Exception as e:
        # Если шаблон не найден, выбрасываем исключение
        raise FileNotFoundError(f"Template not found: {template_name} (Error: {e})")


def template_exists(template_name: str) -> bool:
    """Проверить существование шаблона"""
    try:
        jinja_env.get_template(template_name)
        return True
    except Exception:
        return False
