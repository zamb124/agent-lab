/**
 * Домен редактора интерфейса: каталог блоков из JSON Schema грамматики (`GET /flow-ui/schema`),
 * команды над документом, история с коалесценцией и publish gate. Чистые функции без DOM и сети.
 *
 * Адресация контейнеров — строка ``containerKey``:
 *   ``page`` — корень страницы; ``<block_id>`` — ``section``;
 *   ``<block_id>/<index>`` — колонка ``columns`` или вкладка ``tabs``.
 */

import { INPUT_BLOCK_TYPES, STATE_PATH_PATTERN } from '@platform/lib/flow-ui/protocol/constants.js';
import { templatePaths, unmatchedBraceMessage } from '@platform/lib/flow-ui/runtime/templating.js';

export const HISTORY_LIMIT = 80;
/** Ширина холста по режиму просмотра, px. */
export const EDITOR_VIEWPORTS = Object.freeze({ desktop: 1180, tablet: 820, mobile: 390 });
export const EMPTY_DOCUMENT = Object.freeze({ start_page_id: 'main', pages: [{ page_id: 'main', title: '', blocks: [] }] });
export const CONTAINER_TYPES = Object.freeze(['section', 'columns', 'tabs']);
const ID_PATTERN = /^[a-z][a-z0-9_-]*$/;
const REF_PREFIX = '#/$defs/';

function refName(schema) {
    return typeof schema.$ref === 'string' && schema.$ref.startsWith(REF_PREFIX) ? schema.$ref.slice(REF_PREFIX.length) : null;
}

function nonNullVariants(schema) {
    return Array.isArray(schema.anyOf) ? schema.anyOf.filter((variant) => variant.type !== 'null') : [schema];
}

/** Вид свойства для панели «Свойства»; ``blocks``/``columns``/``tabs`` — структура, редактируется на холсте. */
export function propertyKind(name, schema) {
    if (name === 'blocks') return 'blocks';
    const variants = nonNullVariants(schema);
    const single = variants.length === 1 ? variants[0] : null;
    if (single !== null && 'const' in single) return 'const';
    if (single !== null && single['x-flow-ui'] === 'template') return 'template';
    if (single !== null && single['x-flow-ui'] === 'state_path') return 'state_path';
    if (variants.length === 2 && variants.some((variant) => variant.const === 'auto')) return 'height';
    if (single !== null) {
        const ref = refName(single);
        if (ref === 'FlowUIActionSpec') return 'action';
        if (ref === 'FlowUICondition') return 'condition';
        if (ref === 'FlowUIConversationSettings') return 'conversation_settings';
        if (Array.isArray(single.enum)) return 'enum';
        if (single.type === 'boolean') return 'boolean';
        if (single.type === 'integer') return 'integer';
        if (single.type === 'number') return 'number';
        if (single.type === 'object') return 'json';
        if (single.type === 'array') {
            const items = single.items;
            const itemRef = refName(items);
            if (itemRef === 'FlowUIColumn') return 'columns';
            if (itemRef === 'FlowUITab') return 'tabs';
            if (itemRef === 'FlowUISelectOption') return 'options';
            if (itemRef === 'FlowUITableColumn') return 'table_columns';
            if (items['x-flow-ui'] === 'state_path') return 'state_path_list';
            if (items['x-flow-ui'] === 'template') return 'template_list';
            return 'string_list';
        }
        if (single.type === 'string') return 'string';
    }
    if (variants.some((variant) => variant.type === 'number')) return 'number';
    if (variants.some((variant) => variant.type === 'array')) return 'select_default';
    throw new Error(`interface editor: unsupported property schema for ${name}`);
}

/**
 * Каталог блоков: ``{type, group, icon, defName, required, properties}``; порядок — как в схеме.
 * Свойство: ``{name, kind, required, default, enum, minimum, maximum, pattern}``.
 */
export function blockCatalog(schema) {
    const defs = schema.$defs;
    if (!defs || typeof defs !== 'object') throw new Error('interface editor: schema without $defs');
    const catalog = [];
    for (const [defName, definition] of Object.entries(defs)) {
        const tag = definition['x-flow-ui-block'];
        if (!tag) continue;
        const properties = [];
        for (const [name, propertySchema] of Object.entries(definition.properties)) {
            if (name === 'type') continue;
            const kind = propertyKind(name, propertySchema);
            const variant = nonNullVariants(propertySchema)[0];
            properties.push(Object.freeze({
                name,
                kind,
                required: Array.isArray(definition.required) && definition.required.includes(name),
                default: kind === 'conversation_settings'
                    ? schemaDefaults(defs.FlowUIConversationSettings)
                    : 'default' in propertySchema ? propertySchema.default : undefined,
                enum: Array.isArray(variant.enum) ? variant.enum : null,
                minimum: typeof variant.minimum === 'number' ? variant.minimum : null,
                maximum: typeof variant.maximum === 'number' ? variant.maximum : null,
                pattern: typeof variant.pattern === 'string' ? variant.pattern : null,
            }));
        }
        catalog.push(Object.freeze({
            type: definition.properties.type.const,
            defName,
            group: tag.group,
            icon: tag.icon,
            required: definition.required,
            properties: Object.freeze(properties),
        }));
    }
    return catalog;
}

/** Объект из defaults свойств определения (вложенные модели без default в схеме — списки). */
export function schemaDefaults(definition) {
    const values = {};
    for (const [name, propertySchema] of Object.entries(definition.properties)) {
        values[name] = 'default' in propertySchema ? structuredClone(propertySchema.default) : [];
    }
    return values;
}

export function catalogEntry(catalog, type) {
    const entry = catalog.find((item) => item.type === type);
    if (!entry) throw new Error(`interface editor: unknown block type ${JSON.stringify(type)}`);
    return entry;
}

/** Системные поля state из схемы (``x-flow-ui-frozen-state-fields``). */
export function frozenStateFields(schema) {
    const fields = schema['x-flow-ui-frozen-state-fields'];
    if (!Array.isArray(fields)) throw new Error('interface editor: schema without x-flow-ui-frozen-state-fields');
    return new Set(fields);
}

export function isFrozenPath(path, frozen) {
    return frozen.has(path.split('.')[0]);
}

// --- Обход -------------------------------------------------------------------------------

/** Дочерние контейнеры блока: ``[{key, blocks}]``; для листовых блоков — пусто. */
export function childContainers(block) {
    if (block.type === 'section') return [{ key: block.block_id, blocks: block.blocks }];
    if (block.type === 'columns') return block.columns.map((column, index) => ({ key: `${block.block_id}/${index}`, blocks: column.blocks }));
    if (block.type === 'tabs') return block.tabs.map((tab, index) => ({ key: `${block.block_id}/${index}`, blocks: tab.blocks }));
    return [];
}

/** Все блоки страницы в порядке документа с контейнером и индексом. */
export function walkPage(page) {
    const found = [];
    const visit = (blocks, containerKey, depth) => {
        blocks.forEach((block, index) => {
            found.push({ block, containerKey, index, depth });
            for (const child of childContainers(block)) visit(child.blocks, child.key, depth + 1);
        });
    };
    visit(page.blocks, 'page', 0);
    return found;
}

export function findPage(document, pageId) {
    const page = document.pages.find((item) => item.page_id === pageId);
    if (!page) throw new Error(`interface editor: unknown page ${JSON.stringify(pageId)}`);
    return page;
}

export function locateBlock(page, blockId) {
    const entry = walkPage(page).find((item) => item.block.block_id === blockId);
    if (!entry) throw new Error(`interface editor: unknown block ${JSON.stringify(blockId)}`);
    return entry;
}

/** Массив блоков контейнера внутри (уже склонированной) страницы. */
export function containerBlocks(page, containerKey) {
    if (containerKey === 'page') return page.blocks;
    const [blockId, indexText] = containerKey.split('/');
    const { block } = locateBlock(page, blockId);
    const container = childContainers(block).find((item) => item.key === containerKey);
    if (!container) throw new Error(`interface editor: block ${blockId} has no container ${indexText ?? ''}`);
    return container.blocks;
}

function isDescendantContainer(page, containerKey, blockId) {
    if (containerKey === 'page') return false;
    const ownerId = containerKey.split('/')[0];
    if (ownerId === blockId) return true;
    const { containerKey: parentKey } = locateBlock(page, ownerId);
    return isDescendantContainer(page, parentKey, blockId);
}

// --- Идентификаторы и заготовки ---------------------------------------------------------

function nextFreeId(type, taken) {
    const base = type.replaceAll('_', '-');
    if (!taken.has(base)) return base;
    let counter = 2;
    while (taken.has(`${base}-${counter}`)) counter += 1;
    return `${base}-${counter}`;
}

export function uniqueBlockId(page, type) {
    return nextFreeId(type, new Set(walkPage(page).map((item) => item.block.block_id)));
}

export function uniquePageId(document) {
    const taken = new Set(document.pages.map((page) => page.page_id));
    let counter = document.pages.length + 1;
    while (taken.has(`page-${counter}`)) counter += 1;
    return `page-${counter}`;
}

/** Заготовка блока: обязательные свойства заполняются осмысленными значениями, остальные — defaults схемы. */
export function defaultBlock(entry, blockId, labels) {
    const block = { type: entry.type, block_id: blockId };
    for (const property of entry.properties) {
        if (property.name === 'block_id' || property.kind === 'const') continue;
        if (property.kind === 'blocks') {
            block.blocks = [];
            continue;
        }
        if (property.kind === 'columns') {
            block.columns = [{ width: 6, blocks: [] }, { width: 6, blocks: [] }];
            continue;
        }
        if (property.kind === 'tabs') {
            block.tabs = [{ title: `${labels.tab} 1`, blocks: [] }, { title: `${labels.tab} 2`, blocks: [] }];
            continue;
        }
        if (property.default !== undefined) {
            block[property.name] = structuredClone(property.default);
            continue;
        }
        if (!property.required) {
            block[property.name] = property.kind === 'string_list' || property.kind === 'state_path_list' || property.kind === 'template_list' || property.kind === 'options' || property.kind === 'table_columns' ? [] : property.kind === 'json' ? {} : null;
            continue;
        }
        block[property.name] = requiredDefault(entry.type, property, blockId, labels);
    }
    if (entry.type === 'link') block.url = 'https://';
    if (entry.type === 'data_table') block.rows = 'rows';
    if (entry.type === 'file_card') block.file = 'file';
    if (entry.type === 'html') {
        // Стартовый исходник (i18n ``default_text_html_source``) читает ``state.items`` из скрипта
        // и пишет ввод через ``flowUi.setValue`` — блок объявляет эти пути сразу.
        block.fields = ['items'];
        block.field = blockId.replaceAll('-', '_');
    }
    return block;
}

function requiredDefault(type, property, blockId, labels) {
    switch (property.kind) {
        case 'template':
            return labels.text(type, property.name);
        case 'state_path':
            return blockId.replaceAll('-', '_');
        case 'action':
            return { name: 'submit', payload: {} };
        case 'options':
            return [{ value: 'option_1', label: `${labels.option} 1` }, { value: 'option_2', label: `${labels.option} 2` }];
        case 'template_list':
            return [labels.text(type, property.name)];
        case 'string_list':
            return ['value'];
        case 'string':
            if (property.name === 'x') return 'label';
            if (property.name === 'agent_skill_id') return 'skill';
            return labels.text(type, property.name);
        case 'json':
            return {};
        default:
            throw new Error(`interface editor: no default for required ${type}.${property.name}`);
    }
}

export function withColumns(entry, blockId, count, labels) {
    const block = defaultBlock(entry, blockId, labels);
    const width = Math.floor(12 / count);
    block.columns = Array.from({ length: count }, () => ({ width, blocks: [] }));
    return block;
}

function regenerateIds(block, page) {
    const taken = new Set(walkPage(page).map((item) => item.block.block_id));
    const copy = structuredClone(block);
    const rename = (item) => {
        item.block_id = nextFreeId(item.type, taken);
        taken.add(item.block_id);
        for (const child of childContainers(item)) child.blocks.forEach(rename);
    };
    rename(copy);
    return copy;
}

// --- Команды ------------------------------------------------------------------------------

export function insertBlock(document, pageId, containerKey, index, block) {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    const blocks = containerBlocks(page, containerKey);
    blocks.splice(Math.min(Math.max(index, 0), blocks.length), 0, block);
    return next;
}

export function moveBlock(document, pageId, blockId, containerKey, index) {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    if (isDescendantContainer(page, containerKey, blockId)) throw new Error('interface editor: cannot move a block into itself');
    const source = locateBlock(page, blockId);
    const sourceBlocks = containerBlocks(page, source.containerKey);
    const [block] = sourceBlocks.splice(source.index, 1);
    const targetBlocks = containerBlocks(page, containerKey);
    const shift = source.containerKey === containerKey && source.index < index ? 1 : 0;
    targetBlocks.splice(Math.min(Math.max(index - shift, 0), targetBlocks.length), 0, block);
    return next;
}

export function removeBlock(document, pageId, blockId) {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    const { containerKey, index } = locateBlock(page, blockId);
    containerBlocks(page, containerKey).splice(index, 1);
    return next;
}

export function setBlockProperty(document, pageId, blockId, property, value) {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    const { block } = locateBlock(page, blockId);
    if (property === 'block_id') {
        if (walkPage(page).some((item) => item.block !== block && item.block.block_id === value)) {
            throw new Error(`interface editor: block id ${JSON.stringify(value)} is already used on this page`);
        }
    }
    block[property] = value;
    return next;
}

export function duplicateBlock(document, pageId, blockId) {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    const { block, containerKey, index } = locateBlock(page, blockId);
    const copy = regenerateIds(block, page);
    containerBlocks(page, containerKey).splice(index + 1, 0, copy);
    return next;
}

export function wrapInSection(document, pageId, blockId) {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    const { block, containerKey, index } = locateBlock(page, blockId);
    const section = { type: 'section', block_id: uniqueBlockId(page, 'section'), title: '', visible_when: null, blocks: [block] };
    containerBlocks(page, containerKey).splice(index, 1, section);
    return next;
}

export function insertPage(document, page) {
    return { ...structuredClone(document), pages: [...structuredClone(document.pages), page] };
}

export function removePage(document, pageId) {
    if (document.pages.length === 1) throw new Error('interface editor: document requires at least one page');
    const next = structuredClone(document);
    next.pages = next.pages.filter((page) => page.page_id !== pageId);
    if (next.start_page_id === pageId) next.start_page_id = next.pages[0].page_id;
    return next;
}

export function setPageProperty(document, pageId, property, value) {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    if (property === 'page_id') {
        if (next.pages.some((item) => item !== page && item.page_id === value)) {
            throw new Error(`interface editor: page id ${JSON.stringify(value)} is already used`);
        }
        if (next.start_page_id === pageId) next.start_page_id = value;
        for (const entry of next.pages.flatMap(walkPage)) {
            if (entry.block.type === 'link' && entry.block.page_id === pageId) entry.block.page_id = value;
        }
    }
    page[property] = value;
    return next;
}

export function replacePageBlocks(document, pageId, blocks) {
    const next = structuredClone(document);
    findPage(next, pageId).blocks = structuredClone(blocks);
    return next;
}

// --- История -----------------------------------------------------------------------------

export function createHistory(document) {
    return { present: document, past: [], future: [], coalesceKey: null };
}

/** Новое состояние; одинаковый ``coalesceKey`` (``block_id:property``) подряд заменяет вершину истории. */
export function commitHistory(history, document, coalesceKey = null) {
    if (coalesceKey !== null && coalesceKey === history.coalesceKey) {
        return { ...history, present: document, future: [] };
    }
    const past = [...history.past, history.present].slice(-HISTORY_LIMIT);
    return { present: document, past, future: [], coalesceKey };
}

export function undoHistory(history) {
    if (history.past.length === 0) return history;
    const past = history.past.slice(0, -1);
    return { present: history.past[history.past.length - 1], past, future: [history.present, ...history.future], coalesceKey: null };
}

export function redoHistory(history) {
    if (history.future.length === 0) return history;
    const [present, ...future] = history.future;
    return { present, past: [...history.past, history.present], future, coalesceKey: null };
}

// --- Publish gate ------------------------------------------------------------------------

function templateProperties(entry, block) {
    const templates = [];
    for (const property of entry.properties) {
        const value = block[property.name];
        if (property.kind === 'template' && typeof value === 'string') templates.push(value);
        if (property.kind === 'template_list' && Array.isArray(value)) templates.push(...value.filter((item) => typeof item === 'string'));
        if (property.kind === 'options' && Array.isArray(value)) templates.push(...value.map((option) => option.label));
        if (property.kind === 'table_columns' && Array.isArray(value)) templates.push(...value.map((column) => column.label));
    }
    if (block.type === 'conversation') {
        templates.push(block.settings.greeting, block.settings.placeholder, ...block.settings.suggested_prompts);
    }
    return templates;
}

function statePathProperties(entry, block) {
    const paths = [];
    for (const property of entry.properties) {
        const value = block[property.name];
        if (property.kind === 'state_path' && typeof value === 'string') paths.push({ property: property.name, path: value });
        if (property.kind === 'state_path_list' && Array.isArray(value)) paths.push(...value.map((path) => ({ property: property.name, path })));
    }
    if (block.visible_when && typeof block.visible_when.path === 'string') paths.push({ property: 'visible_when', path: block.visible_when.path });
    return paths;
}

/**
 * Проблемы документа: ``{code, severity, pageId, blockId, property, params}``.
 * ``error`` блокирует публикацию, ``warning`` — нет.
 */
export function documentProblems(document, catalog, frozen) {
    const problems = [];
    const pageIds = new Set(document.pages.map((page) => page.page_id));
    if (!pageIds.has(document.start_page_id)) problems.push({ code: 'start_page_missing', severity: 'error', pageId: null, blockId: null, property: null, params: {} });
    for (const page of document.pages) {
        const report = (code, severity, blockId, property = null, params = {}) => problems.push({ code, severity, pageId: page.page_id, blockId, property, params });
        if (!ID_PATTERN.test(page.page_id)) report('page_id_invalid', 'error', null, 'page_id', { value: page.page_id });
        const entries = walkPage(page);
        const seen = new Set();
        let hasInputs = false;
        let hasAction = false;
        for (const { block } of entries) {
            const entry = catalog.find((item) => item.type === block.type);
            if (!entry) {
                report('block_type_unknown', 'error', block.block_id, 'type', { value: String(block.type) });
                continue;
            }
            if (typeof block.block_id !== 'string' || !ID_PATTERN.test(block.block_id)) report('block_id_invalid', 'error', block.block_id, 'block_id', { value: String(block.block_id) });
            if (seen.has(block.block_id)) report('block_id_duplicate', 'error', block.block_id, 'block_id', { value: block.block_id });
            seen.add(block.block_id);
            for (const property of entry.properties) {
                if (!property.required || property.kind === 'const' || property.kind === 'blocks') continue;
                const value = block[property.name];
                const empty = value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0);
                if (empty) report('property_required', 'error', block.block_id, property.name, { property: property.name });
            }
            if (INPUT_BLOCK_TYPES.has(block.type)) hasInputs = true;
            if (block.type === 'button' || (INPUT_BLOCK_TYPES.has(block.type) && block.action)) hasAction = true;
            for (const { property, path } of statePathProperties(entry, block)) {
                if (!STATE_PATH_PATTERN.test(path)) report('state_path_invalid', 'error', block.block_id, property, { value: path });
                else if (isFrozenPath(path, frozen)) report('state_path_frozen', 'error', block.block_id, property, { value: path });
            }
            for (const template of templateProperties(entry, block)) {
                if (unmatchedBraceMessage(template) !== null) report('template_unbalanced', 'error', block.block_id, null, { value: template });
                for (const path of templatePaths(template)) {
                    if (isFrozenPath(path, frozen)) report('template_path_frozen', 'error', block.block_id, null, { value: path });
                }
            }
            if (block.type === 'link' && block.page_id !== null && !pageIds.has(block.page_id)) report('link_page_missing', 'error', block.block_id, 'page_id', { value: block.page_id });
            if (block.type === 'link' && (block.page_id === null) === (block.url === '')) report('link_target', 'error', block.block_id, 'url', {});
            if (block.type === 'data_table' && (block.rows === null) === (block.file_id === '')) report('data_table_source', 'error', block.block_id, 'rows', {});
            if (block.type === 'file_card' && (block.file === null) === (block.file_id === '')) report('file_card_source', 'error', block.block_id, 'file', {});
            if (block.type === 'columns' && block.columns.reduce((sum, column) => sum + column.width, 0) > 12) report('columns_overflow', 'warning', block.block_id, 'columns', {});
            if (block.type === 'html' && typeof block.height === 'number' && (block.height < 24 || block.height > 4000)) report('html_height', 'error', block.block_id, 'height', {});
        }
        if (hasInputs && !hasAction) report('inputs_without_action', 'error', null, null, {});
    }
    return problems;
}

export function hasBlockingProblems(problems) {
    return problems.some((problem) => problem.severity === 'error');
}

// --- Каталог путей state для подсказок ---------------------------------------------------

/** ``[{path, type, source, protected}]`` из dataflow inspector, тестового state и input-блоков документа. */
export function statePathCatalog({ dataflow, sampleState, document }) {
    const byPath = new Map();
    const add = (path, type, source, isProtected) => {
        if (typeof path !== 'string' || path === '' || byPath.has(path)) return;
        byPath.set(path, { path, type, source, protected: isProtected });
    };
    if (dataflow && typeof dataflow === 'object') {
        for (const descriptor of Array.isArray(dataflow.variables) ? dataflow.variables : []) add(descriptor.path, descriptor.type, descriptor.source, descriptor.protected === true);
        for (const node of Object.values(dataflow.nodes && typeof dataflow.nodes === 'object' ? dataflow.nodes : {})) {
            for (const descriptor of [...node.output_state, ...node.incoming_state]) add(descriptor.path, descriptor.type, descriptor.source, descriptor.protected === true);
        }
    }
    if (sampleState && typeof sampleState === 'object') {
        for (const [key, value] of Object.entries(sampleState)) add(key, Array.isArray(value) ? 'list' : value === null ? 'null' : typeof value, 'preview_state', false);
    }
    for (const page of document.pages) {
        for (const { block } of walkPage(page)) {
            if (INPUT_BLOCK_TYPES.has(block.type) && typeof block.field === 'string') add(block.field, 'string', 'interface', false);
            if (block.type === 'html' && typeof block.field === 'string') add(block.field, 'any', 'interface', false);
        }
    }
    return [...byPath.values()].sort((a, b) => a.path.localeCompare(b.path));
}
