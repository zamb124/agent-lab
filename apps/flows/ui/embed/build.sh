#!/bin/bash
# Build script для встраиваемого виджета чата

echo "🔨 Building Humanitec Chat Widget..."

# Путь к исходному файлу
SOURCE="apps/flows/ui/embed/chat-widget.js"
# Путь к директории назначения
DEST_DIR="core/frontend/static/embed"
# Путь к выходному файлу
DEST="$DEST_DIR/chat-widget.js"
DEST_MIN="$DEST_DIR/chat-widget.min.js"

# Создаем директорию если не существует
mkdir -p "$DEST_DIR"

# Копируем исходный файл
echo "📦 Copying source file..."
cp "$SOURCE" "$DEST"

# Проверяем наличие esbuild
if ! command -v esbuild &> /dev/null; then
    echo "⚠️  esbuild not found, installing..."
    npm install -g esbuild
fi

# Минификация с помощью esbuild
echo "🗜️  Minifying..."
esbuild "$DEST" \
    --bundle \
    --minify \
    --target=es2020 \
    --format=iife \
    --outfile="$DEST_MIN" \
    --sourcemap \
    --alias:@platform=./core/frontend/static

if [ $? -eq 0 ]; then
    echo "✅ Build complete!"
    echo "📁 Files:"
    ls -lh "$DEST_DIR"
    echo ""
    echo "📊 Size comparison:"
    echo "   Original: $(wc -c < "$DEST") bytes"
    echo "   Minified: $(wc -c < "$DEST_MIN") bytes"
else
    echo "❌ Build failed!"
    exit 1
fi

