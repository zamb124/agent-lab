/**
 * platform-tree — раскрытие, выбор, клавиатура, перетаскивание, контекстное меню.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-tree.js';

const NODES = [
    { id: 'root', label: 'База знаний', parent_id: null, icon: 'folder' },
    { id: 'guides', label: 'Инструкции', parent_id: 'root', icon: 'folder' },
    { id: 'onboarding', label: 'Онбординг', parent_id: 'guides' },
    { id: 'specs', label: 'Спецификации', parent_id: 'root' },
    { id: 'archive', label: 'Архив', parent_id: null, count: 12 },
];

async function mountTree(props = {}) {
    const el = await fixture(html`
        <platform-tree
            .nodes=${props.nodes ?? NODES}
            selected-id=${props.selectedId ?? ''}
            ?draggable-nodes=${props.draggable === true}
            .menuItems=${props.menuItems ?? null}
        ></platform-tree>
    `);
    await elementUpdated(el);
    return el;
}

function rows(el) {
    return Array.from(el.shadowRoot.querySelectorAll('.row'));
}

function rowById(el, id) {
    return el.shadowRoot.querySelector(`[data-node-id="${id}"]`);
}

function treeOf(el) {
    return el.shadowRoot.querySelector('[role="tree"]');
}

describe('platform-tree', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('показывает только корневые узлы, пока ничего не раскрыто', async () => {
        const el = await mountTree();

        const labels = rows(el).map((row) => row.querySelector('.label').textContent.trim());
        expect(labels).to.deep.equal(['База знаний', 'Архив']);
    });

    it('раскрытие показывает детей', async () => {
        const el = await mountTree();

        rowById(el, 'root').querySelector('[data-twisty="root"]').click();
        await elementUpdated(el);

        const labels = rows(el).map((row) => row.querySelector('.label').textContent.trim());
        expect(labels).to.deep.equal(['База знаний', 'Инструкции', 'Спецификации', 'Архив']);
    });

    it('повторный клик по шеврону сворачивает узел', async () => {
        const el = await mountTree();
        const twisty = rowById(el, 'root').querySelector('[data-twisty="root"]');

        twisty.click();
        await elementUpdated(el);
        rowById(el, 'root').querySelector('[data-twisty="root"]').click();
        await elementUpdated(el);

        expect(rows(el).length).to.equal(2);
    });

    it('шеврон скрыт у листьев', async () => {
        const el = await mountTree();

        expect(rowById(el, 'archive').querySelector('.twisty').hasAttribute('hidden')).to.be.true;
        expect(rowById(el, 'root').querySelector('.twisty').hasAttribute('hidden')).to.be.false;
    });

    it('раскрытие эмитит tree-toggle', async () => {
        const el = await mountTree();

        const toggled = oneEvent(el, 'tree-toggle');
        rowById(el, 'root').querySelector('[data-twisty="root"]').click();
        const event = await toggled;

        expect(event.detail).to.deep.equal({ id: 'root', expanded: true });
    });

    it('клик по строке эмитит tree-select', async () => {
        const el = await mountTree();

        const selected = oneEvent(el, 'tree-select');
        rowById(el, 'archive').click();
        const event = await selected;

        expect(event.detail.id).to.equal('archive');
        expect(event.detail.node.label).to.equal('Архив');
    });

    it('выбранный узел помечен для доступности', async () => {
        const el = await mountTree({ selectedId: 'archive' });

        expect(rowById(el, 'archive').getAttribute('aria-selected')).to.equal('true');
        expect(rowById(el, 'root').getAttribute('aria-selected')).to.equal('false');
    });

    it('выбранный узел раскрывается вместе с предками', async () => {
        const el = await mountTree({ selectedId: 'onboarding' });

        expect(rowById(el, 'onboarding')).to.exist;
        expect(el.isExpanded('root')).to.be.true;
        expect(el.isExpanded('guides')).to.be.true;
    });

    it('выбранный узел раскрывается, когда дерево пришло позже выбора', async () => {
        const el = await mountTree({ nodes: [], selectedId: 'onboarding' });

        el.nodes = NODES;
        await elementUpdated(el);

        expect(rowById(el, 'onboarding')).to.exist;
    });

    it('свёрнутую вручную ветку выбранного узла не разворачивает обратно', async () => {
        const el = await mountTree({ selectedId: 'onboarding' });

        rowById(el, 'guides').querySelector('[data-twisty="guides"]').click();
        await elementUpdated(el);
        el.nodes = [...NODES];
        await elementUpdated(el);

        expect(el.isExpanded('guides')).to.be.false;
    });

    it('revealNode раскрывает всех предков', async () => {
        const el = await mountTree();

        el.revealNode('onboarding');
        await elementUpdated(el);

        expect(rowById(el, 'onboarding')).to.exist;
        expect(el.isExpanded('root')).to.be.true;
        expect(el.isExpanded('guides')).to.be.true;
    });

    it('уровень вложенности отражён в aria-level', async () => {
        const el = await mountTree();
        el.revealNode('onboarding');
        await elementUpdated(el);

        expect(rowById(el, 'root').getAttribute('aria-level')).to.equal('1');
        expect(rowById(el, 'guides').getAttribute('aria-level')).to.equal('2');
        expect(rowById(el, 'onboarding').getAttribute('aria-level')).to.equal('3');
    });

    it('стрелки вниз и вверх двигают фокус по видимым узлам', async () => {
        const el = await mountTree();
        const tree = treeOf(el);

        tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.row.is-focused').dataset.nodeId).to.equal('root');

        tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.row.is-focused').dataset.nodeId).to.equal('archive');

        tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.row.is-focused').dataset.nodeId).to.equal('root');
    });

    it('стрелка вправо раскрывает узел, затем уходит к первому ребёнку', async () => {
        const el = await mountTree();
        const tree = treeOf(el);
        tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await elementUpdated(el);

        tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
        await elementUpdated(el);
        expect(el.isExpanded('root')).to.be.true;

        tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.row.is-focused').dataset.nodeId).to.equal('guides');
    });

    it('стрелка влево сворачивает узел, затем уходит к родителю', async () => {
        const el = await mountTree();
        el.revealNode('onboarding');
        await elementUpdated(el);
        const tree = treeOf(el);
        rowById(el, 'guides').click();
        await elementUpdated(el);

        tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
        await elementUpdated(el);
        expect(el.isExpanded('guides')).to.be.false;

        tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.row.is-focused').dataset.nodeId).to.equal('root');
    });

    it('Enter выбирает узел под фокусом', async () => {
        const el = await mountTree();
        const tree = treeOf(el);
        tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await elementUpdated(el);

        const selected = oneEvent(el, 'tree-select');
        tree.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        const event = await selected;

        expect(event.detail.id).to.equal('root');
    });

    it('без draggable-nodes узлы не перетаскиваются', async () => {
        const el = await mountTree();

        expect(rowById(el, 'root').getAttribute('draggable')).to.equal('false');
    });

    it('перетаскивание в середину строки кладёт узел внутрь', async () => {
        const el = await mountTree({ draggable: true });
        const source = rowById(el, 'archive');
        const target = rowById(el, 'root');

        source.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: new DataTransfer() }));
        await elementUpdated(el);
        const rect = target.getBoundingClientRect();
        target.dispatchEvent(new DragEvent('dragover', {
            bubbles: true,
            cancelable: true,
            dataTransfer: new DataTransfer(),
            clientY: rect.top + rect.height / 2,
        }));
        await elementUpdated(el);
        expect(target.classList.contains('drop-inside')).to.be.true;

        const moved = oneEvent(el, 'tree-move');
        target.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }));
        const event = await moved;

        expect(event.detail.id).to.equal('archive');
        expect(event.detail.position).to.equal('inside');
        expect(event.detail.parent_id).to.equal('root');
        // Иначе перенесённый узел пропадает внутри свёрнутого родителя.
        expect(el.isExpanded('root')).to.be.true;
    });

    it('перетаскивание к верхней кромке вставляет перед узлом', async () => {
        const el = await mountTree({ draggable: true });
        const source = rowById(el, 'archive');
        const target = rowById(el, 'root');

        source.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: new DataTransfer() }));
        await elementUpdated(el);
        const rect = target.getBoundingClientRect();
        target.dispatchEvent(new DragEvent('dragover', {
            bubbles: true,
            cancelable: true,
            dataTransfer: new DataTransfer(),
            clientY: rect.top + 1,
        }));
        await elementUpdated(el);
        expect(target.classList.contains('drop-before')).to.be.true;

        const moved = oneEvent(el, 'tree-move');
        target.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: new DataTransfer() }));
        const event = await moved;

        expect(event.detail.position).to.equal('before');
        expect(event.detail.parent_id).to.equal(null);
    });

    it('узел нельзя перетащить внутрь собственного потомка', async () => {
        const el = await mountTree({ draggable: true });
        el.revealNode('onboarding');
        await elementUpdated(el);

        rowById(el, 'root').dispatchEvent(
            new DragEvent('dragstart', { bubbles: true, dataTransfer: new DataTransfer() }),
        );
        await elementUpdated(el);
        const target = rowById(el, 'guides');
        const rect = target.getBoundingClientRect();
        target.dispatchEvent(new DragEvent('dragover', {
            bubbles: true,
            cancelable: true,
            dataTransfer: new DataTransfer(),
            clientY: rect.top + rect.height / 2,
        }));
        await elementUpdated(el);

        expect(target.classList.contains('drop-inside')).to.be.false;
    });

    it('контекстное меню открывается и сообщает действие', async () => {
        const el = await mountTree({
            menuItems: (node) => [
                { id: 'rename', label: `Переименовать ${node.label}` },
                { id: 'delete', label: 'Удалить', danger: true },
            ],
        });

        rowById(el, 'archive').dispatchEvent(
            new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 40, clientY: 60 }),
        );
        await elementUpdated(el);

        const menu = el.shadowRoot.querySelector('platform-menu');
        expect(menu).to.exist;
        await elementUpdated(menu);

        const action = oneEvent(el, 'tree-action');
        menu.shadowRoot.querySelector('[data-menu-item="delete"]').click();
        const event = await action;

        expect(event.detail).to.include({ action: 'delete', id: 'archive' });
    });

    it('кнопка меню есть в каждой строке и открывает те же действия', async () => {
        const el = await mountTree({
            menuItems: () => [{ id: 'delete', label: 'Удалить', danger: true }],
        });

        expect(rows(el).every((row) => row.querySelector('.row-menu') !== null)).to.be.true;

        // Выбор узла по кнопке меню срабатывать не должен.
        let selected = false;
        el.addEventListener('tree-select', () => { selected = true; });
        rowById(el, 'archive').querySelector('[data-row-menu="archive"]').click();
        await elementUpdated(el);

        const menu = el.shadowRoot.querySelector('platform-menu');
        expect(menu).to.exist;
        expect(selected).to.be.false;
        await elementUpdated(menu);

        const action = oneEvent(el, 'tree-action');
        menu.shadowRoot.querySelector('[data-menu-item="delete"]').click();
        const event = await action;

        expect(event.detail).to.include({ action: 'delete', id: 'archive' });
    });

    it('повторный клик по кнопке меню закрывает его', async () => {
        const el = await mountTree({ menuItems: () => [{ id: 'delete', label: 'Удалить' }] });
        const button = rowById(el, 'archive').querySelector('[data-row-menu="archive"]');

        button.click();
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('platform-menu')).to.exist;

        button.click();
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('platform-menu')).to.be.null;
    });

    it('без menuItems кнопки меню в строке нет', async () => {
        const el = await mountTree();

        expect(rowById(el, 'root').querySelector('.row-menu')).to.be.null;
    });

    it('без menuItems контекстное меню не открывается', async () => {
        const el = await mountTree();

        rowById(el, 'root').dispatchEvent(
            new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 10, clientY: 10 }),
        );
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('platform-menu')).to.be.null;
    });

    it('пустое дерево показывает подпись', async () => {
        const el = await fixture(html`
            <platform-tree .nodes=${[]} empty-label="Пока пусто"></platform-tree>
        `);
        await elementUpdated(el);

        expect(el.shadowRoot.querySelector('.empty').textContent).to.contain('Пока пусто');
    });

    it('число справа выводится, когда оно задано', async () => {
        const el = await mountTree();

        expect(rowById(el, 'archive').querySelector('.count').textContent.trim()).to.equal('12');
        expect(rowById(el, 'root').querySelector('.count')).to.be.null;
    });
});
