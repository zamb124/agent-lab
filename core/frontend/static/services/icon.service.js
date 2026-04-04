/**
 * Сервис для загрузки SVG иконок.
 * Общие UI-иконки: корень basePath. Типы файлов: basePath/files_icons/ (см. loadFileIcon).
 */

/**
 * Имена файлов в `files_icons/` без `.svg` (как на диске, в т.ч. с пробелами).
 * @type {readonly string[]}
 */
export const FILE_ICON_BASE_NAMES = Object.freeze([
    '001-adobe illustrator',
    '002-apk',
    '003-css',
    '004-disc',
    '005-doc',
    '006-excel',
    '007-font file',
    '008-iso',
    '009-javascript',
    '010-image',
    '011-js file',
    '012-mail',
    '013-mp3',
    '014-video',
    '015-music',
    '016-pdf',
    '017-php',
    '018-powerpoint',
    '019-ppt',
    '020-psd',
    '021-record',
    '022-sql',
    '023-svg',
    '024-text',
    '025-ttf',
    '026-txt',
    '027-mail',
    '028-vector',
    '029-video',
    '030-word',
    '031-xls',
    '032-zip',
]);

/** @type {ReadonlySet<string>} */
const FILE_ICON_BASENAME_SET = new Set(FILE_ICON_BASE_NAMES);

/**
 * Логические имена (UI, расширения, document_type office) -> базовое имя файла в files_icons.
 */
const FILE_ICON_ALIASES = {
    illustrator: '001-adobe illustrator',
    'adobe-illustrator': '001-adobe illustrator',
    apk: '002-apk',
    css: '003-css',
    disc: '004-disc',
    doc: '005-doc',
    word: '030-word',
    docx: '030-word',
    odt: '030-word',
    rtf: '024-text',
    excel: '006-excel',
    cell: '006-excel',
    xls: '031-xls',
    xlsx: '006-excel',
    ods: '006-excel',
    csv: '006-excel',
    'font-file': '007-font file',
    iso: '008-iso',
    javascript: '009-javascript',
    js: '011-js file',
    image: '010-image',
    mail: '012-mail',
    email: '012-mail',
    mp3: '013-mp3',
    music: '015-music',
    pdf: '016-pdf',
    php: '017-php',
    powerpoint: '018-powerpoint',
    slide: '018-powerpoint',
    ppt: '019-ppt',
    pptx: '018-powerpoint',
    odp: '018-powerpoint',
    psd: '020-psd',
    record: '021-record',
    sql: '022-sql',
    svg: '023-svg',
    text: '024-text',
    txt: '026-txt',
    ttf: '025-ttf',
    vector: '028-vector',
    video: '029-video',
    zip: '032-zip',

    png: '010-image',
    jpg: '010-image',
    jpeg: '010-image',
    gif: '010-image',
    webp: '010-image',
    bmp: '010-image',
    ico: '010-image',
    heic: '010-image',
    heif: '010-image',
    tif: '010-image',
    tiff: '010-image',

    wav: '015-music',
    flac: '015-music',
    aac: '015-music',
    m4a: '015-music',
    ogg: '015-music',
    opus: '015-music',
    wma: '015-music',

    mkv: '029-video',
    mov: '029-video',
    avi: '029-video',
    wmv: '029-video',
    m4v: '029-video',
    '3gp': '029-video',

    '7z': '032-zip',
    rar: '032-zip',
    tar: '032-zip',
    gz: '032-zip',
    bz2: '032-zip',
    xz: '032-zip',

    md: '024-text',
    markdown: '024-text',
    log: '024-text',
    ini: '024-text',
    cfg: '024-text',
    conf: '024-text',
    config: '024-text',
    env: '024-text',
    json: '024-text',
    yaml: '024-text',
    yml: '024-text',
    toml: '024-text',
    xml: '024-text',
    html: '024-text',
    htm: '024-text',
    vue: '024-text',
    svelte: '024-text',
    py: '024-text',
    rb: '024-text',
    go: '024-text',
    rs: '024-text',
    java: '024-text',
    kt: '024-text',
    swift: '024-text',
    cpp: '024-text',
    cxx: '024-text',
    cc: '024-text',
    c: '024-text',
    h: '024-text',
    cs: '024-text',
    sh: '024-text',
    bash: '024-text',
    zsh: '024-text',
    ps1: '024-text',
    dockerfile: '024-text',
    lock: '024-text',
    wasm: '024-text',
    eml: '012-mail',
    msg: '012-mail',
};

/**
 * Точные MIME -> логический ключ для loadFileIcon (ключ из FILE_ICON_ALIASES).
 * @type {Readonly<Record<string, string>>}
 */
const FILE_MIME_TO_ICON_KEY = Object.freeze({
    'application/pdf': 'pdf',
    'application/msword': 'word',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'word',
    'application/vnd.oasis.opendocument.text': 'word',
    'application/rtf': 'text',
    'text/rtf': 'text',
    'application/vnd.ms-excel': 'xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'application/vnd.oasis.opendocument.spreadsheet': 'excel',
    'text/csv': 'csv',
    'application/vnd.ms-powerpoint': 'ppt',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
    'application/vnd.oasis.opendocument.presentation': 'slide',
    'application/zip': 'zip',
    'application/x-zip-compressed': 'zip',
    'application/x-rar-compressed': 'zip',
    'application/x-7z-compressed': 'zip',
    'application/gzip': 'zip',
    'application/x-tar': 'zip',
    'application/javascript': 'js',
    'text/javascript': 'js',
    'application/json': 'text',
    'application/xml': 'text',
    'text/xml': 'text',
    'text/html': 'text',
    'text/css': 'css',
    'text/markdown': 'text',
    'text/x-markdown': 'text',
    'text/plain': 'txt',
    'application/sql': 'sql',
    'application/x-sql': 'sql',
    'image/svg+xml': 'svg',
    'application/postscript': 'vector',
    'image/vnd.adobe.photoshop': 'psd',
    'application/x-php': 'php',
    'application/x-httpd-php': 'php',
    'text/php': 'php',
});

/** @type {ReadonlySet<string>} */
const FILE_ICON_ALIAS_KEYS = new Set(Object.keys(FILE_ICON_ALIASES));

/**
 * Логический ключ для loadFileIcon по имени файла и MIME (оба аргумента — строки).
 * @param {string} [filename='']
 * @param {string} [mimeType='']
 * @returns {string}
 */
export function resolveFileIconKey(filename = '', mimeType = '') {
    const name = String(filename ?? '').trim();
    const rawMime = String(mimeType ?? '').trim();
    const mime = rawMime ? rawMime.split(';')[0].trim().toLowerCase() : '';

    if (mime) {
        const exact = FILE_MIME_TO_ICON_KEY[mime];
        if (typeof exact === 'string' && FILE_ICON_ALIAS_KEYS.has(exact)) {
            return exact;
        }
        const slash = mime.indexOf('/');
        if (slash > 0) {
            const main = mime.slice(0, slash);
            const sub = mime.slice(slash + 1);
            if (main === 'image') {
                return 'image';
            }
            if (main === 'audio') {
                return sub === 'mpeg' || sub === 'mp3' ? 'mp3' : 'music';
            }
            if (main === 'video') {
                return 'video';
            }
            if (main === 'text') {
                if (sub === 'plain') {
                    return 'txt';
                }
                return 'text';
            }
        }
    }

    const dot = name.lastIndexOf('.');
    const ext = dot > 0 && dot < name.length - 1 ? name.slice(dot + 1).toLowerCase() : '';
    if (ext && FILE_ICON_ALIAS_KEYS.has(ext)) {
        return ext;
    }

    return 'text';
}

// Маппинг имен иконок на реальные файлы
// Если иконка есть как файл - используется напрямую, иначе через маппинг
const ICON_MAP = {
    // Прямые соответствия (файл существует с таким именем)
    send: 'send',
    close: 'close',
    edit: 'edit',
    trash: 'trash',
    delete: 'trash',
    copy: 'copy',
    check: 'check',
    info: 'info',
    agent: 'agent',
    llm_node: 'agent',
    plus: 'plus',
    chat: 'chat',
    folder: 'folder',
    code: 'code',
    terminal: 'terminal',
    play: 'play',
    stop: 'stop',
    sun: 'sun',
    moon: 'moon',
    'theme-auto': 'theme-auto',
    logout: 'logout',
    login: 'login',
    user: 'user',
    users: 'user',
    settings: 'settings',
    refresh: 'refresh',
    tool: 'tool',
    workflow: 'workflow',
    'tree-square-dot': 'workflow',
    breakpoint: 'breakpoint',
    target: 'target',
    'target-lock': 'target',
    globe: 'globe',
    help: 'help',
    share: 'share',
    route: 'share',
    save: 'save',
    eye: 'eye',
    box: 'box',
    chart: 'chart',
    'chart-multifunction': 'chart',
    cloud: 'cloud',
    fullscreen: 'fullscreen',
    clipboard: 'clipboard',
    'chevron-left': 'chevron-left',
    'chevron-right': 'chevron-right',
    'chevron-down': 'collapse',
    expand: 'expand',
    collapse: 'collapse',
    minimize: 'minimize',
    condition: 'condition',
    ai: 'ai',
    'drag-handle': 'drag-handle',
    paperclip: 'paperclip',
    database: 'database',
    avatar: 'avatar',
    adjustment: 'adjustment',
    brightness: 'brightness',
    'building-one': 'building-one',
    calendar: 'calendar',
    'calendar-solid': 'calendar-solid',
    checklist: 'checklist',
    'book-open': 'book-open',
    'doc-detail': 'doc-detail',
    'video-call': 'video-call',
    'phone-ended': 'phone-ended',
    'circular-connection': 'circular-connection',
    network: 'database-network',
    sparkle: 'sparkle',
    link: 'circular-connection',
    filter: 'filter',
    search: 'search',
    list: 'list',
    'access-request': 'access-request',
    mcp: 'mcp',
    server: 'server',
    key: 'key',
    python: 'python',
    javascript: 'javascript',
    js: 'javascript',

    // Алиасы
    menu: 'hamburger',
    hamburger: 'hamburger',
    attach: 'paperclip',
    bot: 'ai',
    minus: 'collapse',
    maximize: 'fullscreen',
    'arrow-left': 'chevron-left',
    'arrow-right': 'chevron-right',
    'arrow-up': 'expand',
    'arrow-down': 'collapse',
    'chevron-up': 'expand',
    lock: 'condition',
    unlock: 'condition',
    drag: 'drag-handle',
    warning: 'notification-warning',
    error: 'notification-error',
    success: 'notification-success',
    cursor: 'target',
    undo: 'undo',
    redo: 'redo',
    'external-link': 'share',
    x: 'close',
    plug: 'mcp',
    'notification-warning': 'notification-warning',
    'notification-error': 'notification-error',
    'notification-success': 'notification-success',
    'notification-info': 'notification-info',
    bell: 'bell-ring',
    'bell-ring': 'bell-ring',
    more: 'adjustment',
    dots: 'adjustment',
    variable: 'code',
    package: 'box',
    clock: 'calendar',
    timer: 'calendar',
    schedule: 'calendar',
    mail: 'send',
    email: 'send',
    envelope: 'send',
    'message-circle': 'chat',
    phone: 'server',
};

export class IconService {
    constructor(basePath = '/ui/static/assets/icons') {
        /** @type {Map<string, string>} */
        this.cache = new Map();
        this.basePath = basePath.replace(/\/$/, '');
        /** Подкаталог цветных иконок типов файлов относительно basePath */
        this.fileIconsDir = 'files_icons';
    }

    /**
     * @param {string} [filename='']
     * @param {string} [mimeType='']
     * @returns {string}
     */
    resolveFileIconKey(filename, mimeType) {
        return resolveFileIconKey(filename, mimeType);
    }

    /**
     * Разрешить логическое имя или basename в каноническое имя файла (как в FILE_ICON_BASE_NAMES).
     * @param {string} name
     * @returns {string}
     */
    _resolveFileIconBasename(name) {
        const raw = String(name).trim();
        if (!raw) {
            throw new Error('File icon name is required');
        }
        const lower = raw.toLowerCase();
        const fromAlias = FILE_ICON_ALIASES[lower];
        if (fromAlias) {
            return fromAlias;
        }
        if (FILE_ICON_BASENAME_SET.has(raw)) {
            return raw;
        }
        for (const b of FILE_ICON_BASENAME_SET) {
            if (b.toLowerCase() === lower) {
                return b;
            }
        }
        throw new Error(`Unknown file icon: ${name}`);
    }

    _fileIconCacheKey(basename) {
        return `__file_icon__:${basename}`;
    }

    _fileIconUrl(basename) {
        const encoded = `${encodeURIComponent(basename)}.svg`;
        return `${this.basePath}/${this.fileIconsDir}/${encoded}`;
    }

    /**
     * Загрузить цветную иконку типа файла из `files_icons/` (отдельно от общих UI-иконок).
     * @param {string} name — алиас (`word`, `pdf`, `cell`) или basename (`030-word`, `016-pdf`)
     * @returns {Promise<string>} SVG разметка
     */
    async loadFileIcon(name) {
        const basename = this._resolveFileIconBasename(name);
        const cacheKey = this._fileIconCacheKey(basename);
        if (this.cache.has(cacheKey)) {
            return this.cache.get(cacheKey);
        }

        const url = this._fileIconUrl(basename);
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`File icon not found: ${name} (${url}), HTTP ${response.status}`);
        }
        let svg = await response.text();
        if (!svg) {
            throw new Error(`File icon "${name}" loaded but content is empty`);
        }
        svg = this._normalizeSvg(svg);
        this.cache.set(cacheKey, svg);
        return svg;
    }

    /**
     * Иконка для `document_type` из BFF office: word | cell | slide.
     * @param {string} documentType
     * @returns {Promise<string>}
     */
    async loadFileIconForOfficeDocumentType(documentType) {
        const t = String(documentType || '').trim().toLowerCase();
        if (t === 'word' || t === 'cell' || t === 'slide') {
            return this.loadFileIcon(t);
        }
        throw new Error(`Unsupported office document_type for file icon: ${documentType}`);
    }

    /**
     * @param {string[]} names — алиасы или basenames
     */
    async preloadFileIcons(names) {
        if (!Array.isArray(names)) {
            throw new Error('Names must be an array');
        }
        await Promise.all(names.map((n) => this.loadFileIcon(n)));
    }

    /**
     * @param {string} name
     * @returns {string}
     */
    getFileIconFromCache(name) {
        const basename = this._resolveFileIconBasename(name);
        const cacheKey = this._fileIconCacheKey(basename);
        if (!this.cache.has(cacheKey)) {
            throw new Error(
                `File icon "${name}" not in cache. Call loadFileIcon() or preloadFileIcons() first.`,
            );
        }
        return this.cache.get(cacheKey);
    }

    /** Логические алиасы и basenames для подсказок в коде */
    get availableFileIcons() {
        const aliases = Object.keys(FILE_ICON_ALIASES);
        const merged = [...new Set([...aliases, ...FILE_ICON_BASE_NAMES])];
        return merged.sort();
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

        await Promise.all(names.map((name) => this.load(name)));
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
