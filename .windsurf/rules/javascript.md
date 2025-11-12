---
trigger: manual
description:
globs:
---
# Архитектура JavaScript Frontend

## Принципы

### Модульность
- Все JS файлы используют ES6 modules с `type="module"`
- Все импорты должны быть абсолютными от `/static/js/`
- Экспорт через `export default` или именованный `export`

### DRY (Don't Repeat Yourself)
**ВСЕГДА используй существующие утилиты и компоненты!**
- Не дублируй код
- Перед написанием функции проверь наличие готовой в `utils/` или `components/`
- Если нужна новая утилита - добавляй в соответствующий файл

### Единообразие стиля
- Все модули - ES6 классы
- Используй `async/await` вместо callbacks
- Избегай глобальных переменных (кроме `window.app`)

## Структура директорий

```
app/frontend/shared/static/js/
├── app.js                  # Точка входа, инициализация APP
├── 
├── managers/               # Менеджеры (существующие)
│   ├── theme-manager.js
│   ├── language-manager.js
│   ├── layout-manager.js
│   └── htmx-manager.js
├── 
├── chat/                   # Модуль чата
│   ├── manager.js          # ChatManager
│   ├── voice-recorder.js   # VoiceRecorder
│   └── message-renderer.js # ChatMessageRenderer
├── 
├── utils/                  # 🔧 УТИЛИТЫ (используй их!)
│   ├── cookies.js          # getCookie, setCookie, deleteCookie
│   ├── formatting.js       # formatFileSize, formatDate, formatCurrency
│   ├── markdown.js         # renderMarkdown, sanitizeHTML
│   ├── slugify.js          # slugify, generateUniqueId
│   ├── validation.js       # isValidEmail, isValidUrl, isValidVariableName
│   ├── uuid.js             # generateUUID, generateSessionId
│   ├── files.js            # getFileIcon, detectFileType, fileToBase64
│   └── dom.js              # createElement, show, hide, fadeIn, fadeOut
├── 
├── components/             # 🎨 UI КОМПОНЕНТЫ (используй их!)
│   ├── notification.js     # showNotification, hideNotification
│   ├── modal.js            # showModal, hideModal
│   ├── loader.js           # createLoader, showLoadingOverlay
│   └── file-preview.js     # FilePreviewCard, renderDownloadButton
├── 
└── api/                    # 🌐 API CLIENT (используй его!)
    ├── client.js           # APIClient (базовый HTTP client)
    ├── flows.js            # getFlows, getFlow, createFlow, updateFlow
    ├── agents.js           # getAgents, getAgent, createAgent, updateAgent
    ├── tools.js            # getTools, getTool, createTool, updateTool
    ├── files.js            # uploadFile, getFileInfo
    ├── payments.js         # createPayment, getBillingStats
    └── variables.js        # getVariables, getFlowVariables
```

## Правила использования

### ❌ НЕ ДЕЛАЙ ТАК:

```javascript
// ❌ Дублирование formatFileSize
function formatSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    // ...
}

// ❌ Дублирование notifications
function showNotification(msg) {
    const div = document.createElement('div');
    div.className = 'notification';
    // ...
}

// ❌ Прямой fetch вместо API client
const response = await fetch('/api/v1/flows/');
const flows = await response.json();

// ❌ Дублирование getCookie
function getCookie(name) {
    const value = `; ${document.cookie}`;
    // ...
}

// ❌ Относительные импорты
import { something } from './utils/file.js';
import { other } from '../../../shared/js/utils.js';
```

### ✅ ДЕЛАЙ ТАК:

```javascript
// ✅ Используй готовые утилиты
import { formatFileSize } from '/static/js/utils/formatting.js';

const size = formatFileSize(file.size);

// ✅ Используй компоненты
import { showNotification } from '/static/js/components/notification.js';

showNotification('Операция выполнена', 'success');

// ✅ Используй API client
import { getFlows, createFlow } from '/static/js/api/flows.js';

const flows = await getFlows();
const newFlow = await createFlow(flowData);

// ✅ Используй утилиты cookies
import { getCookie, setCookie } from '/static/js/utils/cookies.js';

const token = getCookie('auth_token');
setCookie('theme', 'dark', 365);

// ✅ Абсолютные импорты от /static/js/
import { slugify } from '/static/js/utils/slugify.js';
import { showModal } from '/static/js/components/modal.js';
```

## Утилиты и функции

### Форматирование (`utils/formatting.js`)
```javascript
formatFileSize(bytes)           // "1.5 MB"
formatDate(date, locale)        // "09.10.2025"
formatDateTime(date, locale)    // "09.10.2025 14:30"
formatCurrency(amount, currency) // "1000.00 ₽"
truncateText(text, maxLength)   // "Текст..."
```

### Работа с файлами (`utils/files.js`)
```javascript
getFileIcon(mimeType)          // 'bi-file-earmark-image'
getFileIconEmoji(filename)     // '📄'
detectFileType(fileName)       // 'image', 'video', 'audio', 'pdf', 'document'
fileToBase64(file)             // Promise<base64String>
validateFileType(file, types)  // boolean
validateFileSize(file, maxSize) // boolean
```

### Валидация (`utils/validation.js`)
```javascript
isValidEmail(email)            // boolean
isValidUrl(url)                // boolean
isValidVariableName(name)      // boolean
validateRequired(value, fieldName) // throws Error
validateMinMax(value, min, max, fieldName) // throws Error
```

### Работа с DOM (`utils/dom.js`)
```javascript
createElement(tag, className, innerHTML)
show(element), hide(element)
fadeIn(element, duration), fadeOut(element, duration)
addClass, removeClass, toggleClass, hasClass
escapeHtml(text), escapeAttr(value)
```

### Cookies (`utils/cookies.js`)
```javascript
getCookie(name)               // string | null
setCookie(name, value, days)  // void
deleteCookie(name)            // void
```

### UUID (`utils/uuid.js`)
```javascript
generateUUID()                // 'uuid-string'
generateSessionId(prefix)     // 'prefix_uuid'
```

### Slugify (`utils/slugify.js`)
```javascript
slugify(text)                 // 'text_slug'
generateUniqueId(baseName)    // 'base_name_abc123'
```

### Markdown (`utils/markdown.js`)
```javascript
renderMarkdown(markdown)      // HTML string
sanitizeHTML(html)            // безопасный HTML
```

## UI Компоненты

### Notifications (`components/notification.js`)
```javascript
import { showNotification } from '/static/js/components/notification.js';

showNotification('Сообщение', 'success');  // 'success', 'error', 'warning', 'info'
showNotification('Ошибка', 'error', 3000); // с кастомной длительностью

hideNotification(id);
clearNotifications();
```

### Modals (`components/modal.js`)
```javascript
import { showModal, hideModal } from '/static/js/components/modal.js';

const modalId = showModal('<p>Контент</p>', {
    title: 'Заголовок',
    size: 'medium',  // 'small', 'medium', 'large', 'xlarge', 'full'
    closeButton: true,
    backdrop: true,
    onClose: () => console.log('Закрыто')
});

hideModal(modalId);
hideAllModals();
```

### Loaders (`components/loader.js`)
```javascript
import { createLoader, showLoadingOverlay } from '/static/js/components/loader.js';

const loader = createLoader('Загрузка...');
container.appendChild(loader);

showLoadingOverlay('Пожалуйста, подождите...');
hideLoadingOverlay();
```

### File Preview (`components/file-preview.js`)
```javascript
import { FilePreviewCard, renderDownloadButton } from '/static/js/components/file-preview.js';

const card = new FilePreviewCard(file);
container.appendChild(card.render());

const button = await renderDownloadButton({ url, fileName, fileId });
```

## API Client

### Базовый клиент (`api/client.js`)
```javascript
import apiClient from '/static/js/api/client.js';

// GET запрос
const data = await apiClient.get('/api/v1/endpoint', { param: 'value' });

// POST запрос
const result = await apiClient.post('/api/v1/endpoint', { data });

// PUT запрос
await apiClient.put('/api/v1/endpoint/id', { data });

// DELETE запрос
await apiClient.delete('/api/v1/endpoint/id');

// Upload файла
const formData = new FormData();
formData.append('file', file);
const result = await apiClient.upload('/api/v1/upload', formData);
```

### Специализированные API

#### Flows (`api/flows.js`)
```javascript
import { getFlows, getFlow, createFlow, updateFlow, deleteFlow } from '/static/js/api/flows.js';

const flows = await getFlows();
const flow = await getFlow(flowId);
const newFlow = await createFlow({ name: 'Test' });
await updateFlow(flowId, { name: 'Updated' });
await deleteFlow(flowId);
```

#### Agents (`api/agents.js`)
```javascript
import { getAgents, getAgent, createAgent, updateAgent } from '/static/js/api/agents.js';

const agents = await getAgents();
const agent = await getAgent(agentId);
```

#### Files (`api/files.js`)
```javascript
import { uploadFile, getFileInfo } from '/static/js/api/files.js';

const result = await uploadFile(file);
// { url: '...', file_id: '...' }

const info = await getFileInfo(fileId);
```

#### Payments (`api/payments.js`)
```javascript
import { createPayment, getBillingStats } from '/static/js/api/payments.js';

const payment = await createPayment(1000, 'yoomoney');
const stats = await getBillingStats();
```

## Создание нового модуля

### 1. Импортируй нужные утилиты и компоненты

```javascript
import { showNotification } from '/static/js/components/notification.js';
import { showModal } from '/static/js/components/modal.js';
import { formatFileSize } from '/static/js/utils/formatting.js';
import { slugify } from '/static/js/utils/slugify.js';
import { getFlows } from '/static/js/api/flows.js';
```

### 2. Создай класс или экспортируй функции

```javascript
class MyModule {
    constructor() {
        this.init();
    }
    
    init() {
        this.bindEvents();
    }
    
    bindEvents() {
        // ...
    }
    
    async loadData() {
        try {
            const data = await getFlows();
            showNotification('Данные загружены', 'success');
        } catch (error) {
            showNotification('Ошибка: ' + error.message, 'error');
        }
    }
}

export default MyModule;
```

### 3. Подключи в HTML с type="module"

```html
<script src="/static/my-module/js/module.js" type="module"></script>
```

## Важные правила

### ВСЕГДА используй общие компоненты:

1. **Notifications**: Только `showNotification()` из `components/notification.js`
2. **Modals**: Только `showModal()` из `components/modal.js`
3. **API запросы**: Только через `api/client.js` или специализированные API
4. **Форматирование**: Только из `utils/formatting.js`
5. **Cookies**: Только из `utils/cookies.js`
6. **Markdown**: Только из `utils/markdown.js`
7. **Файлы**: Только из `utils/files.js`

### НЕ создавай новые функции если есть готовые:

```javascript
// ❌ НЕ ДЕЛАЙ
function formatBytes(bytes) { ... }
function showMessage(msg) { ... }
function makeCookie(name, val) { ... }

// ✅ ИСПОЛЬЗУЙ
import { formatFileSize } from '/static/js/utils/formatting.js';
import { showNotification } from '/static/js/components/notification.js';
import { setCookie } from '/static/js/utils/cookies.js';
```

### Импорты ВСЕГДА абсолютные от /static/js/

```javascript
// ❌ НЕ ДЕЛАЙ (относительные пути)
import { something } from './utils/file.js';
import { other } from '../../../shared/js/utils.js';

// ✅ ДЕЛАЙ (абсолютные от /static/js/)
import { something } from '/static/js/utils/file.js';
import { other } from '/static/js/components/modal.js';
```

### Все скрипты с type="module"

```html
<!-- ❌ НЕ ДЕЛАЙ -->
<script src="/static/js/app.js"></script>

<!-- ✅ ДЕЛАЙ -->
<script src="/static/js/app.js" type="module"></script>
```

## Примеры использования

### Создание формы с валидацией

```javascript
import { validateRequired, isValidEmail } from '/static/js/utils/validation.js';
import { showNotification } from '/static/js/components/notification.js';
import { createAgent } from '/static/js/api/agents.js';

async function handleSubmit() {
    const name = document.getElementById('name').value;
    const email = document.getElementById('email').value;
    
    try {
        validateRequired(name, 'Имя');
        validateRequired(email, 'Email');
        
        if (!isValidEmail(email)) {
            throw new Error('Неверный формат email');
        }
        
        const agent = await createAgent({ name, email });
        showNotification('Агент создан', 'success');
        
    } catch (error) {
        showNotification(error.message, 'error');
    }
}
```

### Работа с файлами

```javascript
import { formatFileSize, detectFileType, fileToBase64 } from '/static/js/utils/files.js';
import { uploadFile } from '/static/js/api/files.js';
import { showNotification } from '/static/js/components/notification.js';

async function handleFileUpload(file) {
    if (file.size > 10 * 1024 * 1024) {
        showNotification('Файл слишком большой (макс 10MB)', 'error');
        return;
    }
    
    const type = detectFileType(file.name);
    console.log(`Загружаем ${type} файл, размер: ${formatFileSize(file.size)}`);
    
    try {
        const result = await uploadFile(file);
        showNotification(`Файл загружен: ${result.url}`, 'success');
    } catch (error) {
        showNotification('Ошибка загрузки: ' + error.message, 'error');
    }
}
```

### Создание модального окна

```javascript
import { showModal } from '/static/js/components/modal.js';
import { createLoader } from '/static/js/components/loader.js';

function openSettingsModal() {
    const content = `
        <div class="settings-form">
            <label>Название:</label>
            <input type="text" id="settings-name" class="form-control">
            <button onclick="saveSettings()" class="btn btn-primary">Сохранить</button>
        </div>
    `;
    
    showModal(content, {
        title: 'Настройки',
        size: 'medium',
        closeButton: true
    });
}
```

## Подключение скриптов в шаблонах

### Base template (общий для всех)
```html
<!-- base.html -->
<script src="/static/js/prompt-editor.js" type="module"></script>
<script src="/static/js/app.js" type="module"></script>
```

### Module template (специфичный для модуля)
```html
<!-- bots.html -->
{% block scripts %}
<script src="/static/bots/js/bots.js" type="module"></script>
{% endblock %}
```

### Внутри модуля
```javascript
// /app/frontend/modules/bots/static/js/bots.js
import { slugify } from '/static/js/utils/slugify.js';
import { showNotification } from '/static/js/components/notification.js';

// Твой код...
```

## Миграция существующего кода

Если видишь дублирование:

1. Проверь есть ли готовая утилита в `utils/` или `components/`
2. Если нет - добавь в соответствующий файл
3. Замени все использования на импорт из общей утилиты
4. Удали дублирующий код

Пример:
```javascript
// Было в 3 файлах:
function formatFileSize(bytes) { ... }

// Стало:
// 1. В utils/formatting.js уже есть
// 2. Везде заменяем на:
import { formatFileSize } from '/static/js/utils/formatting.js';
```

## Чеклист перед коммитом

- [ ] Все импорты абсолютные от `/static/js/`
- [ ] Используются общие утилиты вместо дублирования
- [ ] Используется `showNotification()` вместо кастомных уведомлений
- [ ] Используется `showModal()` вместо кастомных модалок
- [ ] API запросы через `api/` модули, а не прямой fetch
- [ ] Все скрипты подключены с `type="module"`
- [ ] Нет дублирования функций (`formatFileSize`, `getCookie`, `renderMarkdown`, etc)
- [ ] Код следует ES6 стилю (классы, async/await, arrow functions)
# Архитектура JavaScript Frontend

## Принципы

### Модульность
- Все JS файлы используют ES6 modules с `type="module"`
- Все импорты должны быть абсолютными от `/static/js/`
- Экспорт через `export default` или именованный `export`

### DRY (Don't Repeat Yourself)
**ВСЕГДА используй существующие утилиты и компоненты!**
- Не дублируй код
- Перед написанием функции проверь наличие готовой в `utils/` или `components/`
- Если нужна новая утилита - добавляй в соответствующий файл

### Единообразие стиля
- Все модули - ES6 классы
- Используй `async/await` вместо callbacks
- Избегай глобальных переменных (кроме `window.app`)

## Структура директорий

```
app/frontend/shared/static/js/
├── app.js                  # Точка входа, инициализация APP
├── 
├── managers/               # Менеджеры (существующие)
│   ├── theme-manager.js
│   ├── language-manager.js
│   ├── layout-manager.js
│   └── htmx-manager.js
├── 
├── chat/                   # Модуль чата
│   ├── manager.js          # ChatManager
│   ├── voice-recorder.js   # VoiceRecorder
│   └── message-renderer.js # ChatMessageRenderer
├── 
├── utils/                  # 🔧 УТИЛИТЫ (используй их!)
│   ├── cookies.js          # getCookie, setCookie, deleteCookie
│   ├── formatting.js       # formatFileSize, formatDate, formatCurrency
│   ├── markdown.js         # renderMarkdown, sanitizeHTML
│   ├── slugify.js          # slugify, generateUniqueId
│   ├── validation.js       # isValidEmail, isValidUrl, isValidVariableName
│   ├── uuid.js             # generateUUID, generateSessionId
│   ├── files.js            # getFileIcon, detectFileType, fileToBase64
│   └── dom.js              # createElement, show, hide, fadeIn, fadeOut
├── 
├── components/             # 🎨 UI КОМПОНЕНТЫ (используй их!)
│   ├── notification.js     # showNotification, hideNotification
│   ├── modal.js            # showModal, hideModal
│   ├── loader.js           # createLoader, showLoadingOverlay
│   └── file-preview.js     # FilePreviewCard, renderDownloadButton
├── 
└── api/                    # 🌐 API CLIENT (используй его!)
    ├── client.js           # APIClient (базовый HTTP client)
    ├── flows.js            # getFlows, getFlow, createFlow, updateFlow
    ├── agents.js           # getAgents, getAgent, createAgent, updateAgent
    ├── tools.js            # getTools, getTool, createTool, updateTool
    ├── files.js            # uploadFile, getFileInfo
    ├── payments.js         # createPayment, getBillingStats
    └── variables.js        # getVariables, getFlowVariables
```

## Правила использования

### ❌ НЕ ДЕЛАЙ ТАК:

```javascript
// ❌ Дублирование formatFileSize
function formatSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    // ...
}

// ❌ Дублирование notifications
function showNotification(msg) {
    const div = document.createElement('div');
    div.className = 'notification';
    // ...
}

// ❌ Прямой fetch вместо API client
const response = await fetch('/api/v1/flows/');
const flows = await response.json();

// ❌ Дублирование getCookie
function getCookie(name) {
    const value = `; ${document.cookie}`;
    // ...
}

// ❌ Относительные импорты
import { something } from './utils/file.js';
import { other } from '../../../shared/js/utils.js';
```

### ✅ ДЕЛАЙ ТАК:

```javascript
// ✅ Используй готовые утилиты
import { formatFileSize } from '/static/js/utils/formatting.js';

const size = formatFileSize(file.size);

// ✅ Используй компоненты
import { showNotification } from '/static/js/components/notification.js';

showNotification('Операция выполнена', 'success');

// ✅ Используй API client
import { getFlows, createFlow } from '/static/js/api/flows.js';

const flows = await getFlows();
const newFlow = await createFlow(flowData);

// ✅ Используй утилиты cookies
import { getCookie, setCookie } from '/static/js/utils/cookies.js';

const token = getCookie('auth_token');
setCookie('theme', 'dark', 365);

// ✅ Абсолютные импорты от /static/js/
import { slugify } from '/static/js/utils/slugify.js';
import { showModal } from '/static/js/components/modal.js';
```

## Утилиты и функции

### Форматирование (`utils/formatting.js`)
```javascript
formatFileSize(bytes)           // "1.5 MB"
formatDate(date, locale)        // "09.10.2025"
formatDateTime(date, locale)    // "09.10.2025 14:30"
formatCurrency(amount, currency) // "1000.00 ₽"
truncateText(text, maxLength)   // "Текст..."
```

### Работа с файлами (`utils/files.js`)
```javascript
getFileIcon(mimeType)          // 'bi-file-earmark-image'
getFileIconEmoji(filename)     // '📄'
detectFileType(fileName)       // 'image', 'video', 'audio', 'pdf', 'document'
fileToBase64(file)             // Promise<base64String>
validateFileType(file, types)  // boolean
validateFileSize(file, maxSize) // boolean
```

### Валидация (`utils/validation.js`)
```javascript
isValidEmail(email)            // boolean
isValidUrl(url)                // boolean
isValidVariableName(name)      // boolean
validateRequired(value, fieldName) // throws Error
validateMinMax(value, min, max, fieldName) // throws Error
```

### Работа с DOM (`utils/dom.js`)
```javascript
createElement(tag, className, innerHTML)
show(element), hide(element)
fadeIn(element, duration), fadeOut(element, duration)
addClass, removeClass, toggleClass, hasClass
escapeHtml(text), escapeAttr(value)
```

### Cookies (`utils/cookies.js`)
```javascript
getCookie(name)               // string | null
setCookie(name, value, days)  // void
deleteCookie(name)            // void
```

### UUID (`utils/uuid.js`)
```javascript
generateUUID()                // 'uuid-string'
generateSessionId(prefix)     // 'prefix_uuid'
```

### Slugify (`utils/slugify.js`)
```javascript
slugify(text)                 // 'text_slug'
generateUniqueId(baseName)    // 'base_name_abc123'
```

### Markdown (`utils/markdown.js`)
```javascript
renderMarkdown(markdown)      // HTML string
sanitizeHTML(html)            // безопасный HTML
```

## UI Компоненты

### Notifications (`components/notification.js`)
```javascript
import { showNotification } from '/static/js/components/notification.js';

showNotification('Сообщение', 'success');  // 'success', 'error', 'warning', 'info'
showNotification('Ошибка', 'error', 3000); // с кастомной длительностью

hideNotification(id);
clearNotifications();
```

### Modals (`components/modal.js`)
```javascript
import { showModal, hideModal } from '/static/js/components/modal.js';

const modalId = showModal('<p>Контент</p>', {
    title: 'Заголовок',
    size: 'medium',  // 'small', 'medium', 'large', 'xlarge', 'full'
    closeButton: true,
    backdrop: true,
    onClose: () => console.log('Закрыто')
});

hideModal(modalId);
hideAllModals();
```

### Loaders (`components/loader.js`)
```javascript
import { createLoader, showLoadingOverlay } from '/static/js/components/loader.js';

const loader = createLoader('Загрузка...');
container.appendChild(loader);

showLoadingOverlay('Пожалуйста, подождите...');
hideLoadingOverlay();
```

### File Preview (`components/file-preview.js`)
```javascript
import { FilePreviewCard, renderDownloadButton } from '/static/js/components/file-preview.js';

const card = new FilePreviewCard(file);
container.appendChild(card.render());

const button = await renderDownloadButton({ url, fileName, fileId });
```

## API Client

### Базовый клиент (`api/client.js`)
```javascript
import apiClient from '/static/js/api/client.js';

// GET запрос
const data = await apiClient.get('/api/v1/endpoint', { param: 'value' });

// POST запрос
const result = await apiClient.post('/api/v1/endpoint', { data });

// PUT запрос
await apiClient.put('/api/v1/endpoint/id', { data });

// DELETE запрос
await apiClient.delete('/api/v1/endpoint/id');

// Upload файла
const formData = new FormData();
formData.append('file', file);
const result = await apiClient.upload('/api/v1/upload', formData);
```

### Специализированные API

#### Flows (`api/flows.js`)
```javascript
import { getFlows, getFlow, createFlow, updateFlow, deleteFlow } from '/static/js/api/flows.js';

const flows = await getFlows();
const flow = await getFlow(flowId);
const newFlow = await createFlow({ name: 'Test' });
await updateFlow(flowId, { name: 'Updated' });
await deleteFlow(flowId);
```

#### Agents (`api/agents.js`)
```javascript
import { getAgents, getAgent, createAgent, updateAgent } from '/static/js/api/agents.js';

const agents = await getAgents();
const agent = await getAgent(agentId);
```

#### Files (`api/files.js`)
```javascript
import { uploadFile, getFileInfo } from '/static/js/api/files.js';

const result = await uploadFile(file);
// { url: '...', file_id: '...' }

const info = await getFileInfo(fileId);
```

#### Payments (`api/payments.js`)
```javascript
import { createPayment, getBillingStats } from '/static/js/api/payments.js';

const payment = await createPayment(1000, 'yoomoney');
const stats = await getBillingStats();
```

## Создание нового модуля

### 1. Импортируй нужные утилиты и компоненты

```javascript
import { showNotification } from '/static/js/components/notification.js';
import { showModal } from '/static/js/components/modal.js';
import { formatFileSize } from '/static/js/utils/formatting.js';
import { slugify } from '/static/js/utils/slugify.js';
import { getFlows } from '/static/js/api/flows.js';
```

### 2. Создай класс или экспортируй функции

```javascript
class MyModule {
    constructor() {
        this.init();
    }
    
    init() {
        this.bindEvents();
    }
    
    bindEvents() {
        // ...
    }
    
    async loadData() {
        try {
            const data = await getFlows();
            showNotification('Данные загружены', 'success');
        } catch (error) {
            showNotification('Ошибка: ' + error.message, 'error');
        }
    }
}

export default MyModule;
```

### 3. Подключи в HTML с type="module"

```html
<script src="/static/my-module/js/module.js" type="module"></script>
```

## Важные правила

### ВСЕГДА используй общие компоненты:

1. **Notifications**: Только `showNotification()` из `components/notification.js`
2. **Modals**: Только `showModal()` из `components/modal.js`
3. **API запросы**: Только через `api/client.js` или специализированные API
4. **Форматирование**: Только из `utils/formatting.js`
5. **Cookies**: Только из `utils/cookies.js`
6. **Markdown**: Только из `utils/markdown.js`
7. **Файлы**: Только из `utils/files.js`

### НЕ создавай новые функции если есть готовые:

```javascript
// ❌ НЕ ДЕЛАЙ
function formatBytes(bytes) { ... }
function showMessage(msg) { ... }
function makeCookie(name, val) { ... }

// ✅ ИСПОЛЬЗУЙ
import { formatFileSize } from '/static/js/utils/formatting.js';
import { showNotification } from '/static/js/components/notification.js';
import { setCookie } from '/static/js/utils/cookies.js';
```

### Импорты ВСЕГДА абсолютные от /static/js/

```javascript
// ❌ НЕ ДЕЛАЙ (относительные пути)
import { something } from './utils/file.js';
import { other } from '../../../shared/js/utils.js';

// ✅ ДЕЛАЙ (абсолютные от /static/js/)
import { something } from '/static/js/utils/file.js';
import { other } from '/static/js/components/modal.js';
```

### Все скрипты с type="module"

```html
<!-- ❌ НЕ ДЕЛАЙ -->
<script src="/static/js/app.js"></script>

<!-- ✅ ДЕЛАЙ -->
<script src="/static/js/app.js" type="module"></script>
```

## Примеры использования

### Создание формы с валидацией

```javascript
import { validateRequired, isValidEmail } from '/static/js/utils/validation.js';
import { showNotification } from '/static/js/components/notification.js';
import { createAgent } from '/static/js/api/agents.js';

async function handleSubmit() {
    const name = document.getElementById('name').value;
    const email = document.getElementById('email').value;
    
    try {
        validateRequired(name, 'Имя');
        validateRequired(email, 'Email');
        
        if (!isValidEmail(email)) {
            throw new Error('Неверный формат email');
        }
        
        const agent = await createAgent({ name, email });
        showNotification('Агент создан', 'success');
        
    } catch (error) {
        showNotification(error.message, 'error');
    }
}
```

### Работа с файлами

```javascript
import { formatFileSize, detectFileType, fileToBase64 } from '/static/js/utils/files.js';
import { uploadFile } from '/static/js/api/files.js';
import { showNotification } from '/static/js/components/notification.js';

async function handleFileUpload(file) {
    if (file.size > 10 * 1024 * 1024) {
        showNotification('Файл слишком большой (макс 10MB)', 'error');
        return;
    }
    
    const type = detectFileType(file.name);
    console.log(`Загружаем ${type} файл, размер: ${formatFileSize(file.size)}`);
    
    try {
        const result = await uploadFile(file);
        showNotification(`Файл загружен: ${result.url}`, 'success');
    } catch (error) {
        showNotification('Ошибка загрузки: ' + error.message, 'error');
    }
}
```

### Создание модального окна

```javascript
import { showModal } from '/static/js/components/modal.js';
import { createLoader } from '/static/js/components/loader.js';

function openSettingsModal() {
    const content = `
        <div class="settings-form">
            <label>Название:</label>
            <input type="text" id="settings-name" class="form-control">
            <button onclick="saveSettings()" class="btn btn-primary">Сохранить</button>
        </div>
    `;
    
    showModal(content, {
        title: 'Настройки',
        size: 'medium',
        closeButton: true
    });
}
```

## Подключение скриптов в шаблонах

### Base template (общий для всех)
```html
<!-- base.html -->
<script src="/static/js/prompt-editor.js" type="module"></script>
<script src="/static/js/app.js" type="module"></script>
```

### Module template (специфичный для модуля)
```html
<!-- bots.html -->
{% block scripts %}
<script src="/static/bots/js/bots.js" type="module"></script>
{% endblock %}
```

### Внутри модуля
```javascript
// /app/frontend/modules/bots/static/js/bots.js
import { slugify } from '/static/js/utils/slugify.js';
import { showNotification } from '/static/js/components/notification.js';

// Твой код...
```

## Миграция существующего кода

Если видишь дублирование:

1. Проверь есть ли готовая утилита в `utils/` или `components/`
2. Если нет - добавь в соответствующий файл
3. Замени все использования на импорт из общей утилиты
4. Удали дублирующий код

Пример:
```javascript
// Было в 3 файлах:
function formatFileSize(bytes) { ... }

// Стало:
// 1. В utils/formatting.js уже есть
// 2. Везде заменяем на:
import { formatFileSize } from '/static/js/utils/formatting.js';
```

## Чеклист перед коммитом

- [ ] Все импорты абсолютные от `/static/js/`
- [ ] Используются общие утилиты вместо дублирования
- [ ] Используется `showNotification()` вместо кастомных уведомлений
- [ ] Используется `showModal()` вместо кастомных модалок
- [ ] API запросы через `api/` модули, а не прямой fetch
- [ ] Все скрипты подключены с `type="module"`
- [ ] Нет дублирования функций (`formatFileSize`, `getCookie`, `renderMarkdown`, etc)
- [ ] Код следует ES6 стилю (классы, async/await, arrow functions)
