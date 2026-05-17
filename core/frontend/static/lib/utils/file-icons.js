/**
 * Pure utilities для типов файлов: alias-таблицы, MIME-резолверы.
 *
 * Не делает HTTP, не использует bus. Иконки тянет icon.effect через bus.
 */

export const FILE_ICON_BASE_NAMES = Object.freeze([
    '001-adobe illustrator', '002-apk', '003-css', '004-disc', '005-doc',
    '006-excel', '007-font file', '008-iso', '009-javascript', '010-image',
    '011-js file', '012-mail', '013-mp3', '014-video', '015-music',
    '016-pdf', '017-php', '018-powerpoint', '019-ppt', '020-psd',
    '021-record', '022-sql', '023-svg', '024-text', '025-ttf',
    '026-txt', '027-mail', '028-vector', '029-video', '030-word',
    '031-xls', '032-zip',
]);

export const FILE_ICON_BASENAME_SET = new Set(FILE_ICON_BASE_NAMES);

export const FILE_ICON_ALIASES = Object.freeze({
    illustrator: '001-adobe illustrator', 'adobe-illustrator': '001-adobe illustrator',
    apk: '002-apk', css: '003-css', disc: '004-disc', doc: '005-doc',
    word: '030-word', docx: '030-word', odt: '030-word', rtf: '024-text',
    excel: '006-excel', cell: '006-excel', xls: '031-xls', xlsx: '006-excel',
    ods: '006-excel', csv: '006-excel', 'font-file': '007-font file',
    iso: '008-iso', javascript: '009-javascript', js: '011-js file',
    image: '010-image', mail: '012-mail', email: '012-mail',
    mp3: '013-mp3', music: '015-music', pdf: '016-pdf', php: '017-php',
    powerpoint: '018-powerpoint', slide: '018-powerpoint', ppt: '019-ppt',
    pptx: '018-powerpoint', odp: '018-powerpoint', psd: '020-psd',
    record: '021-record', sql: '022-sql', svg: '023-svg', text: '024-text',
    txt: '026-txt', ttf: '025-ttf', vector: '028-vector', video: '029-video', zip: '032-zip',
    png: '010-image', jpg: '010-image', jpeg: '010-image', gif: '010-image', webp: '010-image',
    bmp: '010-image', ico: '010-image', heic: '010-image', heif: '010-image', tif: '010-image', tiff: '010-image',
    wav: '015-music', flac: '015-music', aac: '015-music', m4a: '015-music', ogg: '015-music', opus: '015-music', wma: '015-music',
    mkv: '029-video', mov: '029-video', avi: '029-video', wmv: '029-video', m4v: '029-video', '3gp': '029-video',
    '7z': '032-zip', rar: '032-zip', tar: '032-zip', gz: '032-zip', bz2: '032-zip', xz: '032-zip',
    md: '024-text', markdown: '024-text', log: '024-text', ini: '024-text', cfg: '024-text', conf: '024-text',
    config: '024-text', env: '024-text', json: '024-text', yaml: '024-text', yml: '024-text', toml: '024-text',
    xml: '024-text', html: '024-text', htm: '024-text', vue: '024-text', svelte: '024-text', py: '024-text',
    rb: '024-text', go: '024-text', rs: '024-text', java: '024-text', kt: '024-text', swift: '024-text',
    cpp: '024-text', cxx: '024-text', cc: '024-text', c: '024-text', h: '024-text', cs: '024-text',
    sh: '024-text', bash: '024-text', zsh: '024-text', ps1: '024-text', dockerfile: '024-text',
    lock: '024-text', wasm: '024-text', eml: '012-mail', msg: '012-mail',
});

export const FILE_ICON_ALIAS_KEYS = new Set(Object.keys(FILE_ICON_ALIASES));

const FILE_MIME_TO_ICON_KEY = Object.freeze({
    'application/pdf': 'pdf',
    'application/msword': 'word',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'word',
    'application/vnd.oasis.opendocument.text': 'word',
    'application/rtf': 'text', 'text/rtf': 'text',
    'application/vnd.ms-excel': 'xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'application/vnd.oasis.opendocument.spreadsheet': 'excel',
    'text/csv': 'csv',
    'application/vnd.ms-powerpoint': 'ppt',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
    'application/vnd.oasis.opendocument.presentation': 'slide',
    'application/zip': 'zip', 'application/x-zip-compressed': 'zip',
    'application/x-rar-compressed': 'zip', 'application/x-7z-compressed': 'zip',
    'application/gzip': 'zip', 'application/x-tar': 'zip',
    'application/javascript': 'js', 'text/javascript': 'js',
    'application/json': 'text', 'application/xml': 'text', 'text/xml': 'text',
    'text/html': 'text', 'text/css': 'css',
    'text/markdown': 'text', 'text/x-markdown': 'text', 'text/plain': 'txt',
    'application/sql': 'sql', 'application/x-sql': 'sql',
    'image/svg+xml': 'svg', 'application/postscript': 'vector',
    'image/vnd.adobe.photoshop': 'psd',
    'application/x-php': 'php', 'application/x-httpd-php': 'php', 'text/php': 'php',
});

export function resolveFileIconKey(filename = '', mimeType = '') {
    const name = String(filename ?? '').trim();
    const rawMime = String(mimeType ?? '').trim();
    const mime = rawMime ? rawMime.split(';')[0].trim().toLowerCase() : '';

    if (mime) {
        const exact = FILE_MIME_TO_ICON_KEY[mime];
        if (typeof exact === 'string' && FILE_ICON_ALIAS_KEYS.has(exact)) return exact;
        const slash = mime.indexOf('/');
        if (slash > 0) {
            const main = mime.slice(0, slash);
            const sub = mime.slice(slash + 1);
            if (main === 'image') return 'image';
            if (main === 'audio') return sub === 'mpeg' || sub === 'mp3' ? 'mp3' : 'music';
            if (main === 'video') return 'video';
            if (main === 'text') return sub === 'plain' ? 'txt' : 'text';
        }
    }

    const dot = name.lastIndexOf('.');
    const ext = dot > 0 && dot < name.length - 1 ? name.slice(dot + 1).toLowerCase() : '';
    if (ext && FILE_ICON_ALIAS_KEYS.has(ext)) return ext;

    return 'text';
}

/** UI-иконки: имя -> файл. Используется icon.effect. */
export const UI_ICON_MAP = Object.freeze({
    send: 'send', close: 'close', edit: 'edit', trash: 'trash', delete: 'trash',
    apps: 'apps', 'layout-grid': 'apps',
    copy: 'copy', check: 'check', info: 'info', agent: 'agent', llm_node: 'agent',
    plus: 'plus', chat: 'chat', folder: 'folder', code: 'code', terminal: 'terminal',
    play: 'play', stop: 'stop', 'hourglass-top': 'hourglass-top',
    sun: 'sun', moon: 'moon', 'theme-auto': 'theme-auto',
    logout: 'logout', login: 'login', user: 'user', users: 'users', settings: 'settings',
    refresh: 'refresh', tool: 'tool', workflow: 'workflow', 'tree-square-dot': 'workflow',
    breakpoint: 'breakpoint', target: 'target', 'target-lock': 'target', globe: 'globe',
    help: 'help', share: 'share', route: 'share', save: 'save', eye: 'eye', box: 'box',
    chart: 'chart', 'chart-multifunction': 'chart', cloud: 'cloud', fullscreen: 'fullscreen',
    clipboard: 'clipboard', 'chevron-left': 'chevron-left', 'chevron-right': 'chevron-right',
    'chevron-down': 'collapse', expand: 'expand', collapse: 'collapse', minimize: 'minimize',
    condition: 'condition', ai: 'ai', 'drag-handle': 'drag-handle', paperclip: 'paperclip',
    database: 'database', avatar: 'avatar', adjustment: 'adjustment', brightness: 'brightness',
    'building-one': 'building-one', calendar: 'calendar', 'calendar-solid': 'calendar-solid',
    checklist: 'checklist', 'book-open': 'book-open', 'doc-detail': 'doc-detail',
    'video-call': 'video-call', 'phone-ended': 'phone-ended',
    'circular-connection': 'circular-connection', network: 'database-network',
    sparkle: 'sparkle', link: 'circular-connection', filter: 'filter', search: 'search',
    list: 'list', 'access-request': 'access-request', mcp: 'mcp', server: 'server',
    key: 'key',
    python: 'python',
    javascript: 'javascript',
    js: 'javascript',
    typescript: 'typescript',
    ts: 'typescript',
    go: 'go',
    golang: 'go',
    csharp: 'csharp',
    'c-sharp': 'csharp',
    cs: 'csharp',
    'more-vert': 'more-vert', 'more-vertical': 'more-vert', google: 'google',
    yandex: 'yandex', integration: 'integration', schedule: 'schedule',
    'phone-call': 'phone-call', mail: 'mail',
    menu: 'hamburger', hamburger: 'hamburger', attach: 'paperclip', bot: 'ai',
    minus: 'collapse', maximize: 'fullscreen', 'arrow-left': 'chevron-left',
    'arrow-right': 'chevron-right', 'arrow-up': 'expand', 'arrow-down': 'collapse',
    'chevron-up': 'expand', lock: 'condition', unlock: 'condition', drag: 'drag-handle',
    warning: 'notification-warning', error: 'notification-error', success: 'notification-success',
    cursor: 'target', undo: 'undo', redo: 'redo', 'external-link': 'share', x: 'close',
    plug: 'mcp', 'notification-warning': 'notification-warning',
    'notification-error': 'notification-error', 'notification-success': 'notification-success',
    'notification-info': 'notification-info', bell: 'bell-ring', 'bell-ring': 'bell-ring',
    more: 'more-vert', dots: 'more-vert', variable: 'code', package: 'box',
    clock: 'schedule', timer: 'schedule', email: 'mail', envelope: 'mail',
    'message-circle': 'chat', phone: 'phone-call',
    video: 'video-call', smile: 'smile', emoji: 'smile', emoticon: 'smile',
    mic: 'mic', microphone: 'microphone', 'mic-off': 'mic-off',
    'volume-up': 'volume-up',
    'volume_off': 'volume-off',
    'volume-off': 'volume-off',
    'volume-2': 'volume-up',
    volume: 'volume-up',
    'check-double': 'done-all', 'done-all': 'done-all', checkall: 'done-all',
    'alert-circle': 'alert-triangle', 'alert-triangle': 'alert-triangle',
    file: 'doc-detail', document: 'doc-detail',
    note: 'doc-detail',
    image: 'image', picture: 'image', photo: 'image',
    pause: 'pause', 'phone-plus': 'phone-plus', 'screen-share': 'screen-share',
    pin: 'pin', reply: 'reply', forward: 'forward', download: 'download',
    monitor: 'monitor', square: 'square',
    'message-square': 'chat', message: 'chat', comment: 'chat',
    'phone-off': 'phone-ended', hangup: 'phone-ended',
    'git-branch': 'git-branch', branch: 'git-branch',
    circle: 'circle', dot: 'fiber-manual-record', record: 'fiber-manual-record',
    zap: 'zap', bolt: 'zap', flash: 'zap',
    'trace-json': 'trace-json',
    'trace-tree': 'trace-tree',
    'trace-timeline': 'trace-timeline',
});

const UI_ICON_KEYS = new Set([...Object.keys(UI_ICON_MAP), ...Object.values(UI_ICON_MAP)]);

/** Список доступных UI-иконок для подсказок. */
export function listAvailableUiIcons() {
    return [...UI_ICON_KEYS].sort();
}

/** Список доступных файловых иконок. */
export function listAvailableFileIcons() {
    return [...new Set([...Object.keys(FILE_ICON_ALIASES), ...FILE_ICON_BASE_NAMES])].sort();
}

export function resolveFileIconBasename(name) {
    const raw = String(name).trim();
    if (!raw) throw new Error('File icon name is required');
    const lower = raw.toLowerCase();
    const fromAlias = FILE_ICON_ALIASES[lower];
    if (fromAlias) return fromAlias;
    if (FILE_ICON_BASENAME_SET.has(raw)) return raw;
    for (const b of FILE_ICON_BASENAME_SET) {
        if (b.toLowerCase() === lower) return b;
    }
    throw new Error(`Unknown file icon: ${name}`);
}

export function isUiIconKnown(name) {
    if (typeof name !== 'string' || name.length === 0) return false;
    return Object.prototype.hasOwnProperty.call(UI_ICON_MAP, name)
        || Object.prototype.hasOwnProperty.call(UI_ICON_MAP, name.toLowerCase());
}

export function resolveUiIconFile(name) {
    return UI_ICON_MAP[name] || UI_ICON_MAP[name.toLowerCase()] || name;
}

export function normalizeSvg(svg) {
    return String(svg || '').replace(/\s+width="[^"]*"/g, '').replace(/\s+height="[^"]*"/g, '');
}
