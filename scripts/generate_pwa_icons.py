"""
Скрипт для генерации PWA иконок
Использует Pillow для создания иконок программно
"""
from pathlib import Path

from PIL import Image, ImageDraw

# Пути
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "core/frontend/static/pwa/icons"

# Размеры иконок для PWA
ICON_SIZES = [72, 96, 128, 144, 152, 180, 192, 384, 512]

# Цвета
BG_COLOR = (26, 26, 46)  # #1a1a2e
LOGO_COLOR = (87, 104, 254)  # #5768FE


def hex_to_rgb(hex_color: str) -> tuple:
    """Конвертирует HEX цвет в RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def draw_logo(draw: ImageDraw.Draw, x: int, y: int, size: int, color: tuple):
    """
    Рисует стилизованный логотип Humanitec (геометрическая H-образная форма)
    Упрощенная версия оригинального SVG
    """
    scale = size / 40  # оригинальный viewBox 40x40
    
    def s(val):
        """Масштабирует координату"""
        return int(val * scale) + x
    
    def sy(val):
        """Масштабирует Y координату"""
        return int(val * scale) + y
    
    # Левая вертикальная часть (снизу)
    draw.rectangle([s(0), sy(34), s(6), sy(40)], fill=color)
    
    # Левая вертикальная часть (сверху)
    draw.rectangle([s(6), sy(0), s(12), sy(14)], fill=color)
    draw.rectangle([s(6), sy(26), s(12), sy(34)], fill=color)
    
    # Правая вертикальная часть (сверху)
    draw.rectangle([s(28), sy(6), s(34), sy(17)], fill=color)
    draw.rectangle([s(34), sy(0), s(40), sy(6)], fill=color)
    
    # Правая вертикальная часть (снизу)
    draw.rectangle([s(28), sy(23), s(34), sy(40)], fill=color)
    
    # Центральный шестиугольник (упрощенный как ромб)
    center_x = s(20)
    center_y = sy(20)
    hex_size = int(8 * scale)
    
    hexagon = [
        (center_x - hex_size, center_y),
        (center_x - hex_size//2, center_y - hex_size),
        (center_x + hex_size//2, center_y - hex_size),
        (center_x + hex_size, center_y),
        (center_x + hex_size//2, center_y + hex_size),
        (center_x - hex_size//2, center_y + hex_size),
    ]
    draw.polygon(hexagon, fill=color)
    
    # Диагональные линии (упрощенные как прямоугольники)
    # Верхняя левая диагональ
    draw.polygon([
        (s(12), sy(14)),
        (s(14), sy(10)),
        (s(17), sy(10)),
        (s(12), sy(17)),
    ], fill=color)
    
    # Верхняя правая диагональ
    draw.polygon([
        (s(23), sy(10)),
        (s(26), sy(10)),
        (s(28), sy(14)),
        (s(28), sy(17)),
    ], fill=color)
    
    # Нижняя левая диагональ
    draw.polygon([
        (s(12), sy(23)),
        (s(17), sy(30)),
        (s(14), sy(30)),
        (s(12), sy(26)),
    ], fill=color)
    
    # Нижняя правая диагональ
    draw.polygon([
        (s(28), sy(23)),
        (s(28), sy(26)),
        (s(26), sy(30)),
        (s(23), sy(30)),
    ], fill=color)


def create_icon(size: int, output_path: Path, logo_color: tuple = LOGO_COLOR, 
                bg_color: tuple = BG_COLOR, logo_scale: float = 0.6,
                transparent_bg: bool = False):
    """Создает иконку с фоном и логотипом"""
    if transparent_bg:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    else:
        img = Image.new('RGBA', (size, size), (*bg_color, 255))
    
    draw = ImageDraw.Draw(img)
    
    logo_size = int(size * logo_scale)
    offset = (size - logo_size) // 2
    
    draw_logo(draw, offset, offset, logo_size, (*logo_color, 255))
    
    img.save(str(output_path), 'PNG')


def generate_icons():
    """Генерация всех PWA иконок"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Обычные иконки
    for size in ICON_SIZES:
        output_path = OUTPUT_DIR / f"icon-{size}x{size}.png"
        create_icon(size, output_path)
        print(f"Created: {output_path.name}")
    
    # Maskable иконки (с большим padding для safe zone)
    for size in [192, 512]:
        output_path = OUTPUT_DIR / f"maskable-{size}x{size}.png"
        create_icon(size, output_path, logo_scale=0.5)
        print(f"Created: {output_path.name}")
    
    # Badge для push notifications (белый логотип на прозрачном фоне)
    output_path = OUTPUT_DIR / "badge-72x72.png"
    create_icon(72, output_path, logo_color=(255, 255, 255), 
                transparent_bg=True, logo_scale=0.7)
    print(f"Created: {output_path.name}")
    
    # Shortcut иконки для сервисов
    shortcuts = {
        "agents": "#10b981",  # зеленый
        "crm": "#f59e0b",     # оранжевый  
        "rag": "#8b5cf6"      # фиолетовый
    }
    
    for name, color in shortcuts.items():
        output_path = OUTPUT_DIR / f"shortcut-{name}.png"
        create_icon(96, output_path, logo_color=hex_to_rgb(color))
        print(f"Created: {output_path.name}")
    
    print(f"\nAll icons generated in: {OUTPUT_DIR}")


if __name__ == "__main__":
    generate_icons()
