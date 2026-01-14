# App Loader Component

Универсальный компонент загрузки с анимированным AI-мозгом для всех UI приложений платформы.

## Использование

### Full-page loader (начальная загрузка страницы)

```html
<!-- В index.html перед <platform-app> -->
<app-loader id="app-loader" fullscreen></app-loader>

<script>
  // Скрыть loader когда приложение загружено
  customElements.whenDefined('platform-app').then(() => {
    const loader = document.getElementById('app-loader');
    if (loader) {
      loader.classList.add('hidden');
      setTimeout(() => loader.remove(), 400);
    }
  });
</script>
```

### Inline компонент (внутри приложения)

```javascript
import { html } from 'lit';

class MyComponent extends PlatformElement {
  render() {
    return html`
      ${this.loading ? html`
        <app-loader size="md" text="Загрузка данных..."></app-loader>
      ` : html`
        <!-- Контент -->
      `}
    `;
  }
}
```

## Свойства

| Свойство | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `size` | String | `'lg'` | Размер loader: `'sm'`, `'md'`, `'lg'`, `'xl'` |
| `text` | String | `'AI Studio'` | Текст под логотипом |
| `fullscreen` | Boolean | `false` | Полноэкранный режим с градиентным фоном |

## Размеры

- `sm` - 60px
- `md` - 90px
- `lg` - 120px (по умолчанию)
- `xl` - 160px

## Примеры

### Полноэкранный с кастомным текстом

```html
<app-loader fullscreen text="Загрузка Humanitec..."></app-loader>
```

### Маленький inline loader

```html
<app-loader size="sm" text="Обработка..."></app-loader>
```

### Большой loader без текста

```html
<app-loader size="xl" text=""></app-loader>
```

## Анимации

Компонент включает несколько анимаций:
- Вращение внешней структуры AI-мозга (8s)
- Пульсация узлов нейронной сети (2s)
- Плавный поток данных между узлами (2s)
- Свечение центрального узла (3s)
- Расширяющиеся волны от центра (3s)

## Стиль

Loader использует цветовую палитру платформы:
- Основной градиент: `#10b981` → `#06b6d4` (emerald → cyan)
- Фон (fullscreen): градиент от `#1a1a2e` до `#0f0f23`
- Эффекты свечения: размытые круги emerald и purple

## CSS классы

- `.hidden` - для плавного скрытия loader с opacity transition

