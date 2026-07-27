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
        pm.textblockTypeInputRule(/^(#{1,4})\s$/, schema.nodes.heading, (match) => ({
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

    return pm.inputRules({ rules });
}

/**
 * @param {object} pm
 * @param {object} schema
 * @param {{onSlash?: () => void}} handlers
 * @returns {object} плагин keymap
 */
export function buildKeymap(pm, schema, handlers = {}) {
    const keys = {
        'Mod-b': pm.toggleMark(schema.marks.strong),
        'Mod-i': pm.toggleMark(schema.marks.em),
        'Mod-e': pm.toggleMark(schema.marks.code),
        'Mod-Shift-x': pm.toggleMark(schema.marks.strike),
        'Mod-Shift-h': pm.toggleMark(schema.marks.highlight),
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

    for (const level of [1, 2, 3, 4]) {
        keys[`Mod-Alt-${level}`] = pm.setBlockType(schema.nodes.heading, { level });
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

export const SLASH_MENU_ITEMS = Object.freeze([
    { command: 'heading_1', icon: 'type', labelKey: 'editor.block.heading_1' },
    { command: 'heading_2', icon: 'type', labelKey: 'editor.block.heading_2' },
    { command: 'heading_3', icon: 'type', labelKey: 'editor.block.heading_3' },
    { command: 'bullet_list', icon: 'list', labelKey: 'editor.block.bullet_list' },
    { command: 'ordered_list', icon: 'list', labelKey: 'editor.block.ordered_list' },
    { command: 'task_list', icon: 'check', labelKey: 'editor.block.task_list' },
    { command: 'toggle', icon: 'chevron-right', labelKey: 'editor.block.toggle' },
    { command: 'callout', icon: 'info', labelKey: 'editor.block.callout' },
    { command: 'blockquote', icon: 'quote', labelKey: 'editor.block.blockquote' },
    { command: 'code_block', icon: 'code', labelKey: 'editor.block.code_block' },
    { command: 'table', icon: 'table', labelKey: 'editor.block.table' },
    { command: 'horizontal_rule', icon: 'minus', labelKey: 'editor.block.horizontal_rule' },
]);
