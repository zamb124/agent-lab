/**
 * platform-rich-editor — блочный редактор: ввод, слои, меню блока, таблицы.
 */

import { fixture, html, expect, oneEvent, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-rich-editor.js';

function docWithText(text) {
    return {
        type: 'doc',
        content: [{ type: 'paragraph', content: [{ type: 'text', text }] }],
    };
}

async function mountEditor(props = {}) {
    const el = await fixture(html`
        <platform-rich-editor
            .value=${props.value ?? { type: 'doc', content: [{ type: 'paragraph' }] }}
            ?readonly=${props.readonly === true}
            .mentionProvider=${props.mentionProvider ?? null}
        ></platform-rich-editor>
    `);
    // Схема и бандл ProseMirror грузятся динамически.
    for (let attempt = 0; attempt < 60 && el._view === null; attempt += 1) {
        await aTimeout(20);
    }
    await elementUpdated(el);
    return el;
}

/** Поставить курсор в первую ячейку таблицы документа. */
function selectFirstTableCell(el) {
    const { state } = el._view;
    let cellPos = -1;
    state.doc.descendants((node, pos) => {
        if (cellPos !== -1) return false;
        if (node.type.name === 'table_header' || node.type.name === 'table_cell') {
            cellPos = pos;
            return false;
        }
        return true;
    });
    if (cellPos === -1) {
        throw new Error('в документе нет таблицы');
    }
    const selection = el._pm.TextSelection.create(state.doc, cellPos + 2);
    el._view.dispatch(state.tr.setSelection(selection));
}

function countTableRows(doc) {
    return JSON.stringify(doc).split('"table_row"').length - 1;
}

/** Поставить курсор в конец документа и вернуть состояние. */
function focusEnd(el) {
    const { state } = el._view;
    const selection = el._pm.TextSelection.create(state.doc, state.doc.content.size - 1);
    el._view.dispatch(state.tr.setSelection(selection));
}

describe('platform-rich-editor', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('поднимает редактор и показывает документ', async () => {
        const el = await mountEditor({ value: docWithText('Привет') });

        expect(el._view).to.not.equal(null);
        expect(el.querySelector('.pm-editor').textContent).to.contain('Привет');
    });

    it('правка документа эмитит change с новым содержимым', async () => {
        const el = await mountEditor({ value: docWithText('Текст') });

        const changed = oneEvent(el, 'change');
        const { state } = el._view;
        el._view.dispatch(state.tr.insertText('!', state.doc.content.size - 1));
        const event = await changed;

        expect(JSON.stringify(event.detail.content)).to.contain('Текст!');
    });

    it('внешнее значение заменяет содержимое', async () => {
        const el = await mountEditor({ value: docWithText('Старое') });

        el.value = docWithText('Новое содержимое');
        await elementUpdated(el);

        expect(el.querySelector('.pm-editor').textContent).to.contain('Новое содержимое');
    });

    it('в режиме чтения редактор не редактируется', async () => {
        const el = await mountEditor({ value: docWithText('Только чтение'), readonly: true });

        expect(el._view.editable).to.be.false;
    });

    it('выделение открывает панель форматирования с якорем по выделению', async () => {
        const el = await mountEditor({ value: docWithText('Выделенный текст') });

        const { state } = el._view;
        const selection = el._pm.TextSelection.create(state.doc, 1, 10);
        el._view.dispatch(state.tr.setSelection(selection));
        await elementUpdated(el);

        expect(el.querySelector('.pm-bubble')).to.exist;
        expect(el._bubbleAnchor).to.not.equal(null);
        expect(el._bubbleAnchor.width).to.be.greaterThan(0);
    });

    it('панель форматирования переключает начертание', async () => {
        const el = await mountEditor({ value: docWithText('Жирный') });
        const { state } = el._view;
        el._view.dispatch(state.tr.setSelection(el._pm.TextSelection.create(state.doc, 1, 7)));
        await elementUpdated(el);

        el.querySelector('.pm-bubble-btn').click();
        await elementUpdated(el);

        expect(JSON.stringify(el.value)).to.contain('strong');
    });

    it('снятие выделения убирает панель', async () => {
        const el = await mountEditor({ value: docWithText('Текст') });
        const { state } = el._view;
        el._view.dispatch(state.tr.setSelection(el._pm.TextSelection.create(state.doc, 1, 5)));
        await elementUpdated(el);
        expect(el.querySelector('.pm-bubble')).to.exist;

        el._view.dispatch(el._view.state.tr.setSelection(
            el._pm.TextSelection.create(el._view.state.doc, 1),
        ));
        await elementUpdated(el);

        expect(el.querySelector('.pm-bubble')).to.be.null;
    });

    it('меню команд открывается по слэшу и позиционируется', async () => {
        const el = await mountEditor();
        focusEnd(el);

        el._slashOpen = true;
        el._slashAnchor = el._selectionAnchor(el._view.state);
        await elementUpdated(el);

        expect(el.querySelector('.pm-slash')).to.exist;
        expect(el._slashAnchor).to.not.equal(null);
    });

    it('команда из меню превращает блок в заголовок', async () => {
        const el = await mountEditor({ value: docWithText('Заголовок раздела') });
        focusEnd(el);
        el._slashOpen = true;
        await elementUpdated(el);

        el.querySelector('[data-slash-command="heading_1"]').click();
        await elementUpdated(el);

        expect(el.value.content[0].type).to.equal('heading');
        expect(el.querySelector('.pm-slash')).to.be.null;
    });

    it('меню команд фильтруется по набранному тексту', async () => {
        const el = await mountEditor();
        el._slashOpen = true;
        el._slashQuery = 'table';
        await elementUpdated(el);

        const commands = Array.from(el.querySelectorAll('[data-slash-command]'))
            .map((node) => node.dataset.slashCommand);
        expect(commands).to.deep.equal(['table']);
    });

    it('меню упоминаний показывает результаты провайдера', async () => {
        const el = await mountEditor({
            mentionProvider: async () => [
                { id: 'u1', kind: 'user', label: 'Иван Петров' },
                { id: 'p1', kind: 'wiki_page', label: 'Онбординг' },
            ],
        });

        el._mentionOpen = true;
        await el._loadMentions('');
        await elementUpdated(el);

        const items = Array.from(el.querySelectorAll('[data-mention-id]'));
        expect(items.length).to.equal(2);
        expect(items[0].textContent).to.contain('Иван Петров');
    });

    it('выбор упоминания вставляет узел в документ', async () => {
        const el = await mountEditor({
            value: docWithText('Спросить у '),
            mentionProvider: async () => [{ id: 'u1', kind: 'user', label: 'Иван Петров' }],
        });
        focusEnd(el);
        el._mentionOpen = true;
        await el._loadMentions('');
        await elementUpdated(el);

        el.querySelector('[data-mention-id="u1"]').click();
        await elementUpdated(el);

        expect(JSON.stringify(el.value)).to.contain('mention');
        expect(el._mentionOpen).to.be.false;
    });

    it('поздний ответ провайдера упоминаний не затирает актуальный', async () => {
        let call = 0;
        const el = await mountEditor({
            mentionProvider: async (query) => {
                call += 1;
                if (call === 1) {
                    await aTimeout(80);
                    return [{ id: 'stale', kind: 'user', label: 'Устаревший' }];
                }
                return [{ id: 'fresh', kind: 'user', label: `Актуальный ${query}` }];
            },
        });
        el._mentionOpen = true;

        const slow = el._loadMentions('и');
        const fast = el._loadMentions('ив');
        await Promise.all([slow, fast]);
        await elementUpdated(el);

        expect(el._mentionItems.map((item) => item.id)).to.deep.equal(['fresh']);
    });

    it('ручка блока появляется при наведении и открывает меню', async () => {
        const el = await mountEditor({ value: docWithText('Блок текста') });

        el._handleTop = 10;
        el._handleBlockPos = 0;
        await elementUpdated(el);
        const handle = el.querySelector('.pm-block-handle-btn');
        expect(handle).to.exist;

        handle.click();
        await elementUpdated(el);

        expect(el.querySelector('platform-menu')).to.exist;
    });

    it('меню блока удаляет блок', async () => {
        const el = await mountEditor({
            value: {
                type: 'doc',
                content: [
                    { type: 'paragraph', content: [{ type: 'text', text: 'Первый' }] },
                    { type: 'paragraph', content: [{ type: 'text', text: 'Второй' }] },
                ],
            },
        });
        el._handleBlockPos = 0;

        el._onBlockMenuSelect({ detail: { id: 'delete' } });
        await elementUpdated(el);

        expect(el.querySelector('.pm-editor').textContent).to.not.contain('Первый');
        expect(el.querySelector('.pm-editor').textContent).to.contain('Второй');
    });

    it('меню блока дублирует блок', async () => {
        const el = await mountEditor({ value: docWithText('Копируемый') });
        el._handleBlockPos = 0;

        el._onBlockMenuSelect({ detail: { id: 'duplicate' } });
        await elementUpdated(el);

        expect(el.value.content.length).to.equal(2);
    });

    it('меню блока превращает абзац в заголовок', async () => {
        const el = await mountEditor({ value: docWithText('Станет заголовком') });
        el._handleBlockPos = 0;

        el._onBlockMenuSelect({ detail: { id: 'turn_heading_2' } });
        await elementUpdated(el);

        expect(el.value.content[0].type).to.equal('heading');
        expect(el.value.content[0].attrs.level).to.equal(2);
    });

    it('неизвестное действие меню блока падает, а не молчит', async () => {
        const el = await mountEditor({ value: docWithText('Текст') });
        el._handleBlockPos = 0;

        expect(() => el._onBlockMenuSelect({ detail: { id: 'turn_unknown' } })).to.throw();
    });

    it('внутри таблицы появляются контролы строк и колонок', async () => {
        const el = await mountEditor();
        focusEnd(el);
        el._runSlashCommand('table');
        await elementUpdated(el);

        selectFirstTableCell(el);
        await elementUpdated(el);

        expect(el._inTable).to.be.true;
        expect(el.querySelector('[data-table-action="addRowAfter"]')).to.exist;
    });

    it('контрол таблицы добавляет строку', async () => {
        const el = await mountEditor();
        focusEnd(el);
        el._runSlashCommand('table');
        await elementUpdated(el);
        const rowsBefore = countTableRows(el.value);

        selectFirstTableCell(el);
        await elementUpdated(el);
        el._runTableCommand('addRowAfter');
        await elementUpdated(el);

        expect(countTableRows(el.value)).to.equal(rowsBefore + 1);
    });

    it('getOutline возвращает заголовки по порядку', async () => {
        const el = await mountEditor({
            value: {
                type: 'doc',
                content: [
                    { type: 'heading', attrs: { level: 1 }, content: [{ type: 'text', text: 'Первый' }] },
                    { type: 'paragraph', content: [{ type: 'text', text: 'текст' }] },
                    { type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: 'Второй' }] },
                ],
            },
        });

        const outline = el.getOutline();
        expect(outline.map((item) => item.text)).to.deep.equal(['Первый', 'Второй']);
        expect(outline.map((item) => item.level)).to.deep.equal([1, 2]);
    });
});
