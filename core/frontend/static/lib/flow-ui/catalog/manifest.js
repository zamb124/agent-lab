import { LINNEX_CATALOG_ID } from '../protocol/constants.js';

const BASIC = [
    'Text', 'Image', 'Icon', 'Video', 'AudioPlayer', 'Row', 'Column', 'List', 'Card', 'Tabs',
    'Divider', 'Modal', 'Button', 'TextField', 'CheckBox', 'ChoicePicker', 'Slider', 'DateTimeInput',
];
const PLATFORM = [
    'PageShell', 'Navigation', 'PageLink', 'Section', 'Grid', 'Stack', 'Heading', 'Markdown',
    'CodeBlock', 'Citations', 'Form', 'FieldGroup', 'Select', 'TextArea', 'NumberField', 'DatePicker',
    'Switch', 'FileUpload', 'VoiceInput', 'FileCard', 'FileList', 'DataTable', 'Chart', 'Metric', 'Badge', 'Status',
    'Progress', 'Alert', 'EmptyState', 'Avatar', 'AgentIdentity', 'ArtifactFeed', 'ArtifactCard',
    'JsonInspector', 'TaskControls', 'RunTrace', 'ToolActivity', 'BrowserPreview', 'SuggestedPrompts',
    'ConversationFeed', 'FileCollection', 'SkillActivity', 'ReflectionResult', 'ActionPreview',
    'ActionResult', 'ActivityCard',
];

const CONTAINERS = new Set([
    'Row', 'Column', 'List', 'Card', 'Tabs', 'Modal', 'PageShell', 'Navigation', 'Section',
    'Grid', 'Stack', 'Form', 'FieldGroup', 'ArtifactFeed', 'ConversationFeed',
]);

/** @typedef {{
 *   move: 'grid' | 'none',
 *   resizeInline: 'span' | 'none',
 *   resizeBlock: 'row_span' | 'none',
 *   minColumnSpan: number,
 *   maxColumnSpan: 'full' | number,
 *   minRowSpan: number,
 *   maxRowSpan: number | null,
 *   lockAspect: boolean,
 * }} FlowUILayoutCapabilities */

/** @type {Readonly<FlowUILayoutCapabilities>} */
const LAYOUT_NONE = Object.freeze({
    move: 'none',
    resizeInline: 'none',
    resizeBlock: 'none',
    minColumnSpan: 1,
    maxColumnSpan: 'full',
    minRowSpan: 1,
    maxRowSpan: null,
    lockAspect: false,
});

/** @type {Readonly<FlowUILayoutCapabilities>} */
const LAYOUT_SHELL = Object.freeze({
    move: 'none',
    resizeInline: 'none',
    resizeBlock: 'none',
    minColumnSpan: 1,
    maxColumnSpan: 'full',
    minRowSpan: 1,
    maxRowSpan: null,
    lockAspect: false,
});

/** @type {Readonly<FlowUILayoutCapabilities>} */
const LAYOUT_CONTAINER = Object.freeze({
    move: 'grid',
    resizeInline: 'span',
    resizeBlock: 'row_span',
    minColumnSpan: 1,
    maxColumnSpan: 'full',
    minRowSpan: 1,
    maxRowSpan: null,
    lockAspect: false,
});

/** @type {Readonly<FlowUILayoutCapabilities>} */
const LAYOUT_MEDIA = Object.freeze({
    move: 'grid',
    resizeInline: 'span',
    resizeBlock: 'row_span',
    minColumnSpan: 2,
    maxColumnSpan: 'full',
    minRowSpan: 1,
    maxRowSpan: null,
    lockAspect: false,
});

/** @type {Readonly<FlowUILayoutCapabilities>} */
const LAYOUT_COMPACT = Object.freeze({
    move: 'grid',
    resizeInline: 'span',
    resizeBlock: 'row_span',
    minColumnSpan: 1,
    maxColumnSpan: 6,
    minRowSpan: 1,
    maxRowSpan: 2,
    lockAspect: false,
});

/** Ordinary content/input block: free 2D placement on the parent grid. */
/** @type {Readonly<FlowUILayoutCapabilities>} */
const LAYOUT_BLOCK = Object.freeze({
    move: 'grid',
    resizeInline: 'span',
    resizeBlock: 'row_span',
    minColumnSpan: 1,
    maxColumnSpan: 'full',
    minRowSpan: 1,
    maxRowSpan: null,
    lockAspect: false,
});

/** @type {Readonly<FlowUILayoutCapabilities>} */
const LAYOUT_DIVIDER = Object.freeze({
    move: 'grid',
    resizeInline: 'span',
    resizeBlock: 'none',
    minColumnSpan: 1,
    maxColumnSpan: 'full',
    minRowSpan: 1,
    maxRowSpan: 1,
    lockAspect: false,
});

/** @type {Readonly<Record<string, FlowUILayoutCapabilities>>} */
const LAYOUT_BY_TYPE = Object.freeze({
    PageShell: LAYOUT_SHELL,
    ConversationFeed: LAYOUT_BLOCK,
    ArtifactFeed: LAYOUT_BLOCK,
    Form: LAYOUT_BLOCK,
    Navigation: LAYOUT_SHELL,
    Modal: LAYOUT_SHELL,

    Section: LAYOUT_CONTAINER,
    Grid: LAYOUT_CONTAINER,
    Stack: LAYOUT_CONTAINER,
    FieldGroup: LAYOUT_CONTAINER,
    Card: LAYOUT_CONTAINER,
    Row: LAYOUT_CONTAINER,
    Column: LAYOUT_CONTAINER,
    List: LAYOUT_CONTAINER,
    Tabs: LAYOUT_CONTAINER,

    TextArea: LAYOUT_MEDIA,
    TextField: LAYOUT_MEDIA,
    DataTable: LAYOUT_MEDIA,
    Chart: LAYOUT_MEDIA,
    Image: LAYOUT_MEDIA,
    Video: LAYOUT_MEDIA,
    CodeBlock: LAYOUT_MEDIA,
    JsonInspector: LAYOUT_MEDIA,
    BrowserPreview: LAYOUT_MEDIA,
    FileList: LAYOUT_MEDIA,
    FileCollection: LAYOUT_MEDIA,

    Button: LAYOUT_COMPACT,
    Badge: LAYOUT_COMPACT,
    Icon: LAYOUT_COMPACT,
    Avatar: LAYOUT_COMPACT,
    AgentIdentity: LAYOUT_COMPACT,
    Metric: LAYOUT_COMPACT,
    Status: LAYOUT_COMPACT,
    Progress: LAYOUT_COMPACT,
    Switch: LAYOUT_COMPACT,
    CheckBox: LAYOUT_COMPACT,
    PageLink: LAYOUT_COMPACT,

    Divider: LAYOUT_DIVIDER,

    FileUpload: LAYOUT_BLOCK,
    VoiceInput: LAYOUT_COMPACT,
    SuggestedPrompts: LAYOUT_BLOCK,
    TaskControls: LAYOUT_BLOCK,
    EmptyState: LAYOUT_BLOCK,
    Heading: LAYOUT_BLOCK,
    Text: LAYOUT_BLOCK,
    Markdown: LAYOUT_BLOCK,
    Alert: LAYOUT_BLOCK,
    Citations: LAYOUT_BLOCK,
    Select: LAYOUT_BLOCK,
    NumberField: LAYOUT_BLOCK,
    DatePicker: LAYOUT_BLOCK,
    DateTimeInput: LAYOUT_BLOCK,
    ChoicePicker: LAYOUT_BLOCK,
    Slider: LAYOUT_BLOCK,
    FileCard: LAYOUT_BLOCK,
    ArtifactCard: LAYOUT_BLOCK,
    RunTrace: LAYOUT_BLOCK,
    ToolActivity: LAYOUT_BLOCK,
    SkillActivity: LAYOUT_BLOCK,
    ReflectionResult: LAYOUT_BLOCK,
    ActionPreview: LAYOUT_BLOCK,
    ActionResult: LAYOUT_BLOCK,
    ActivityCard: LAYOUT_BLOCK,
    AudioPlayer: LAYOUT_BLOCK,
});

/**
 * @param {string} type
 * @returns {Readonly<FlowUILayoutCapabilities>}
 */
export function layoutCapabilitiesForType(type) {
    if (typeof type !== 'string' || type.length === 0) {
        throw new Error('flow-ui catalog: type required for layout capabilities');
    }
    const layout = LAYOUT_BY_TYPE[type];
    if (!layout) {
        return LAYOUT_NONE;
    }
    return layout;
}

/**
 * Editor metadata — the single source for the Insert panel, inspector property
 * forms and insert defaults. Palette groups, icons and property schemas never
 * live in editor chrome; they are catalog contract.
 *
 * Schema field kinds map to inspector controls:
 * string | text | number | boolean | enum (options: [{value,label}] | string[] | number[];
 * inspector stringifies option.value for platform-field-enum) | image
 * (preview + platform.file_picker; stores download URL in the property) | file_id
 * (platform.file_picker; stores platform file_id, not a download URL).
 * Field labels are pinned RU/EN pairs because the manifest is standalone
 * flow-ui infrastructure (same contract as flow-ui/utils/text.js).
 */

function field(name, kind, ru, en, extra = {}) {
    return Object.freeze({ name, kind, label: Object.freeze({ ru, en }), ...extra });
}

const TEXT_FIELD = field('text', 'text', 'Текст', 'Text');
const LABEL_FIELD = field('label', 'string', 'Подпись', 'Label');
const PLACEHOLDER_FIELD = field('placeholder', 'string', 'Плейсхолдер', 'Placeholder');
const VARIANT_FIELD = field('variant', 'enum', 'Вариант', 'Variant', {
    options: Object.freeze(['primary', 'secondary']),
});
const FIELD_NAME_FIELD = field(
    'fieldName',
    'string',
    'Имя в @state:ui_values',
    'Name in @state:ui_values',
);
const MARKDOWN_MODE_FIELD = field('markdownMode', 'enum', 'Markdown в content', 'Markdown in content', {
    options: Object.freeze([
        Object.freeze({ value: 'auto', label: Object.freeze({ ru: 'Авто', en: 'Auto' }) }),
        Object.freeze({ value: 'always', label: Object.freeze({ ru: 'Всегда', en: 'Always' }) }),
        Object.freeze({ value: 'exclude', label: Object.freeze({ ru: 'Исключить', en: 'Exclude' }) }),
    ]),
});
const MARKDOWN_LABEL_FIELD = field(
    'markdownLabel',
    'string',
    'Подпись в Markdown',
    'Markdown label',
);
const CONTENT_MODE_FIELD = field('contentMode', 'enum', 'Режим state.content', 'state.content mode', {
    options: Object.freeze([
        Object.freeze({ value: 'auto', label: Object.freeze({ ru: 'Авто', en: 'Auto' }) }),
        Object.freeze({ value: 'values', label: Object.freeze({ ru: 'Только values', en: 'Values only' }) }),
        Object.freeze({ value: 'page', label: Object.freeze({ ru: 'Вся страница', en: 'Whole page' }) }),
        Object.freeze({ value: 'message', label: Object.freeze({ ru: 'Только message', en: 'Message only' }) }),
    ]),
});
const INPUT_CONTRACT_FIELDS = Object.freeze([
    FIELD_NAME_FIELD,
    MARKDOWN_MODE_FIELD,
    MARKDOWN_LABEL_FIELD,
]);
const CONTENT_CONTRACT_FIELDS = Object.freeze([MARKDOWN_MODE_FIELD, MARKDOWN_LABEL_FIELD]);

/** @type {Readonly<Record<string, {
 *   group: string,
 *   icon: string,
 *   schema?: readonly object[],
 *   defaults?: object,
 *   maturity?: 'production' | 'partial' | 'runtime_owned' | 'stub',
 *   palette?: boolean,
 * }>>} */
const EDITOR_BY_TYPE = Object.freeze({
    PageShell: {
        group: 'layout',
        icon: 'monitor',
        schema: [CONTENT_MODE_FIELD],
        palette: false,
    },
    Section: { group: 'layout', icon: 'square', schema: [field('presentation', 'string', 'Представление', 'Presentation')] },
    Grid: { group: 'layout', icon: 'apps', palette: false },
    Stack: { group: 'layout', icon: 'layers', palette: false },
    Row: { group: 'layout', icon: 'swap-horiz', palette: false },
    Column: { group: 'layout', icon: 'list', palette: false },
    Card: { group: 'layout', icon: 'clipboard' },
    Divider: { group: 'layout', icon: 'minus' },
    Navigation: { group: 'layout', icon: 'forward', maturity: 'partial' },
    Modal: {
        group: 'layout',
        icon: 'expand',
        schema: [field('open', 'boolean', 'Открыт', 'Open')],
        defaults: { properties: { open: true } },
        maturity: 'partial',
    },
    Tabs: {
        group: 'layout',
        icon: 'folder',
        maturity: 'partial',
        defaults: {
            properties: {
                tabs: Object.freeze([
                    Object.freeze({ id: 'tab-1', label: 'Tab 1' }),
                    Object.freeze({ id: 'tab-2', label: 'Tab 2' }),
                ]),
                value: 'tab-1',
            },
        },
    },
    List: { group: 'layout', icon: 'list', palette: false },

    Heading: {
        group: 'content',
        icon: 'heading-1',
        schema: [
            TEXT_FIELD,
            field('level', 'enum', 'Уровень', 'Level', { options: Object.freeze([1, 2, 3, 4]) }),
            ...CONTENT_CONTRACT_FIELDS,
        ],
        defaults: { properties: { text: { ru: 'Новый заголовок', en: 'New heading' }, level: 2 } },
    },
    Text: {
        group: 'content',
        icon: 'text',
        schema: [TEXT_FIELD, ...CONTENT_CONTRACT_FIELDS],
        defaults: { properties: { text: { ru: 'Новый текст', en: 'New text' } } },
    },
    Markdown: {
        group: 'content',
        icon: 'text-fields',
        schema: [field('content', 'text', 'Markdown', 'Markdown'), ...CONTENT_CONTRACT_FIELDS],
        defaults: { properties: { content: { ru: 'Markdown', en: 'Markdown' } } },
    },
    CodeBlock: {
        group: 'content',
        icon: 'code',
        schema: [field('code', 'text', 'Код', 'Code'), ...CONTENT_CONTRACT_FIELDS],
        defaults: { properties: { code: { ru: '// код', en: '// code' } } },
    },
    Image: {
        group: 'content',
        icon: 'image',
        schema: [
            field('src', 'image', 'Изображение', 'Image'),
            field('alt', 'string', 'Alt-текст', 'Alt text'),
        ],
        defaults: {
            properties: {
                src: '',
                alt: { ru: 'Изображение', en: 'Image' },
            },
        },
    },
    Video: {
        group: 'content',
        icon: 'videocam-off',
        schema: [field('src', 'string', 'URL видео', 'Video URL')],
        defaults: { properties: { src: 'about:blank' } },
        maturity: 'partial',
    },
    AudioPlayer: {
        group: 'content',
        icon: 'volume-up',
        schema: [field('src', 'string', 'URL аудио', 'Audio URL')],
        defaults: { properties: { src: 'about:blank' } },
        maturity: 'partial',
    },
    Icon: {
        group: 'content',
        icon: 'star',
        schema: [field('name', 'string', 'Имя иконки', 'Icon name')],
        defaults: { properties: { name: 'star' } },
    },
    Badge: {
        group: 'content',
        icon: 'tag',
        schema: [LABEL_FIELD],
        defaults: { properties: { label: { ru: 'Метка', en: 'Badge' } } },
    },
    Alert: {
        group: 'content',
        icon: 'alert-triangle',
        schema: [field('message', 'text', 'Сообщение', 'Message')],
        defaults: { properties: { message: { ru: 'Сообщение', en: 'Alert' } } },
    },
    Metric: {
        group: 'content',
        icon: 'target',
        schema: [LABEL_FIELD, field('value', 'string', 'Значение', 'Value')],
        defaults: { properties: { label: { ru: 'Метрика', en: 'Metric' }, value: '0' } },
    },
    Status: {
        group: 'content',
        icon: 'fiber-manual-record',
        schema: [LABEL_FIELD],
        defaults: { properties: { label: { ru: 'Статус', en: 'Status' } } },
    },
    Progress: {
        group: 'content',
        icon: 'hourglass-top',
        schema: [field('value', 'number', 'Значение', 'Value'), field('max', 'number', 'Максимум', 'Max')],
        defaults: { properties: { value: 40, max: 100 } },
    },
    EmptyState: {
        group: 'content',
        icon: 'inbox',
        schema: [field('message', 'text', 'Сообщение', 'Message')],
        defaults: { properties: { message: { ru: 'Пока пусто', en: 'Nothing here yet' } } },
        maturity: 'runtime_owned',
    },
    Citations: { group: 'content', icon: 'quote', maturity: 'partial' },

    TextField: {
        group: 'input',
        icon: 'text-fields',
        schema: [LABEL_FIELD, PLACEHOLDER_FIELD, ...INPUT_CONTRACT_FIELDS],
        defaults: { properties: { label: { ru: 'Поле', en: 'Field' } }, bindings: { value: '/values/{id}' } },
    },
    TextArea: {
        group: 'input',
        icon: 'text',
        schema: [LABEL_FIELD, PLACEHOLDER_FIELD, field('rows', 'number', 'Строк', 'Rows'), ...INPUT_CONTRACT_FIELDS],
        defaults: { properties: { label: { ru: 'Текст', en: 'Text' } }, bindings: { value: '/values/{id}' } },
    },
    NumberField: {
        group: 'input',
        icon: 'plus',
        schema: [LABEL_FIELD, PLACEHOLDER_FIELD, ...INPUT_CONTRACT_FIELDS],
        defaults: { properties: { label: { ru: 'Число', en: 'Number' } }, bindings: { value: '/values/{id}' } },
    },
    Select: {
        group: 'input',
        icon: 'chevron-down',
        schema: [LABEL_FIELD, ...INPUT_CONTRACT_FIELDS],
        defaults: { properties: { label: { ru: 'Выбор', en: 'Select' }, options: [] }, bindings: { value: '/values/{id}' } },
        maturity: 'partial',
    },
    ChoicePicker: {
        group: 'input',
        icon: 'radio',
        schema: [LABEL_FIELD, ...INPUT_CONTRACT_FIELDS],
        defaults: { bindings: { value: '/values/{id}' } },
        maturity: 'partial',
    },
    CheckBox: {
        group: 'input',
        icon: 'check-square',
        schema: [LABEL_FIELD, ...INPUT_CONTRACT_FIELDS],
        defaults: { properties: { label: { ru: 'Флажок', en: 'Checkbox' } }, bindings: { value: '/values/{id}' } },
    },
    Switch: {
        group: 'input',
        icon: 'adjustment',
        schema: [LABEL_FIELD, ...INPUT_CONTRACT_FIELDS],
        defaults: { bindings: { value: '/values/{id}' } },
    },
    Slider: {
        group: 'input',
        icon: 'adjustment',
        schema: [
            LABEL_FIELD,
            field('min', 'number', 'Мин', 'Min'),
            field('max', 'number', 'Макс', 'Max'),
            ...INPUT_CONTRACT_FIELDS,
        ],
        defaults: { bindings: { value: '/values/{id}' } },
    },
    DateTimeInput: {
        group: 'input',
        icon: 'calendar',
        schema: [LABEL_FIELD, ...INPUT_CONTRACT_FIELDS],
        defaults: { bindings: { value: '/values/{id}' } },
    },
    DatePicker: {
        group: 'input',
        icon: 'calendar-solid',
        schema: [LABEL_FIELD, ...INPUT_CONTRACT_FIELDS],
        defaults: { bindings: { value: '/values/{id}' } },
    },
    FileUpload: {
        group: 'input',
        icon: 'paperclip',
        schema: [
            LABEL_FIELD,
            field('multiple', 'boolean', 'Несколько файлов', 'Multiple files'),
            ...INPUT_CONTRACT_FIELDS,
        ],
        defaults: { properties: { multiple: true }, bindings: { value: '/values/{id}' } },
    },
    VoiceInput: {
        group: 'input',
        icon: 'mic',
        schema: [
            field('mode', 'enum', 'Режим', 'Mode', {
                options: Object.freeze([
                    Object.freeze({ value: 'dictation', label: Object.freeze({ ru: 'Диктовка', en: 'Dictation' }) }),
                    Object.freeze({ value: 'session', label: Object.freeze({ ru: 'Эфир', en: 'Live session' }) }),
                ]),
            }),
            field('presentation', 'string', 'Представление', 'Presentation'),
        ],
        defaults: {
            properties: { mode: 'dictation' },
            bindings: { value: '/values/message' },
        },
    },
    Form: { group: 'input', icon: 'checklist', schema: [field('formId', 'string', 'ID формы', 'Form ID'), field('presentation', 'string', 'Представление', 'Presentation')] },
    FieldGroup: { group: 'input', icon: 'list-check' },

    Button: {
        group: 'action',
        icon: 'play',
        schema: [LABEL_FIELD, VARIANT_FIELD, field('disabled', 'boolean', 'Отключена', 'Disabled')],
        defaults: { properties: { label: { ru: 'Кнопка', en: 'Button' }, variant: 'secondary' } },
    },
    PageLink: {
        group: 'action',
        icon: 'link',
        schema: [LABEL_FIELD, field('pageId', 'string', 'Страница', 'Page')],
        defaults: { properties: { label: { ru: 'Страница', en: 'Page' }, pageId: 'main' } },
    },
    SuggestedPrompts: { group: 'action', icon: 'sparkle', maturity: 'runtime_owned' },
    TaskControls: { group: 'action', icon: 'stop', maturity: 'runtime_owned' },

    DataTable: {
        group: 'data',
        icon: 'table',
        schema: [
            field('file_id', 'file_id', 'file_id таблицы', 'DataTable file_id'),
            field('table_name', 'string', 'Имя таблицы в SQLite', 'SQLite table name'),
        ],
        defaults: {
            properties: {
                file_id: '',
                table_name: '',
                columns: Object.freeze([]),
                rows: Object.freeze([]),
            },
        },
        maturity: 'partial',
    },
    Chart: {
        group: 'data',
        icon: 'chart',
        maturity: 'stub',
        defaults: {
            properties: {
                spec: Object.freeze({
                    kind: 'bar',
                    series: Object.freeze([
                        Object.freeze({ name: 'A', value: 1 }),
                        Object.freeze({ name: 'B', value: 2 }),
                    ]),
                }),
            },
        },
    },
    JsonInspector: {
        group: 'data',
        icon: 'trace-json',
        schema: [LABEL_FIELD],
        defaults: { properties: { label: { ru: 'JSON', en: 'JSON' } } },
        maturity: 'stub',
    },
    FileCard: {
        group: 'data',
        icon: 'file-text',
        defaults: {
            properties: {
                file: Object.freeze({
                    file_id: 'preview-file',
                    original_name: 'preview.txt',
                    content_type: 'text/plain',
                    file_size: 0,
                }),
            },
        },
    },
    FileList: {
        group: 'data',
        icon: 'list',
        defaults: { properties: { files: Object.freeze([]) } },
        maturity: 'partial',
    },
    FileCollection: { group: 'data', icon: 'folder', maturity: 'stub' },
    ArtifactCard: {
        group: 'data',
        icon: 'box',
        defaults: {
            properties: {
                artifact: Object.freeze({
                    artifactId: 'preview-artifact',
                    name: 'Artifact',
                    parts: Object.freeze([]),
                }),
            },
        },
    },

    ArtifactFeed: {
        group: 'platform',
        icon: 'chat',
        schema: [field('presentation', 'string', 'Представление', 'Presentation')],
        maturity: 'runtime_owned',
    },
    ConversationFeed: { group: 'platform', icon: 'chat', maturity: 'runtime_owned' },
    AgentIdentity: {
        group: 'platform',
        icon: 'bot',
        schema: [field('title', 'string', 'Название', 'Title')],
        defaults: { properties: { title: { ru: 'Агент', en: 'Agent' } } },
    },
    Avatar: {
        group: 'platform',
        icon: 'avatar',
        schema: [field('name', 'string', 'Имя', 'Name')],
        defaults: { properties: { name: { ru: 'Аватар', en: 'Avatar' } } },
        maturity: 'partial',
    },
    RunTrace: {
        group: 'platform',
        icon: 'trace-tree',
        defaults: { properties: { spans: Object.freeze([]) } },
        maturity: 'partial',
    },
    ToolActivity: {
        group: 'platform',
        icon: 'tool',
        defaults: { properties: { calls: Object.freeze([]) } },
        maturity: 'partial',
    },
    BrowserPreview: {
        group: 'platform',
        icon: 'globe',
        maturity: 'stub',
        defaults: {
            properties: {
                sessionRef: Object.freeze({ session_id: 'preview-session', page_id: null }),
            },
        },
    },
    SkillActivity: { group: 'platform', icon: 'scroll-text', maturity: 'stub' },
    ReflectionResult: { group: 'platform', icon: 'science', maturity: 'stub' },
    ActionPreview: { group: 'platform', icon: 'eye', maturity: 'stub' },
    ActionResult: { group: 'platform', icon: 'done-all', maturity: 'stub' },
    ActivityCard: { group: 'platform', icon: 'zap', maturity: 'stub' },
});

/**
 * Human names for everything the author can insert.
 *
 * Pinned RU/EN like `schema[]` field labels: the manifest is standalone flow-ui
 * infrastructure, so palette copy lives here and never as a raw type id in chrome.
 */
const EDITOR_LABELS = Object.freeze({
    Card: Object.freeze({ ru: 'Карточка', en: 'Card' }),
    Tabs: Object.freeze({ ru: 'Табы', en: 'Tabs' }),
    Divider: Object.freeze({ ru: 'Разделитель', en: 'Divider' }),
    Modal: Object.freeze({ ru: 'Модальное окно', en: 'Modal' }),
    Navigation: Object.freeze({ ru: 'Навигация', en: 'Navigation' }),
    Section: Object.freeze({ ru: 'Секция', en: 'Section' }),
    Text: Object.freeze({ ru: 'Текст', en: 'Text' }),
    Image: Object.freeze({ ru: 'Картинка', en: 'Image' }),
    Icon: Object.freeze({ ru: 'Иконка', en: 'Icon' }),
    Video: Object.freeze({ ru: 'Видео', en: 'Video' }),
    AudioPlayer: Object.freeze({ ru: 'Аудио', en: 'Audio' }),
    Heading: Object.freeze({ ru: 'Заголовок', en: 'Heading' }),
    Markdown: Object.freeze({ ru: 'Markdown', en: 'Markdown' }),
    CodeBlock: Object.freeze({ ru: 'Блок кода', en: 'Code block' }),
    Citations: Object.freeze({ ru: 'Источники', en: 'Citations' }),
    Metric: Object.freeze({ ru: 'Метрика', en: 'Metric' }),
    Badge: Object.freeze({ ru: 'Бейдж', en: 'Badge' }),
    Status: Object.freeze({ ru: 'Статус', en: 'Status' }),
    Progress: Object.freeze({ ru: 'Прогресс', en: 'Progress' }),
    Alert: Object.freeze({ ru: 'Уведомление', en: 'Alert' }),
    EmptyState: Object.freeze({ ru: 'Пустое состояние', en: 'Empty state' }),
    TextField: Object.freeze({ ru: 'Поле ввода', en: 'Text field' }),
    CheckBox: Object.freeze({ ru: 'Чекбокс', en: 'Checkbox' }),
    ChoicePicker: Object.freeze({ ru: 'Выбор из списка', en: 'Choice picker' }),
    Slider: Object.freeze({ ru: 'Слайдер', en: 'Slider' }),
    DateTimeInput: Object.freeze({ ru: 'Дата и время', en: 'Date and time' }),
    Form: Object.freeze({ ru: 'Форма', en: 'Form' }),
    FieldGroup: Object.freeze({ ru: 'Группа полей', en: 'Field group' }),
    Select: Object.freeze({ ru: 'Выпадающий список', en: 'Select' }),
    TextArea: Object.freeze({ ru: 'Многострочное поле', en: 'Text area' }),
    NumberField: Object.freeze({ ru: 'Число', en: 'Number' }),
    DatePicker: Object.freeze({ ru: 'Дата', en: 'Date' }),
    Switch: Object.freeze({ ru: 'Переключатель', en: 'Switch' }),
    FileUpload: Object.freeze({ ru: 'Загрузка файлов', en: 'File upload' }),
    VoiceInput: Object.freeze({ ru: 'Голосовой ввод', en: 'Voice input' }),
    Button: Object.freeze({ ru: 'Кнопка', en: 'Button' }),
    PageLink: Object.freeze({ ru: 'Ссылка на страницу', en: 'Page link' }),
    TaskControls: Object.freeze({ ru: 'Управление запуском', en: 'Run controls' }),
    SuggestedPrompts: Object.freeze({ ru: 'Подсказки', en: 'Suggested prompts' }),
    FileCard: Object.freeze({ ru: 'Карточка файла', en: 'File card' }),
    FileList: Object.freeze({ ru: 'Список файлов', en: 'File list' }),
    DataTable: Object.freeze({ ru: 'Таблица', en: 'Table' }),
    ArtifactCard: Object.freeze({ ru: 'Карточка артефакта', en: 'Artifact card' }),
    Avatar: Object.freeze({ ru: 'Аватар', en: 'Avatar' }),
    AgentIdentity: Object.freeze({ ru: 'Агент', en: 'Agent identity' }),
    ArtifactFeed: Object.freeze({ ru: 'Лента артефактов', en: 'Artifact feed' }),
    RunTrace: Object.freeze({ ru: 'Трейс запуска', en: 'Run trace' }),
    ToolActivity: Object.freeze({ ru: 'Активность тулов', en: 'Tool activity' }),
    ConversationFeed: Object.freeze({ ru: 'Лента диалога', en: 'Conversation feed' }),
});

/**
 * Palette-only entries: they insert a prepared structure rather than one catalog
 * type, so the label says what the author gets (a row split into columns).
 */
export const FLOW_UI_PALETTE_PSEUDO_ENTRIES = Object.freeze([
    Object.freeze({
        type: 'Submit',
        editor: Object.freeze({
            group: 'action',
            icon: 'send',
            maturity: 'production',
            palette: true,
            label: Object.freeze({ ru: 'Кнопка отправки', en: 'Submit button' }),
        }),
    }),
    Object.freeze({
        type: 'Columns2',
        editor: Object.freeze({
            group: 'layout',
            icon: 'apps',
            maturity: 'production',
            palette: true,
            label: Object.freeze({ ru: 'Ряд: 2 колонки', en: 'Row: 2 columns' }),
        }),
    }),
    Object.freeze({
        type: 'Columns3',
        editor: Object.freeze({
            group: 'layout',
            icon: 'apps',
            maturity: 'production',
            palette: true,
            label: Object.freeze({ ru: 'Ряд: 3 колонки', en: 'Row: 3 columns' }),
        }),
    }),
    Object.freeze({
        type: 'Columns4',
        editor: Object.freeze({
            group: 'layout',
            icon: 'apps',
            maturity: 'production',
            palette: true,
            label: Object.freeze({ ru: 'Ряд: 4 колонки', en: 'Row: 4 columns' }),
        }),
    }),
]);

export const FLOW_UI_EDITOR_GROUPS = Object.freeze([
    'layout', 'content', 'input', 'action', 'data', 'platform',
]);

/** Editor palette maturity — stub types stay in catalog for runtime projection but not in palette. */
export const FLOW_UI_EDITOR_MATURITIES = Object.freeze([
    'production', 'partial', 'runtime_owned', 'stub',
]);

function editorMeta(type) {
    const meta = EDITOR_BY_TYPE[type];
    if (!meta) {
        return Object.freeze({
            group: 'platform',
            icon: 'box',
            schema: Object.freeze([]),
            defaults: Object.freeze({}),
            maturity: 'production',
            palette: true,
            label: editorLabel(type),
        });
    }
    const maturity = FLOW_UI_EDITOR_MATURITIES.includes(meta.maturity)
        ? meta.maturity
        : 'production';
    const palette = meta.palette === false || maturity === 'stub'
        ? false
        : true;
    return Object.freeze({
        group: meta.group,
        icon: meta.icon,
        schema: Object.freeze(meta.schema || []),
        defaults: Object.freeze(meta.defaults || {}),
        maturity,
        palette,
        label: editorLabel(type),
    });
}

/** Palette-visible types carry a pinned RU/EN name; the rest fall back to the type. */
function editorLabel(type) {
    const label = EDITOR_LABELS[type];
    if (label) return label;
    return Object.freeze({ ru: type, en: type });
}

function entry(type) {
    return Object.freeze({
        type,
        version: '1.0.0',
        kind: CONTAINERS.has(type) ? 'container' : 'leaf',
        category: BASIC.includes(type) ? 'Basic' : 'Linnex',
        security: 'trusted-declarative',
        supportsPlacement: true,
        layout: layoutCapabilitiesForType(type),
        editor: editorMeta(type),
    });
}

export const FLOW_UI_CATALOG_MANIFEST = Object.freeze({
    catalogId: LINNEX_CATALOG_ID,
    version: '1.0.0',
    checksum: 'linnex-flow-ui-catalog-v2',
    components: Object.freeze(
        Object.fromEntries([...BASIC, ...PLATFORM].map((type) => [type, entry(type)])),
    ),
});

/**
 * Catalog entries visible in the interface editor palette.
 * @returns {readonly object[]}
 */
export function flowUIPaletteComponentEntries() {
    return Object.freeze(
        Object.values(FLOW_UI_CATALOG_MANIFEST.components)
            .filter((entry) => entry.editor.palette !== false),
    );
}

/** Container types allowed to receive children in the editor. */
export const FLOW_UI_CONTAINER_TYPES = Object.freeze([...CONTAINERS]);

export { LAYOUT_NONE };
