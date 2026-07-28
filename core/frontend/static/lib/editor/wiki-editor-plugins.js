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
export function buildInputRules(pm, schema) {
    const rules = [];

    rules.push(
        pm.textblockTypeInputRule(/^(#{1,6})\s$/, schema.nodes.heading, (match) => ({
            level: match[1].length,
        })),
    );
    rules.push(pm.textblockTypeInputRule(/^```([a-zA-Z0-9+-]*)\s$/, schema.nodes.code_block, (match) => ({
        language: match[1] || '',
    })));
    rules.push(pm.wrappingInputRule(/^\s*>\s$/, schema.nodes.blockquote));
    rules.push(pm.wrappingInputRule(/^\s*([-+*])\s$/, schema.nodes.bullet_list));
    rules.push(
        pm.wrappingInputRule(
            /^(\d+)\.\s$/,
            schema.nodes.ordered_list,
            (match) => ({ start: Number(match[1]) }),
            (match, node) => node.childCount + node.attrs.start === Number(match[1]),
        ),
    );

    // `---` на пустой строке — разделитель. InputRule нужен вручную:
    // horizontal_rule не текстовый блок и не обёртка.
    rules.push(
        new pm.InputRule(/^(?:---|___|\*\*\*)$/, (state, match, start, end) => {
            const tr = state.tr.replaceRangeWith(start, end, schema.nodes.horizontal_rule.create());
            return tr;
        }),
    );

    // `$$` — блок формулы: атомарный узел, поэтому тоже вручную.
    rules.push(
        new pm.InputRule(/^\$\$\s$/, (state, match, start, end) => (
            state.tr.replaceRangeWith(start, end, schema.nodes.math_block.create({ formula: '' }))
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
export function buildKeymap(pm, schema, handlers = {}) {
    const keys = {
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
        'Shift-Enter': pm.chainCommands(pm.exitCode, (state, dispatch) => {
            if (dispatch) {
                dispatch(state.tr.replaceSelectionWith(schema.nodes.hard_break.create()).scrollIntoView());
            }
            return true;
        }),
        Enter: pm.chainCommands(
            pm.splitListItem(schema.nodes.task_item),
            pm.splitListItem(schema.nodes.list_item),
        ),
        Tab: pm.chainCommands(
            pm.sinkListItem(schema.nodes.task_item),
            pm.sinkListItem(schema.nodes.list_item),
        ),
        'Shift-Tab': pm.chainCommands(
            pm.liftListItem(schema.nodes.task_item),
            pm.liftListItem(schema.nodes.list_item),
        ),
    };

    for (const level of [1, 2, 3, 4, 5, 6]) {
        keys[`Mod-Alt-${level}`] = pm.setBlockType(schema.nodes.heading, { level });
    }

    // Обычная вставка кладёт markdown как текст; эта — разбирает его в блоки.
    if (typeof handlers.onPasteMarkdown === 'function') {
        keys['Mod-Shift-v'] = () => {
            handlers.onPasteMarkdown();
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
export function buildBlockCommands(pm, schema) {
    const setHeading = (level) => pm.setBlockType(schema.nodes.heading, { level });

    return {
        paragraph: pm.setBlockType(schema.nodes.paragraph),
        heading_1: setHeading(1),
        heading_2: setHeading(2),
        heading_3: setHeading(3),
        bullet_list: pm.wrapInList(schema.nodes.bullet_list),
        ordered_list: pm.wrapInList(schema.nodes.ordered_list),
        task_list: pm.wrapInList(schema.nodes.task_list),
        blockquote: pm.wrapIn(schema.nodes.blockquote),
        code_block: pm.setBlockType(schema.nodes.code_block),
        callout: pm.wrapIn(schema.nodes.callout, { tone: 'info', icon: '' }),
        callout_info: pm.wrapIn(schema.nodes.callout, { tone: 'info', icon: '' }),
        callout_success: pm.wrapIn(schema.nodes.callout, { tone: 'success', icon: '' }),
        callout_warning: pm.wrapIn(schema.nodes.callout, { tone: 'warning', icon: '' }),
        callout_danger: pm.wrapIn(schema.nodes.callout, { tone: 'danger', icon: '' }),
        toggle: (state, dispatch) => {
            const { toggle, toggle_summary: summary, paragraph } = schema.nodes;
            const node = toggle.create(null, [
                summary.create(null, schema.text('Заголовок блока')),
                paragraph.create(),
            ]);
            if (dispatch) dispatch(state.tr.replaceSelectionWith(node).scrollIntoView());
            return true;
        },
        horizontal_rule: (state, dispatch) => {
            if (dispatch) {
                dispatch(state.tr.replaceSelectionWith(schema.nodes.horizontal_rule.create()).scrollIntoView());
            }
            return true;
        },
        math_block: (state, dispatch) => {
            if (dispatch) {
                dispatch(
                    state.tr
                        .replaceSelectionWith(schema.nodes.math_block.create({ formula: '' }))
                        .scrollIntoView(),
                );
            }
            return true;
        },
        footnote: (state, dispatch) => {
            // Сноска это пара: ссылка в тексте и определение в конце документа.
            // Метка выводится из числа уже существующих определений.
            const { footnote_reference: reference, footnote_definition: definition, paragraph } = schema.nodes;
            let used = 0;
            state.doc.descendants((node) => {
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
        table: (state, dispatch) => {
            const { table, table_row: row, table_header: header, table_cell: cell, paragraph } = schema.nodes;
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
export function insertMentionCommand(schema, mention) {
    return (state, dispatch) => {
        const node = schema.nodes.platform_mention.create({
            mention_kind: mention.mentionKind,
            target_id: mention.targetId,
            label: mention.label || '',
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
export function insertPlatformFileCommand(schema, file) {
    return (state, dispatch) => {
        const node = schema.nodes.platform_file.create({
            file_id: file.fileId,
            original_name: file.originalName || '',
            content_type: file.contentType || '',
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
export function insertImageCommand(schema, image) {
    return (state, dispatch) => {
        if (typeof image.fileId !== 'string' || image.fileId.length === 0) {
            throw new Error('insertImageCommand: fileId required');
        }
        if (typeof image.src !== 'string' || image.src.length === 0) {
            throw new Error('insertImageCommand: src required');
        }
        const node = schema.nodes.image.create({
            src: image.src,
            alt: image.alt || '',
            title: image.title || '',
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
export function setLinkCommand(schema, href) {
    return (state, dispatch) => {
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
export function setHighlightColorCommand(schema, color) {
    return (state, dispatch) => {
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
