import type {
    PmCommand,
    PmMarkTypeLike,
    PmNodeTypeLike,
    PmNodeLike,
    PmPluginApiLike,
    PmSchemaLike,
    PmStateLike,
    PmDispatch,
} from './pm-types.js';
import { attrString } from './wiki-schema-builder.js';

type RxMatch = RegExpMatchArray & Record<number, string>;

function nt(schema: PmSchemaLike, name: string): PmNodeTypeLike {
    const nodeType = schema.nodes[name];
    if (!nodeType) {
        throw new Error(`wiki-editor-plugins: schema node ${name} missing`);
    }
    return nodeType;
}

/**
 * Поведение редактора wiki: горячие клавиши, markdown-правила ввода, команды блоков.
 *
 * Всё, что превращает набранный текст в блок, живёт здесь: `# ` в заголовок,
 * `- ` в список, `> ` в цитату. Так печать остаётся привычной для тех, кто
 * пишет markdown, а результат сразу становится структурой документа.
 */

/**
 * @param {object} pm — модуль prosemirror-bundle
 * @param {object} schema
 * @returns {object[]} плагины input rules
 */
export function buildInputRules(pm: PmPluginApiLike, schema: PmSchemaLike): unknown {
    const rules: unknown[] = [];

    rules.push(
        pm.textblockTypeInputRule(/^(#{1,6})\s$/, nt(schema, 'heading'), (match: RxMatch) => ({
            level: String(match[1]).length,
        })),
    );
    rules.push(pm.textblockTypeInputRule(/^```([a-zA-Z0-9+-]*)\s$/, nt(schema, 'code_block'), (match: RxMatch) => ({
        language: match[1],
    })));
    rules.push(pm.wrappingInputRule(/^\s*>\s$/, nt(schema, 'blockquote')));
    rules.push(pm.wrappingInputRule(/^\s*([-+*])\s$/, nt(schema, 'bullet_list')));
    rules.push(
        pm.wrappingInputRule(
            /^(\d+)\.\s$/,
            nt(schema, 'ordered_list'),
            (match: RxMatch) => ({ start: Number(match[1]) }),
            (match: RxMatch, node: PmNodeLike) => node.childCount + Number(node.attrs.start) === Number(match[1]),
        ),
    );

    // `---` на пустой строке — разделитель. InputRule нужен вручную:
    // horizontal_rule не текстовый блок и не обёртка.
    rules.push(
        new pm.InputRule(/^(?:---|___|\*\*\*)$/, (state: PmStateLike, _match: RegExpMatchArray, start: number, end: number) => {
            return state.tr.replaceRangeWith(start, end, nt(schema, 'horizontal_rule').create());
        }),
    );

    // `$$` — блок формулы: атомарный узел, поэтому тоже вручную.
    rules.push(
        new pm.InputRule(/^\$\$\s$/, (state: PmStateLike, _match: RegExpMatchArray, start: number, end: number) => (
            state.tr.replaceRangeWith(start, end, nt(schema, 'math_block').create({ formula: '' }))
        )),
    );

    return pm.inputRules({ rules });
}

/**
 * @param {object} pm
 * @param {object} schema
 * @param {{onSlash?: () => void, onPasteMarkdown?: () => void}} handlers
 * @returns {object} плагин keymap
 */
export interface KeymapHandlers {
    onLink?: () => void;
    onSlash?: () => void;
    onPasteMarkdown?: () => void;
}

export function buildKeymap(pm: PmPluginApiLike, schema: PmSchemaLike, handlers: KeymapHandlers = {}): unknown {
    const keys: Record<string, PmCommand> = {
        'Mod-b': pm.toggleMark(schema.marks.strong),
        'Mod-i': pm.toggleMark(schema.marks.em),
        'Mod-e': pm.toggleMark(schema.marks.code),
        'Mod-Shift-x': pm.toggleMark(schema.marks.strike),
        'Mod-Shift-h': pm.toggleMark(schema.marks.highlight),
        'Mod-k': () => {
            if (typeof handlers.onLink !== 'function') {
                return false;
            }
            handlers.onLink();
            return true;
        },
        'Mod-z': pm.undo,
        'Mod-y': pm.redo,
        'Mod-Shift-z': pm.redo,
        'Shift-Enter': pm.chainCommands(pm.exitCode, (state: PmStateLike, dispatch?: PmDispatch) => {
            if (dispatch) {
                dispatch(state.tr.replaceSelectionWith(nt(schema, 'hard_break').create()).scrollIntoView());
            }
            return true;
        }),
        Enter: pm.chainCommands(
            pm.splitListItem(nt(schema, 'task_item')),
            pm.splitListItem(nt(schema, 'list_item')),
        ),
        Tab: pm.chainCommands(
            pm.sinkListItem(nt(schema, 'task_item')),
            pm.sinkListItem(nt(schema, 'list_item')),
        ),
        'Shift-Tab': pm.chainCommands(
            pm.liftListItem(nt(schema, 'task_item')),
            pm.liftListItem(nt(schema, 'list_item')),
        ),
    };

    for (const level of [1, 2, 3, 4, 5, 6]) {
        keys[`Mod-Alt-${level}`] = pm.setBlockType(nt(schema, 'heading'), { level });
    }

    // Обычная вставка кладёт markdown как текст; эта — разбирает его в блоки.
    if (typeof handlers.onPasteMarkdown === 'function') {
        keys['Mod-Shift-v'] = () => {
            handlers.onPasteMarkdown?.();
            return true;
        };
    }

    return pm.keymap(keys);
}

/**
 * Команды, доступные из slash-меню и панели форматирования.
 * @param {object} pm
 * @param {object} schema
 * @returns {Record<string, (state: object, dispatch: Function) => boolean>}
 */
export function buildBlockCommands(pm: PmPluginApiLike, schema: PmSchemaLike): Record<string, PmCommand> {
    const setHeading = (level: number): PmCommand => pm.setBlockType(nt(schema, 'heading'), { level });

    return {
        paragraph: pm.setBlockType(nt(schema, 'paragraph')),
        heading_1: setHeading(1),
        heading_2: setHeading(2),
        heading_3: setHeading(3),
        bullet_list: pm.wrapInList(nt(schema, 'bullet_list')),
        ordered_list: pm.wrapInList(nt(schema, 'ordered_list')),
        task_list: pm.wrapInList(nt(schema, 'task_list')),
        blockquote: pm.wrapIn(nt(schema, 'blockquote')),
        code_block: pm.setBlockType(nt(schema, 'code_block')),
        callout: pm.wrapIn(nt(schema, 'callout'), { tone: 'info', icon: '' }),
        callout_info: pm.wrapIn(nt(schema, 'callout'), { tone: 'info', icon: '' }),
        callout_success: pm.wrapIn(nt(schema, 'callout'), { tone: 'success', icon: '' }),
        callout_warning: pm.wrapIn(nt(schema, 'callout'), { tone: 'warning', icon: '' }),
        callout_danger: pm.wrapIn(nt(schema, 'callout'), { tone: 'danger', icon: '' }),
        toggle: (state: PmStateLike, dispatch?: PmDispatch) => {
            const toggle = nt(schema, 'toggle');
            const summary = nt(schema, 'toggle_summary');
            const paragraph = nt(schema, 'paragraph');
            const node = toggle.create(null, [
                summary.create(null, schema.text('Заголовок блока')),
                paragraph.create(),
            ]);
            if (dispatch) dispatch(state.tr.replaceSelectionWith(node).scrollIntoView());
            return true;
        },
        horizontal_rule: (state: PmStateLike, dispatch?: PmDispatch) => {
            if (dispatch) {
                dispatch(state.tr.replaceSelectionWith(nt(schema, 'horizontal_rule').create()).scrollIntoView());
            }
            return true;
        },
        math_block: (state: PmStateLike, dispatch?: PmDispatch) => {
            if (dispatch) {
                dispatch(
                    state.tr
                        .replaceSelectionWith(nt(schema, 'math_block').create({ formula: '' }))
                        .scrollIntoView(),
                );
            }
            return true;
        },
        footnote: (state: PmStateLike, dispatch?: PmDispatch) => {
            // Сноска это пара: ссылка в тексте и определение в конце документа.
            // Метка выводится из числа уже существующих определений.
            const reference = nt(schema, 'footnote_reference');
            const definition = nt(schema, 'footnote_definition');
            const paragraph = nt(schema, 'paragraph');
            let used = 0;
            state.doc.descendants((node: PmNodeLike) => {
                if (node.type === definition) used += 1;
                return true;
            });
            const label = String(used + 1);
            if (dispatch) {
                const tr = state.tr.replaceSelectionWith(reference.create({ label }), false);
                tr.insert(
                    tr.doc.content.size,
                    definition.create({ label }, paragraph.create()),
                );
                dispatch(tr.scrollIntoView());
            }
            return true;
        },
        table: (state: PmStateLike, dispatch?: PmDispatch) => {
            const table = nt(schema, 'table');
            const row = nt(schema, 'table_row');
            const header = nt(schema, 'table_header');
            const cell = nt(schema, 'table_cell');
            const paragraph = nt(schema, 'paragraph');
            const headerRow = row.create(null, [
                header.create(null, paragraph.create()),
                header.create(null, paragraph.create()),
            ]);
            const bodyRow = row.create(null, [
                cell.create(null, paragraph.create()),
                cell.create(null, paragraph.create()),
            ]);
            if (dispatch) {
                dispatch(state.tr.replaceSelectionWith(table.create(null, [headerRow, bodyRow])).scrollIntoView());
            }
            return true;
        },
    };
}

/**
 * Вставка узла-упоминания.
 * @param {object} schema
 * @param {{mentionKind: string, targetId: string, label: string}} mention
 * @returns {(state: object, dispatch: Function) => boolean}
 */
export interface MentionPayload {
    mentionKind: string;
    targetId: string;
    label?: string;
}

export function insertMentionCommand(schema: PmSchemaLike, mention: MentionPayload): PmCommand {
    return (state: PmStateLike, dispatch?: PmDispatch) => {
        const node = nt(schema, 'platform_mention').create({
            mention_kind: mention.mentionKind,
            target_id: mention.targetId,
            label: attrString(mention.label),
        });
        if (dispatch) dispatch(state.tr.replaceSelectionWith(node, false).scrollIntoView());
        return true;
    };
}

/**
 * Вставка карточки документа платформы.
 * @param {object} schema
 * @param {{fileId: string, originalName?: string, contentType?: string}} file
 * @returns {(state: object, dispatch: Function) => boolean}
 */
export interface PlatformFilePayload {
    fileId: string;
    originalName?: string;
    contentType?: string;
}

export function insertPlatformFileCommand(schema: PmSchemaLike, file: PlatformFilePayload): PmCommand {
    return (state: PmStateLike, dispatch?: PmDispatch) => {
        const node = nt(schema, 'platform_file').create({
            file_id: file.fileId,
            original_name: attrString(file.originalName),
            content_type: attrString(file.contentType),
        });
        if (dispatch) dispatch(state.tr.replaceSelectionWith(node).scrollIntoView());
        return true;
    };
}

/**
 * Вставка картинки: `src` — платформенный download URL, `file_id` — связь с Files.
 * @param {object} schema
 * @param {{fileId: string, src: string, alt?: string, title?: string}} image
 * @returns {(state: object, dispatch: Function) => boolean}
 */
export interface ImagePayload {
    fileId: string;
    src: string;
    alt?: string;
    title?: string;
}

export function insertImageCommand(schema: PmSchemaLike, image: ImagePayload): PmCommand {
    return (state: PmStateLike, dispatch?: PmDispatch) => {
        if (typeof image.fileId !== 'string' || image.fileId.length === 0) {
            throw new Error('insertImageCommand: fileId required');
        }
        if (typeof image.src !== 'string' || image.src.length === 0) {
            throw new Error('insertImageCommand: src required');
        }
        const node = nt(schema, 'image').create({
            src: image.src,
            alt: attrString(image.alt),
            title: attrString(image.title),
            file_id: image.fileId,
        });
        if (dispatch) dispatch(state.tr.replaceSelectionWith(node).scrollIntoView());
        return true;
    };
}

/**
 * Проставить или снять ссылку на выделении.
 * @param {object} schema
 * @param {string} href
 * @returns {(state: object, dispatch: Function) => boolean}
 */
export function setLinkCommand(schema: PmSchemaLike, href: string): PmCommand {
    return (state: PmStateLike, dispatch?: PmDispatch) => {
        const markType = schema.marks.link;
        if (!markType) {
            throw new Error('setLinkCommand: link mark missing from schema');
        }
        const { from, to, empty } = state.selection;
        if (empty) {
            return false;
        }
        if (href === '') {
            if (dispatch) {
                dispatch(state.tr.removeMark(from, to, markType));
            }
            return true;
        }
        if (dispatch) {
            dispatch(state.tr.addMark(from, to, markType.create({ href, title: '' })));
        }
        return true;
    };
}

/**
 * Выделение цветом: mark highlight с attrs.color.
 * @param {object} schema
 * @param {string} color
 * @returns {(state: object, dispatch: Function) => boolean}
 */
export function setHighlightColorCommand(schema: PmSchemaLike, color: string): PmCommand {
    return (state: PmStateLike, dispatch?: PmDispatch) => {
        const markType = schema.marks.highlight;
        if (!markType) {
            throw new Error('setHighlightColorCommand: highlight mark missing from schema');
        }
        const { from, to, empty } = state.selection;
        if (empty) {
            return false;
        }
        if (dispatch) {
            const tr = state.tr.removeMark(from, to, markType);
            tr.addMark(from, to, markType.create({ color }));
            dispatch(tr);
        }
        return true;
    };
}

export const HIGHLIGHT_COLORS = Object.freeze([
    'yellow',
    'green',
    'blue',
    'pink',
    'orange',
]);

export const SLASH_MENU_ITEMS = Object.freeze([
    { command: 'heading_1', icon: 'heading-1', labelKey: 'editor.block.heading_1' },
    { command: 'heading_2', icon: 'heading-2', labelKey: 'editor.block.heading_2' },
    { command: 'heading_3', icon: 'heading-3', labelKey: 'editor.block.heading_3' },
    { command: 'bullet_list', icon: 'list', labelKey: 'editor.block.bullet_list' },
    { command: 'ordered_list', icon: 'list', labelKey: 'editor.block.ordered_list' },
    { command: 'task_list', icon: 'check', labelKey: 'editor.block.task_list' },
    { command: 'toggle', icon: 'chevron-right', labelKey: 'editor.block.toggle' },
    { command: 'callout_info', icon: 'info', labelKey: 'editor.block.callout_info' },
    { command: 'callout_success', icon: 'check', labelKey: 'editor.block.callout_success' },
    { command: 'callout_warning', icon: 'alert-triangle', labelKey: 'editor.block.callout_warning' },
    { command: 'callout_danger', icon: 'alert-circle', labelKey: 'editor.block.callout_danger' },
    { command: 'blockquote', icon: 'quote', labelKey: 'editor.block.blockquote' },
    { command: 'code_block', icon: 'code', labelKey: 'editor.block.code_block' },
    { command: 'image', icon: 'image', labelKey: 'editor.block.image' },
    { command: 'platform_file', icon: 'file', labelKey: 'editor.block.platform_file' },
    { command: 'table', icon: 'table', labelKey: 'editor.block.table' },
    { command: 'math_block', icon: 'code', labelKey: 'editor.block.math_block' },
    { command: 'footnote', icon: 'scroll-text', labelKey: 'editor.block.footnote' },
    { command: 'horizontal_rule', icon: 'minus', labelKey: 'editor.block.horizontal_rule' },
]);
