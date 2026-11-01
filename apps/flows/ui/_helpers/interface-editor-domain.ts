/**
 * Домен редактора интерфейса: каталог блоков из JSON Schema грамматики (`GET /flow-ui/schema`),
 * команды над документом, история с коалесценцией и publish gate. Чистые функции без DOM и сети.
 *
 * Адресация контейнеров — строка ``containerKey``:
 *   ``page`` — корень страницы; ``<block_id>`` — ``section``;
 *   ``<block_id>/<index>`` — колонка ``columns`` или вкладка ``tabs``.
 */

import { INPUT_BLOCK_TYPES, STATE_PATH_PATTERN } from '@platform/lib/a2a/constants.js';
import { templatePaths, unmatchedBraceMessage } from '@platform/lib/flow-ui/runtime/templating.js';

export const HISTORY_LIMIT = 80;
/** Ширина холста по режиму просмотра, px. */
export const EDITOR_VIEWPORTS = Object.freeze({ desktop: 1180, tablet: 820, mobile: 390 });
export const EMPTY_DOCUMENT = Object.freeze({ start_page_id: 'main', pages: [{ page_id: 'main', title: '', blocks: [] }] });
export const CONTAINER_TYPES = Object.freeze(['section', 'columns', 'tabs']);
const ID_PATTERN = /^[a-z][a-z0-9_-]*$/;
const REF_PREFIX = '#/$defs/';

export interface FlowUiBlock {
    type: string;
    block_id: string;
    [key: string]: unknown;
}

export interface FlowUiColumn {
    width: number;
    blocks: FlowUiBlock[];
}

export interface FlowUiTab {
    blocks: FlowUiBlock[];
    title?: string;
}

export interface FlowUiPage {
    page_id: string;
    blocks: FlowUiBlock[];
    [key: string]: unknown;
}

export interface FlowUiDocument {
    start_page_id: string;
    pages: FlowUiPage[];
    [key: string]: unknown;
}

export interface CatalogProperty {
    readonly name: string;
    readonly kind: string;
    readonly required: boolean;
    readonly default: unknown;
    readonly enum: readonly unknown[] | null;
    readonly minimum: number | null;
    readonly maximum: number | null;
    readonly pattern: string | null;
}

export interface CatalogEntry {
    readonly type: string;
    readonly defName: string;
    readonly group: unknown;
    readonly icon: unknown;
    readonly required: unknown;
    readonly properties: readonly CatalogProperty[];
}

export interface BlockLabels {
    tab: string;
    option: string;
    text: (type: string, name: string) => string;
}

export interface EditorHistory {
    present: FlowUiDocument;
    past: FlowUiDocument[];
    future: FlowUiDocument[];
    coalesceKey: string | null;
}

export interface DocumentProblem {
    code: string;
    severity: 'error' | 'warning';
    pageId: string | null;
    blockId: string | null;
    property: string | null;
    params: Record<string, unknown>;
}

export interface StatePathEntry {
    path: string;
    type: string;
    source: string;
    protected: boolean;
}

interface BlockLocation {
    block: FlowUiBlock;
    containerKey: string;
    index: number;
    depth: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isFlowUiBlock(value: unknown): value is FlowUiBlock {
    return isRecord(value) && typeof value.type === 'string' && typeof value.block_id === 'string';
}

function isBlockArray(value: unknown): value is FlowUiBlock[] {
    return Array.isArray(value) && value.every(isFlowUiBlock);
}

function isFlowUiColumn(value: unknown): value is FlowUiColumn {
    return isRecord(value) && typeof value.width === 'number' && isBlockArray(value.blocks);
}

function isColumnArray(value: unknown): value is FlowUiColumn[] {
    return Array.isArray(value) && value.every(isFlowUiColumn);
}

function isFlowUiTab(value: unknown): value is FlowUiTab {
    if (!isRecord(value) || !isBlockArray(value.blocks)) return false;
    return value.title === undefined || typeof value.title === 'string';
}

function isTabArray(value: unknown): value is FlowUiTab[] {
    return Array.isArray(value) && value.every(isFlowUiTab);
}

function isFlowUiPage(value: unknown): value is FlowUiPage {
    return isRecord(value) && typeof value.page_id === 'string' && isBlockArray(value.blocks);
}

function isPageArray(value: unknown): value is FlowUiPage[] {
    return Array.isArray(value) && value.every(isFlowUiPage);
}

function isFlowUiDocument(value: unknown): value is FlowUiDocument {
    return isRecord(value) && typeof value.start_page_id === 'string' && isPageArray(value.pages);
}

function requireDocument(value: unknown): FlowUiDocument {
    if (!isFlowUiDocument(value)) throw new Error('interface editor: document required');
    return value;
}

function requirePageBlocks(page: FlowUiPage): FlowUiBlock[] {
    if (!isBlockArray(page.blocks)) throw new Error(`interface editor: page ${page.page_id} blocks required`);
    return page.blocks;
}

function requireSectionBlocks(block: FlowUiBlock): FlowUiBlock[] {
    if (!isBlockArray(block.blocks)) throw new Error(`interface editor: ${block.block_id} blocks required`);
    return block.blocks;
}

function requireColumns(block: FlowUiBlock): FlowUiColumn[] {
    if (!isColumnArray(block.columns)) throw new Error(`interface editor: ${block.block_id} columns required`);
    return block.columns;
}

function requireTabs(block: FlowUiBlock): FlowUiTab[] {
    if (!isTabArray(block.tabs)) throw new Error(`interface editor: ${block.block_id} tabs required`);
    return block.tabs;
}

function refName(schema: unknown): string | null {
    if (!isRecord(schema) || typeof schema.$ref !== 'string' || !schema.$ref.startsWith(REF_PREFIX)) return null;
    return schema.$ref.slice(REF_PREFIX.length);
}

function nonNullVariants(schema: unknown): Record<string, unknown>[] {
    if (!isRecord(schema)) throw new Error('interface editor: property schema required');
    if (!Array.isArray(schema.anyOf)) return [schema];
    const variants: Record<string, unknown>[] = [];
    for (const variant of schema.anyOf) {
        if (!isRecord(variant) || variant.type === 'null') continue;
        variants.push(variant);
    }
    return variants;
}

/** Вид свойства для панели «Свойства»; ``blocks``/``columns``/``tabs`` — структура, редактируется на холсте. */
export function propertyKind(name: string, schema: unknown): string {
    if (name === 'blocks') return 'blocks';
    const variants = nonNullVariants(schema);
    const single = variants.length === 1 ? variants[0] : null;
    if (single === undefined) throw new Error(`interface editor: unsupported property schema for ${name}`);
    if (single !== null && 'const' in single) return 'const';
    if (single !== null && single['x-flow-ui'] === 'template') return 'template';
    if (single !== null && single['x-flow-ui'] === 'state_path') return 'state_path';
    if (single !== null && single['x-flow-ui'] === 'image_url') return 'image_url';
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
            if (!isRecord(items)) throw new Error(`interface editor: unsupported property schema for ${name}`);
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
export function blockCatalog(schema: unknown): CatalogEntry[] {
    if (!isRecord(schema) || !isRecord(schema.$defs)) throw new Error('interface editor: schema without $defs');
    const defs = schema.$defs;
    const catalog: CatalogEntry[] = [];
    for (const [defName, definition] of Object.entries(defs)) {
        if (!isRecord(definition)) continue;
        const tag = definition['x-flow-ui-block'];
        if (!isRecord(tag)) continue;
        const propertiesSchema = definition.properties;
        if (!isRecord(propertiesSchema)) throw new Error(`interface editor: ${defName} properties required`);
        const requiredNames = Array.isArray(definition.required) ? definition.required : [];
        const properties: CatalogProperty[] = [];
        for (const [name, propertySchema] of Object.entries(propertiesSchema)) {
            if (name === 'type') continue;
            const kind = propertyKind(name, propertySchema);
            const variant = nonNullVariants(propertySchema)[0];
            if (variant === undefined) throw new Error(`interface editor: unsupported property schema for ${name}`);
            const schemaDefault = kind === 'conversation_settings'
                ? schemaDefaults(defs.FlowUIConversationSettings)
                : isRecord(propertySchema) && 'default' in propertySchema ? propertySchema.default : undefined;
            properties.push(Object.freeze({
                name,
                kind,
                required: requiredNames.includes(name),
                default: schemaDefault,
                enum: Array.isArray(variant.enum) ? variant.enum : null,
                minimum: typeof variant.minimum === 'number' ? variant.minimum : null,
                maximum: typeof variant.maximum === 'number' ? variant.maximum : null,
                pattern: typeof variant.pattern === 'string' ? variant.pattern : null,
            }));
        }
        const typeSchema = propertiesSchema.type;
        if (!isRecord(typeSchema) || typeof typeSchema.const !== 'string') {
            throw new Error(`interface editor: ${defName} type const required`);
        }
        catalog.push(Object.freeze({
            type: typeSchema.const,
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
export function schemaDefaults(definition: unknown): Record<string, unknown> {
    if (!isRecord(definition) || !isRecord(definition.properties)) {
        throw new Error('interface editor: definition properties required');
    }
    const values: Record<string, unknown> = {};
    for (const [name, propertySchema] of Object.entries(definition.properties)) {
        if (!isRecord(propertySchema) || !('default' in propertySchema)) {
            values[name] = [];
            continue;
        }
        values[name] = structuredClone(propertySchema.default);
    }
    return values;
}

export function catalogEntry(catalog: readonly CatalogEntry[], type: string): CatalogEntry {
    const entry = catalog.find((item) => item.type === type);
    if (entry === undefined) throw new Error(`interface editor: unknown block type ${JSON.stringify(type)}`);
    return entry;
}

/** Системные поля state из схемы (``x-flow-ui-frozen-state-fields``). */
export function frozenStateFields(schema: unknown): Set<string> {
    if (!isRecord(schema)) throw new Error('interface editor: schema without x-flow-ui-frozen-state-fields');
    const fields = schema['x-flow-ui-frozen-state-fields'];
    if (!Array.isArray(fields)) throw new Error('interface editor: schema without x-flow-ui-frozen-state-fields');
    const names = new Set<string>();
    for (const field of fields) {
        if (typeof field !== 'string') throw new Error('interface editor: frozen state field must be a string');
        names.add(field);
    }
    return names;
}

export function isFrozenPath(path: string, frozen: ReadonlySet<string>): boolean {
    const root = path.split('.')[0];
    if (root === undefined) throw new Error('interface editor: state path required');
    return frozen.has(root);
}

// --- Обход -------------------------------------------------------------------------------

/** Дочерние контейнеры блока: ``[{key, blocks}]``; для листовых блоков — пусто. */
export function childContainers(block: FlowUiBlock): { key: string; blocks: FlowUiBlock[] }[] {
    if (block.type === 'section') return [{ key: block.block_id, blocks: requireSectionBlocks(block) }];
    if (block.type === 'columns') {
        return requireColumns(block).map((column, index) => ({ key: `${block.block_id}/${index}`, blocks: column.blocks }));
    }
    if (block.type === 'tabs') {
        return requireTabs(block).map((tab, index) => ({ key: `${block.block_id}/${index}`, blocks: tab.blocks }));
    }
    return [];
}

/** Все блоки страницы в порядке документа с контейнером и индексом. */
export function walkPage(page: FlowUiPage): BlockLocation[] {
    const found: BlockLocation[] = [];
    const visit = (blocks: FlowUiBlock[], containerKey: string, depth: number) => {
        blocks.forEach((block, index) => {
            found.push({ block, containerKey, index, depth });
            for (const child of childContainers(block)) visit(child.blocks, child.key, depth + 1);
        });
    };
    visit(requirePageBlocks(page), 'page', 0);
    return found;
}

export function findPage(document: FlowUiDocument, pageId: string): FlowUiPage {
    if (!isPageArray(document.pages)) throw new Error('interface editor: document pages required');
    const page = document.pages.find((item) => item.page_id === pageId);
    if (page === undefined) throw new Error(`interface editor: unknown page ${JSON.stringify(pageId)}`);
    return page;
}

export function locateBlock(page: FlowUiPage, blockId: string): BlockLocation {
    const entry = walkPage(page).find((item) => item.block.block_id === blockId);
    if (entry === undefined) throw new Error(`interface editor: unknown block ${JSON.stringify(blockId)}`);
    return entry;
}

/** Массив блоков контейнера внутри (уже склонированной) страницы. */
export function containerBlocks(page: FlowUiPage, containerKey: string): FlowUiBlock[] {
    if (containerKey === 'page') return requirePageBlocks(page);
    const [blockId, indexText] = containerKey.split('/');
    if (blockId === undefined) throw new Error('interface editor: container key required');
    const { block } = locateBlock(page, blockId);
    const container = childContainers(block).find((item) => item.key === containerKey);
    const indexLabel = indexText === undefined ? '' : indexText;
    if (container === undefined) throw new Error(`interface editor: block ${blockId} has no container ${indexLabel}`);
    return container.blocks;
}

/** Куда вставлять блок из палитры: в выбранный контейнер, иначе после выделенного блока или в конец страницы. */
export function paletteInsertTarget(page: FlowUiPage, selectedBlockId: string | null): { containerKey: string; index: number } {
    const pageBlocks = requirePageBlocks(page);
    if (selectedBlockId === null || selectedBlockId === '') {
        return { containerKey: 'page', index: pageBlocks.length };
    }
    const { block, containerKey, index } = locateBlock(page, selectedBlockId);
    if (block.type === 'section') return { containerKey: block.block_id, index: requireSectionBlocks(block).length };
    if (block.type === 'columns') {
        const columns = requireColumns(block);
        const columnIndex = Math.max(0, columns.findIndex((column) => column.blocks.length === 0));
        const column = columns[columnIndex];
        if (column === undefined) throw new Error(`interface editor: ${block.block_id} column required`);
        return { containerKey: `${block.block_id}/${columnIndex}`, index: column.blocks.length };
    }
    if (block.type === 'tabs') {
        const tabs = requireTabs(block);
        const tabIndex = Math.max(0, tabs.findIndex((tab) => tab.blocks.length === 0));
        const tab = tabs[tabIndex];
        if (tab === undefined) throw new Error(`interface editor: ${block.block_id} tab required`);
        return { containerKey: `${block.block_id}/${tabIndex}`, index: tab.blocks.length };
    }
    return { containerKey, index: index + 1 };
}

function isDescendantContainer(page: FlowUiPage, containerKey: string, blockId: string): boolean {
    if (containerKey === 'page') return false;
    const ownerId = containerKey.split('/')[0];
    if (ownerId === undefined) throw new Error('interface editor: container key required');
    if (ownerId === blockId) return true;
    const { containerKey: parentKey } = locateBlock(page, ownerId);
    return isDescendantContainer(page, parentKey, blockId);
}

// --- Идентификаторы и заготовки ---------------------------------------------------------

function nextFreeId(type: string, taken: ReadonlySet<string>): string {
    const base = type.replaceAll('_', '-');
    if (!taken.has(base)) return base;
    let counter = 2;
    while (taken.has(`${base}-${counter}`)) counter += 1;
    return `${base}-${counter}`;
}

export function uniqueBlockId(page: FlowUiPage, type: string): string {
    return nextFreeId(type, new Set(walkPage(page).map((item) => item.block.block_id)));
}

export function uniquePageId(document: FlowUiDocument): string {
    if (!isPageArray(document.pages)) throw new Error('interface editor: document pages required');
    const taken = new Set(document.pages.map((page) => page.page_id));
    let counter = document.pages.length + 1;
    while (taken.has(`page-${counter}`)) counter += 1;
    return `page-${counter}`;
}

/** Заготовка блока: обязательные свойства заполняются осмысленными значениями, остальные — defaults схемы. */
export function defaultBlock(entry: CatalogEntry, blockId: string, labels: BlockLabels): FlowUiBlock {
    const block: FlowUiBlock = { type: entry.type, block_id: blockId };
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
    if (entry.type === 'button') block.action = { name: 'submit', payload: {} };
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

function requiredDefault(type: string, property: CatalogProperty, blockId: string, labels: BlockLabels): unknown {
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

export function withColumns(entry: CatalogEntry, blockId: string, count: number, labels: BlockLabels): FlowUiBlock {
    const block = defaultBlock(entry, blockId, labels);
    const width = Math.floor(12 / count);
    block.columns = Array.from({ length: count }, () => ({ width, blocks: [] }));
    return block;
}

function regenerateIds(block: FlowUiBlock, page: FlowUiPage): FlowUiBlock {
    const taken = new Set(walkPage(page).map((item) => item.block.block_id));
    const copy = structuredClone(block);
    const rename = (item: FlowUiBlock) => {
        item.block_id = nextFreeId(item.type, taken);
        taken.add(item.block_id);
        for (const child of childContainers(item)) child.blocks.forEach(rename);
    };
    rename(copy);
    return copy;
}

// --- Команды ------------------------------------------------------------------------------

export function insertBlock(document: FlowUiDocument, pageId: string, containerKey: string, index: number, block: FlowUiBlock): FlowUiDocument {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    const blocks = containerBlocks(page, containerKey);
    blocks.splice(Math.min(Math.max(index, 0), blocks.length), 0, block);
    return next;
}

export function moveBlock(document: FlowUiDocument, pageId: string, blockId: string, containerKey: string, index: number): FlowUiDocument {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    if (isDescendantContainer(page, containerKey, blockId)) throw new Error('interface editor: cannot move a block into itself');
    const source = locateBlock(page, blockId);
    const sourceBlocks = containerBlocks(page, source.containerKey);
    const removed = sourceBlocks.splice(source.index, 1);
    const block = removed[0];
    if (block === undefined) throw new Error(`interface editor: unknown block ${JSON.stringify(blockId)}`);
    const targetBlocks = containerBlocks(page, containerKey);
    const shift = source.containerKey === containerKey && source.index < index ? 1 : 0;
    targetBlocks.splice(Math.min(Math.max(index - shift, 0), targetBlocks.length), 0, block);
    return next;
}

export function removeBlock(document: FlowUiDocument, pageId: string, blockId: string): FlowUiDocument {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    const { containerKey, index } = locateBlock(page, blockId);
    containerBlocks(page, containerKey).splice(index, 1);
    return next;
}

export function setBlockProperty(document: FlowUiDocument, pageId: string, blockId: string, property: string, value: unknown): FlowUiDocument {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    const { block } = locateBlock(page, blockId);
    if (property === 'block_id') {
        if (typeof value !== 'string') throw new Error('interface editor: block id must be a string');
        if (walkPage(page).some((item) => item.block !== block && item.block.block_id === value)) {
            throw new Error(`interface editor: block id ${JSON.stringify(value)} is already used on this page`);
        }
    }
    if (property === 'click_target' && isRecord(value)) {
        Object.assign(block, value);
        return next;
    }
    block[property] = value;
    return next;
}

export function duplicateBlock(document: FlowUiDocument, pageId: string, blockId: string): FlowUiDocument {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    const { block, containerKey, index } = locateBlock(page, blockId);
    const copy = regenerateIds(block, page);
    containerBlocks(page, containerKey).splice(index + 1, 0, copy);
    return next;
}

export function wrapInSection(document: FlowUiDocument, pageId: string, blockId: string): FlowUiDocument {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    const { block, containerKey, index } = locateBlock(page, blockId);
    const section: FlowUiBlock = { type: 'section', block_id: uniqueBlockId(page, 'section'), title: '', visible_when: null, span: 12, align: 'start', valign: 'start', blocks: [block] };
    containerBlocks(page, containerKey).splice(index, 1, section);
    return next;
}

export function insertPage(document: FlowUiDocument, page: FlowUiPage): FlowUiDocument {
    const next = structuredClone(document);
    if (!isPageArray(next.pages)) throw new Error('interface editor: document pages required');
    next.pages = [...next.pages, page];
    return next;
}

export function removePage(document: FlowUiDocument, pageId: string): FlowUiDocument {
    if (!isPageArray(document.pages)) throw new Error('interface editor: document pages required');
    if (document.pages.length === 1) throw new Error('interface editor: document requires at least one page');
    const next = structuredClone(document);
    if (!isPageArray(next.pages)) throw new Error('interface editor: document pages required');
    next.pages = next.pages.filter((page) => page.page_id !== pageId);
    if (next.start_page_id === pageId) {
        const first = next.pages[0];
        if (first === undefined) throw new Error('interface editor: document requires at least one page');
        next.start_page_id = first.page_id;
    }
    return next;
}

export function setPageProperty(document: FlowUiDocument, pageId: string, property: string, value: unknown): FlowUiDocument {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    if (property === 'page_id') {
        if (typeof value !== 'string') throw new Error('interface editor: page id must be a string');
        if (!isPageArray(next.pages)) throw new Error('interface editor: document pages required');
        if (next.pages.some((item) => item !== page && item.page_id === value)) {
            throw new Error(`interface editor: page id ${JSON.stringify(value)} is already used`);
        }
        if (next.start_page_id === pageId) next.start_page_id = value;
        for (const entry of next.pages.flatMap(walkPage)) {
            if (entry.block.type === 'link' || entry.block.type === 'button') {
                if (entry.block.page_id === pageId) entry.block.page_id = value;
            }
        }
    }
    page[property] = value;
    return next;
}

export function replacePageBlocks(document: FlowUiDocument, pageId: string, blocks: FlowUiBlock[]): FlowUiDocument {
    const next = structuredClone(document);
    const page = findPage(next, pageId);
    page.blocks = structuredClone(blocks);
    return next;
}

// --- История -----------------------------------------------------------------------------

export function createHistory(document: unknown): EditorHistory {
    return { present: requireDocument(document), past: [], future: [], coalesceKey: null };
}

/** Новое состояние; одинаковый ``coalesceKey`` (``block_id:property``) подряд заменяет вершину истории. */
export function commitHistory(history: EditorHistory, document: unknown, coalesceKey: string | null = null): EditorHistory {
    const present = requireDocument(document);
    if (coalesceKey !== null && coalesceKey === history.coalesceKey) {
        return { ...history, present, future: [] };
    }
    const past = [...history.past, history.present].slice(-HISTORY_LIMIT);
    return { present, past, future: [], coalesceKey };
}

export function undoHistory(history: EditorHistory): EditorHistory {
    if (history.past.length === 0) return history;
    const present = history.past[history.past.length - 1];
    if (present === undefined) throw new Error('interface editor: history present missing');
    const past = history.past.slice(0, -1);
    return { present, past, future: [history.present, ...history.future], coalesceKey: null };
}

export function redoHistory(history: EditorHistory): EditorHistory {
    if (history.future.length === 0) return history;
    const present = history.future[0];
    if (present === undefined) throw new Error('interface editor: history present missing');
    return { present, past: [...history.past, history.present], future: history.future.slice(1), coalesceKey: null };
}

// --- Publish gate ------------------------------------------------------------------------

function stringLabels(value: unknown, label: string): string[] {
    if (!Array.isArray(value)) throw new Error(`interface editor: ${label} must be a list`);
    const labels: string[] = [];
    for (const item of value) {
        if (!isRecord(item) || typeof item.label !== 'string') throw new Error(`interface editor: ${label} label must be a string`);
        labels.push(item.label);
    }
    return labels;
}

function templateProperties(entry: CatalogEntry, block: FlowUiBlock): string[] {
    const templates: string[] = [];
    for (const property of entry.properties) {
        const value = block[property.name];
        if (property.kind === 'template' && typeof value === 'string') templates.push(value);
        if (property.kind === 'template_list' && Array.isArray(value)) {
            for (const item of value) {
                if (typeof item !== 'string') throw new Error(`interface editor: ${property.name} template must be a string`);
                templates.push(item);
            }
        }
        if (property.kind === 'options' && Array.isArray(value)) templates.push(...stringLabels(value, property.name));
        if (property.kind === 'table_columns' && Array.isArray(value)) templates.push(...stringLabels(value, property.name));
    }
    if (block.type === 'conversation') {
        const settings = block.settings;
        if (!isRecord(settings)) throw new Error('interface editor: conversation settings required');
        if (typeof settings.greeting === 'string') templates.push(settings.greeting);
        if (typeof settings.placeholder === 'string') templates.push(settings.placeholder);
        const prompts = settings.suggested_prompts;
        if (!Array.isArray(prompts)) throw new Error('interface editor: conversation prompts required');
        for (const prompt of prompts) {
            if (typeof prompt !== 'string') throw new Error('interface editor: conversation prompt must be a string');
            templates.push(prompt);
        }
    }
    return templates;
}

function statePathProperties(entry: CatalogEntry, block: FlowUiBlock): { property: string; path: string }[] {
    const paths: { property: string; path: string }[] = [];
    for (const property of entry.properties) {
        const value = block[property.name];
        if (property.kind === 'state_path' && typeof value === 'string') paths.push({ property: property.name, path: value });
        if (property.kind === 'state_path_list' && Array.isArray(value)) {
            for (const path of value) {
                if (typeof path !== 'string') throw new Error(`interface editor: ${property.name} state path must be a string`);
                paths.push({ property: property.name, path });
            }
        }
    }
    const visibleWhen = block.visible_when;
    if (isRecord(visibleWhen) && typeof visibleWhen.path === 'string') paths.push({ property: 'visible_when', path: visibleWhen.path });
    return paths;
}

/**
 * Проблемы документа: ``{code, severity, pageId, blockId, property, params}``.
 * ``error`` блокирует публикацию, ``warning`` — нет.
 */
export function documentProblems(document: FlowUiDocument, catalog: readonly CatalogEntry[], frozen: ReadonlySet<string>): DocumentProblem[] {
    if (!isFlowUiDocument(document)) throw new Error('interface editor: document required');
    const problems: DocumentProblem[] = [];
    const pageIds = new Set(document.pages.map((page) => page.page_id));
    if (!pageIds.has(document.start_page_id)) problems.push({ code: 'start_page_missing', severity: 'error', pageId: null, blockId: null, property: null, params: {} });
    for (const page of document.pages) {
        const report = (code: string, severity: 'error' | 'warning', blockId: string | null, property: string | null = null, params: Record<string, unknown> = {}) => {
            problems.push({ code, severity, pageId: page.page_id, blockId, property, params });
        };
        if (!ID_PATTERN.test(page.page_id)) report('page_id_invalid', 'error', null, 'page_id', { value: page.page_id });
        const entries = walkPage(page);
        const seen = new Set<string>();
        let hasInputs = false;
        let hasAction = false;
        for (const { block } of entries) {
            const entry = catalog.find((item) => item.type === block.type);
            if (entry === undefined) {
                report('block_type_unknown', 'error', block.block_id, 'type', { value: block.type });
                continue;
            }
            if (!ID_PATTERN.test(block.block_id)) report('block_id_invalid', 'error', block.block_id, 'block_id', { value: block.block_id });
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
            const linkPageId = block.page_id;
            if (block.type === 'link' && linkPageId !== null && typeof linkPageId === 'string' && !pageIds.has(linkPageId)) {
                report('link_page_missing', 'error', block.block_id, 'page_id', { value: linkPageId });
            }
            if (block.type === 'link' && (block.page_id === null) === (block.url === '')) report('link_target', 'error', block.block_id, 'url', {});
            if (block.type === 'button') {
                const buttonHasAction = block.action !== null && block.action !== undefined;
                const buttonPageId = block.page_id;
                const hasPage = typeof buttonPageId === 'string' && buttonPageId !== '';
                const hasUrl = typeof block.url === 'string' && block.url !== '';
                if ((buttonHasAction ? 1 : 0) + (hasPage ? 1 : 0) + (hasUrl ? 1 : 0) !== 1) report('button_target', 'error', block.block_id, 'action', {});
                if (hasPage && !pageIds.has(buttonPageId)) report('link_page_missing', 'error', block.block_id, 'page_id', { value: buttonPageId });
            }
            if (block.type === 'data_table' && (block.rows === null) === (block.file_id === '')) report('data_table_source', 'error', block.block_id, 'rows', {});
            if (block.type === 'file_card' && (block.file === null) === (block.file_id === '')) report('file_card_source', 'error', block.block_id, 'file', {});
            if (block.type === 'columns' && requireColumns(block).reduce((sum, column) => sum + column.width, 0) > 12) report('columns_overflow', 'warning', block.block_id, 'columns', {});
            const height = block.height;
            if (block.type === 'html' && typeof height === 'number' && (height < 24 || height > 4000)) report('html_height', 'error', block.block_id, 'height', {});
        }
        if (hasInputs && !hasAction) report('inputs_without_action', 'error', null, null, {});
    }
    return problems;
}

export function hasBlockingProblems(problems: readonly { severity: string }[]): boolean {
    return problems.some((problem) => problem.severity === 'error');
}

// --- Каталог путей state для подсказок ---------------------------------------------------

/** ``[{path, type, source, protected}]`` из dataflow inspector, тестового state и input-блоков документа. */
export function statePathCatalog(input: { dataflow: unknown; sampleState: unknown; document: FlowUiDocument }): StatePathEntry[] {
    const { dataflow, sampleState, document } = input;
    if (!isFlowUiDocument(document)) throw new Error('interface editor: document required');
    const byPath = new Map<string, StatePathEntry>();
    const add = (path: unknown, type: unknown, source: unknown, isProtected: boolean) => {
        if (typeof path !== 'string' || path === '' || byPath.has(path)) return;
        // DataflowSource — str | list[str]: inspector склеивает источники одного пути в список.
        const sourceLabel = typeof source === 'string'
            ? source
            : Array.isArray(source) && source.length > 0 && source.every((item) => typeof item === 'string')
                ? source.join(', ')
                : null;
        if (typeof type !== 'string' || sourceLabel === null) throw new Error('interface editor: state path descriptor required');
        byPath.set(path, { path, type, source: sourceLabel, protected: isProtected });
    };
    if (isRecord(dataflow)) {
        const variables = dataflow.variables;
        if (Array.isArray(variables)) {
            for (const descriptor of variables) {
                if (!isRecord(descriptor)) throw new Error('interface editor: state path descriptor required');
                add(descriptor.path, descriptor.type, descriptor.source, descriptor.protected === true);
            }
        }
        const nodes = dataflow.nodes;
        if (isRecord(nodes)) {
            for (const node of Object.values(nodes)) {
                if (!isRecord(node) || !Array.isArray(node.output_state) || !Array.isArray(node.incoming_state)) {
                    throw new Error('interface editor: node state descriptors required');
                }
                for (const descriptor of [...node.output_state, ...node.incoming_state]) {
                    if (!isRecord(descriptor)) throw new Error('interface editor: state path descriptor required');
                    add(descriptor.path, descriptor.type, descriptor.source, descriptor.protected === true);
                }
            }
        }
    }
    if (isRecord(sampleState)) {
        for (const [key, value] of Object.entries(sampleState)) {
            const type = Array.isArray(value) ? 'list' : value === null ? 'null' : typeof value;
            add(key, type, 'preview_state', false);
        }
    }
    for (const page of document.pages) {
        for (const { block } of walkPage(page)) {
            if (INPUT_BLOCK_TYPES.has(block.type) && typeof block.field === 'string') add(block.field, 'string', 'interface', false);
            if (block.type === 'html' && typeof block.field === 'string') add(block.field, 'any', 'interface', false);
        }
    }
    return [...byPath.values()].sort((a, b) => a.path.localeCompare(b.path));
}
