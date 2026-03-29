/**
 * Сервис для загрузки SVG иконок
 * Иконки находятся в /static/templates/shared/icons/
 */

// Маппинг имен иконок на реальные файлы
// Если иконка есть как файл - используется напрямую, иначе через маппинг
const ICON_MAP = {
    // Прямые соответствия (файл существует с таким именем)
    'send': 'send',
    'close': 'close',
    'edit': 'edit',
    'trash': 'trash',
    'delete': 'trash',
    'copy': 'copy',
    'check': 'check',
    'info': 'info',
    'agent': 'agent',
    'llm_node': 'agent',
    'plus': 'plus',
    'chat': 'chat',
    'file': 'file',
    'folder': 'folder',
    'code': 'code',
    'terminal': 'terminal',
    'play': 'play',
    'stop': 'stop',
    'sun': 'sun',
    'moon': 'moon',
    'theme-auto': 'theme-auto',
    'logout': 'logout',
    'login': 'login',
    'user': 'user',
    'settings': 'settings',
    'refresh': 'refresh',
    'tool': 'tool',
    'workflow': 'workflow',
    'tree-square-dot': 'workflow',
    'breakpoint': 'breakpoint',
    'target': 'target',
    'target-lock': 'target',
    'globe': 'globe',
    'help': 'help',
    'share': 'share',
    'route': 'share',
    'save': 'save',
    'eye': 'eye',
    'box': 'box',
    'chart': 'chart',
    'chart-multifunction': 'chart',
    'cloud': 'cloud',
    'fullscreen': 'fullscreen',
    'clipboard': 'clipboard',
    'chevron-left': 'chevron-left',
    'chevron-right': 'chevron-right',
    'chevron-down': 'arrow-down',
    'expand': 'expand',
    'collapse': 'collapse',
    'minimize': 'minimize',
    'condition': 'condition',
    'ai': 'ai',
    'drag-handle': 'drag-handle',
    'paperclip': 'paperclip',
    'database': 'database',
    'avatar': 'avatar',
    'adjustment': 'adjustment',
    'brightness': 'brightness',
    'building-one': 'building-one',
    'calendar': 'calendar',
    'calendar-solid': 'calendar-solid',
    'checklist': 'checklist',
    'book-open': 'book-open',
    'doc-detail': 'doc-detail',
    'circular-connection': 'circular-connection',
    'network': 'database-network',
    'sparkle': 'sparkle',
    'link': 'circular-connection',
    'filter': 'filter',
    'list': 'list',
    'access-request': 'access-request',
    'mcp': 'mcp',
    'server': 'server',
    'key': 'key',
    'python': 'python',
    'javascript': 'javascript',
    'js': 'javascript',
    
    // Алиасы
    'menu': 'hamburger',
    'hamburger': 'hamburger',
    'attach': 'paperclip',
    'bot': 'ai',
    'minus': 'collapse',
    'maximize': 'fullscreen',
    'search': 'eye',
    'arrow-left': 'chevron-left',
    'arrow-right': 'chevron-right',
    'arrow-up': 'expand',
    'arrow-down': 'collapse',
    'chevron-down': 'collapse',
    'chevron-up': 'expand',
    'lock': 'condition',
    'unlock': 'condition',
    'drag': 'drag-handle',
    'warning': 'notification-warning',
    'error': 'notification-error',
    'success': 'notification-success',
    'cursor': 'target',
    'undo': 'undo',
    'redo': 'redo',
    'external-link': 'share',
    'x': 'close',
    'plug': 'mcp',
    'notification-warning': 'notification-warning',
    'notification-error': 'notification-error',
    'notification-success': 'notification-success',
    'notification-info': 'notification-info',
    'bell': 'bell-ring',
    'bell-ring': 'bell-ring',
    'more': 'adjustment',
    'dots': 'adjustment',
    'variable': 'code',
    'package': 'box',
    'clock': 'calendar',
    'timer': 'calendar',
    'schedule': 'calendar',
    'mail': 'send',
    'email': 'send',
    'envelope': 'send',
    'message-circle': 'chat',
    'phone': 'server',
};

export class IconService {
    constructor(basePath = '/ui/static/assets/icons') {
        /** @type {Map<string, string>} */
        this.cache = new Map();
        this.basePath = basePath;
    }

    /**
     * Загрузить иконку
     * @param {string} name - имя иконки
     * @returns {Promise<string>} SVG разметка
     */
    async load(name) {
        if (!name) {
            throw new Error('Icon name is required');
        }

        const requestedName = String(name).trim();
        if (!requestedName) {
            throw new Error('Icon name is required');
        }

        if (this.cache.has(requestedName)) {
            return this.cache.get(requestedName);
        }

        const mappedFileName = ICON_MAP[requestedName] || requestedName;
        const primaryUrl = `${this.basePath}/${mappedFileName}.svg`;
        const primaryResponse = await fetch(primaryUrl);

        let response = primaryResponse;
        let resolvedFileName = mappedFileName;
        if (!primaryResponse.ok && mappedFileName !== requestedName) {
            const fallbackUrl = `${this.basePath}/${requestedName}.svg`;
            const fallbackResponse = await fetch(fallbackUrl);
            if (fallbackResponse.ok) {
                response = fallbackResponse;
                resolvedFileName = requestedName;
            }
        }

        if (!response.ok) {
            throw new Error(`Icon not found: ${requestedName} (${primaryUrl}), HTTP ${response.status}`);
        }

        let svg = await response.text();
        if (!svg) {
            throw new Error(`Icon "${requestedName}" loaded but content is empty`);
        }

        svg = this._normalizeSvg(svg);

        this.cache.set(requestedName, svg);
        if (resolvedFileName !== requestedName) {
            this.cache.set(resolvedFileName, svg);
        }
        return svg;
    }

    /**
     * Нормализовать SVG - убрать width/height атрибуты
     */
    _normalizeSvg(svg) {
        return svg
            .replace(/\s+width="[^"]*"/g, '')
            .replace(/\s+height="[^"]*"/g, '');
    }

    /**
     * Предзагрузить набор иконок
     * @param {string[]} names
     */
    async preload(names) {
        if (!Array.isArray(names)) {
            throw new Error('Names must be an array');
        }

        await Promise.all(names.map(name => this.load(name)));
    }

    /**
     * Получить иконку синхронно из кеша
     * @param {string} name
     * @returns {string} SVG разметка
     */
    getFromCache(name) {
        if (!name) {
            throw new Error('Icon name is required');
        }

        if (!this.cache.has(name)) {
            throw new Error(`Icon "${name}" not in cache. Call preload() first.`);
        }

        return this.cache.get(name);
    }

    /**
     * Список доступных иконок
     */
    get availableIcons() {
        return [...new Set([...Object.keys(ICON_MAP), ...Object.values(ICON_MAP)])].sort();
    }
}
