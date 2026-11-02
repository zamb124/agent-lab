/**
 * ShopCategoryTree — дерево категорий меню: вложенный рендер, раскрытие,
 * счётчики, drag&drop порядка/вложенности, drop товаров, inline-операции.
 * События наружу: tree-change (полный items), tree-select, tree-toggle,
 * tree-create, tree-rename, tree-remove, product-drop.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../apps/shop/ui/components/shop-category-tree.js';
import type { ShopTreeReorderItem } from '../../../../apps/shop/ui/components/shop-category-tree.js';

const CAT_MIME = 'application/x-shop-category-id';
const PROD_MIME = 'application/x-shop-product-id';

const CAT_A = { shop_category_id: 'cat_a', parent_id: null, name: 'Пицца', sort: 0, is_active: true };
const CAT_A1 = { shop_category_id: 'cat_a1', parent_id: 'cat_a', name: 'Классика', sort: 0, is_active: true };
const CAT_A2 = { shop_category_id: 'cat_a2', parent_id: 'cat_a', name: 'Авторская', sort: 1, is_active: true };
const CAT_B = { shop_category_id: 'cat_b', parent_id: null, name: 'Роллы', sort: 1, is_active: true };
const CATS = [CAT_A, CAT_B, CAT_A1, CAT_A2];

interface TreeState {
    categories?: typeof CATS;
    counts?: Record<string, number>;
    allCount?: number;
    activeId?: string | null;
    expandedIds?: string[];
}

async function treeFixture(state: TreeState = {}) {
    const el = await fixture<HTMLElement & { shadowRoot: ShadowRoot }>(html`
        <shop-category-tree
            .categories=${state.categories ?? CATS}
            .counts=${state.counts ?? {}}
            .allCount=${state.allCount ?? 0}
            .activeId=${state.activeId ?? null}
            .expandedIds=${state.expandedIds ?? ['cat_a']}
        ></shop-category-tree>
    `);
    await elementUpdated(el);
    return el;
}

function collect<T>(el: HTMLElement, name: string): T[] {
    const out: T[] = [];
    el.addEventListener(name, (e) => out.push((e as CustomEvent<T>).detail));
    return out;
}

function rowByLabel(root: ParentNode, label: string): HTMLElement {
    const hit = Array.from(root.querySelectorAll('.treeitem')).find(
        (n) => n.querySelector('.item-label')?.textContent?.trim() === label,
    );
    expect(hit, `treeitem "${label}"`).to.exist;
    return hit as HTMLElement;
}

function labels(root: ParentNode): string[] {
    return Array.from(root.querySelectorAll('.treeitem .item-label'))
        .map((n) => n.textContent?.trim() ?? '');
}

function fireDrag(target: HTMLElement, type: string, dt: DataTransfer, clientY = 0): void {
    target.dispatchEvent(new DragEvent(type, { dataTransfer: dt, clientY, bubbles: true, composed: true }));
}

function dragCategory(source: HTMLElement, target: HTMLElement, ratioY: number): DataTransfer {
    const dt = new DataTransfer();
    fireDrag(source, 'dragstart', dt);
    const rect = target.getBoundingClientRect();
    fireDrag(target, 'drop', dt, rect.top + rect.height * ratioY);
    return dt;
}

function typeIntoEditField(el: HTMLElement & { shadowRoot: ShadowRoot }, text: string): void {
    const input = el.shadowRoot.querySelector('.edit-input') as HTMLInputElement;
    expect(input, '.edit-input').to.exist;
    input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, composed: true }));
}

describe('shop-category-tree: рендер и навигация', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('вложенные категории видны при развёрнутом родителе с отступом', async () => {
        const el = await treeFixture();
        expect(labels(el.shadowRoot)).to.include.members(['Классика', 'Авторская']);
        const child = rowByLabel(el.shadowRoot, 'Классика');
        const row = child.closest('.row') as HTMLElement;
        expect(row.style.paddingLeft).to.equal('14px');
    });

    it('свернутая ветка скрывает детей', async () => {
        const el = await treeFixture({ expandedIds: [] });
        expect(labels(el.shadowRoot)).to.not.include('Классика');
        expect(labels(el.shadowRoot)).to.include.members(['Пицца', 'Роллы']);
    });

    it('toggle диспетчит tree-toggle, клик по строке — tree-select', async () => {
        const el = await treeFixture();
        const toggles = collect<{ id: string; expanded: boolean }>(el, 'tree-toggle');
        const selects = collect<{ id: string | null }>(el, 'tree-select');
        const catRow = rowByLabel(el.shadowRoot, 'Пицца').closest('.row') as HTMLElement;
        (catRow.querySelector('.toggle') as HTMLButtonElement).click();
        expect(toggles[0]).to.deep.equal({ id: 'cat_a', expanded: false });
        (rowByLabel(el.shadowRoot, 'Роллы').querySelector('.item-main') as HTMLButtonElement).click();
        expect(selects[0]).to.deep.equal({ id: 'cat_b' });
    });

    it('счётчики поддерева и allCount на строках', async () => {
        const el = await treeFixture({ counts: { cat_a: 5 }, allCount: 9 });
        const count = rowByLabel(el.shadowRoot, 'Пицца').querySelector('.count');
        expect(count?.textContent?.trim()).to.equal('5');
        const allCount = (el.shadowRoot.querySelector('.list .treeitem .count') as HTMLElement).textContent?.trim();
        expect(allCount).to.equal('9');
    });
});

describe('shop-category-tree: drag&drop категорий', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('drop в середину строки вкладывает категорию (parent_id = цель)', async () => {
        const el = await treeFixture();
        const changes = collect<{ items: ShopTreeReorderItem[] }>(el, 'tree-change');
        dragCategory(rowByLabel(el.shadowRoot, 'Роллы'), rowByLabel(el.shadowRoot, 'Пицца'), 0.5);
        expect(changes.length).to.equal(1);
        const items = changes[0]!.items;
        expect(items.length).to.equal(4);
        const moved = items.find((i) => i.category_id === 'cat_b');
        expect(moved?.parent_id).to.equal('cat_a');
    });

    it('drop выше строки переставляет среди siblings', async () => {
        const el = await treeFixture();
        const changes = collect<{ items: ShopTreeReorderItem[] }>(el, 'tree-change');
        dragCategory(rowByLabel(el.shadowRoot, 'Роллы'), rowByLabel(el.shadowRoot, 'Пицца'), 0.05);
        const items = changes[0]!.items;
        expect(items[0]!).to.deep.equal({ category_id: 'cat_b', parent_id: null });
        expect(items[1]!).to.deep.equal({ category_id: 'cat_a', parent_id: null });
    });

    it('drop ниже строки sibling переставляет внутри уровня', async () => {
        const el = await treeFixture();
        const changes = collect<{ items: ShopTreeReorderItem[] }>(el, 'tree-change');
        dragCategory(rowByLabel(el.shadowRoot, 'Авторская'), rowByLabel(el.shadowRoot, 'Классика'), 0.05);
        const items = changes[0]!.items;
        const kids = items.filter((i) => i.parent_id === 'cat_a').map((i) => i.category_id);
        expect(kids).to.deep.equal(['cat_a2', 'cat_a1']);
    });

    it('drop на собственного потомка запрещён — tree-change не уходит', async () => {
        const el = await treeFixture();
        const changes = collect<{ items: ShopTreeReorderItem[] }>(el, 'tree-change');
        dragCategory(rowByLabel(el.shadowRoot, 'Пицца'), rowByLabel(el.shadowRoot, 'Классика'), 0.5);
        expect(changes.length).to.equal(0);
    });

    it('drop на строку "все товары" переносит категорию в корень', async () => {
        const el = await treeFixture();
        const changes = collect<{ items: ShopTreeReorderItem[] }>(el, 'tree-change');
        const allRow = el.shadowRoot.querySelector('.list .treeitem') as HTMLElement;
        dragCategory(rowByLabel(el.shadowRoot, 'Классика'), allRow, 0.5);
        const moved = changes[0]!.items.find((i) => i.category_id === 'cat_a1');
        expect(moved?.parent_id).to.equal(null);
    });
});

describe('shop-category-tree: drop товаров', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('drop товара на категорию диспетчит product-drop с её id', async () => {
        const el = await treeFixture();
        const drops = collect<{ productId: string; categoryId: string | null }>(el, 'product-drop');
        const dt = new DataTransfer();
        dt.setData(PROD_MIME, 'prod_42');
        fireDrag(rowByLabel(el.shadowRoot, 'Роллы'), 'drop', dt, 10);
        expect(drops).to.deep.equal([{ productId: 'prod_42', categoryId: 'cat_b' }]);
    });

    it('drop товара на "все товары" диспетчит categoryId=null', async () => {
        const el = await treeFixture();
        const drops = collect<{ productId: string; categoryId: string | null }>(el, 'product-drop');
        const dt = new DataTransfer();
        dt.setData(PROD_MIME, 'prod_7');
        fireDrag(el.shadowRoot.querySelector('.list .treeitem') as HTMLElement, 'drop', dt, 10);
        expect(drops).to.deep.equal([{ productId: 'prod_7', categoryId: null }]);
    });
});

describe('shop-category-tree: inline-операции', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('кнопка + в шапке создаёт корень — tree-create parentId=null', async () => {
        const el = await treeFixture();
        const created = collect<{ parentId: string | null; name: string }>(el, 'tree-create');
        (el.shadowRoot.querySelector('.head platform-button') as HTMLElement).click();
        await elementUpdated(el);
        typeIntoEditField(el, 'Десерты');
        expect(created).to.deep.equal([{ parentId: null, name: 'Десерты' }]);
    });

    it('кнопка + у строки создаёт подкатегорию — tree-create с parentId', async () => {
        const el = await treeFixture();
        const created = collect<{ parentId: string | null; name: string }>(el, 'tree-create');
        const ops = rowByLabel(el.shadowRoot, 'Роллы').querySelectorAll('.ops platform-button');
        (ops[0] as HTMLElement | undefined)!.click();
        await elementUpdated(el);
        typeIntoEditField(el, 'Запечённые');
        expect(created).to.deep.equal([{ parentId: 'cat_b', name: 'Запечённые' }]);
    });

    it('карандаш переименовывает — tree-rename', async () => {
        const el = await treeFixture();
        const renamed = collect<{ id: string; name: string }>(el, 'tree-rename');
        const ops = rowByLabel(el.shadowRoot, 'Пицца').querySelectorAll('.ops platform-button');
        (ops[1] as HTMLElement | undefined)!.click();
        await elementUpdated(el);
        typeIntoEditField(el, 'Пицца NEW');
        expect(renamed).to.deep.equal([{ id: 'cat_a', name: 'Пицца NEW' }]);
    });

    it('строка "Новая категория" в конце списка создаёт корень', async () => {
        const el = await treeFixture();
        const created = collect<{ parentId: string | null; name: string }>(el, 'tree-create');
        (el.shadowRoot.querySelector('.add-row') as HTMLElement).click();
        await elementUpdated(el);
        typeIntoEditField(el, 'Напитки');
        expect(created).to.deep.equal([{ parentId: null, name: 'Напитки' }]);
    });

    it('корзина диспетчит tree-remove', async () => {
        const el = await treeFixture();
        const removed = collect<{ id: string }>(el, 'tree-remove');
        const ops = rowByLabel(el.shadowRoot, 'Роллы').querySelectorAll('.ops platform-button');
        (ops[2] as HTMLElement | undefined)!.click();
        expect(removed).to.deep.equal([{ id: 'cat_b' }]);
    });
});

describe('shop-category-tree: movebar активной строки', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('стрелка вверх переставляет с предыдущим sibling', async () => {
        const el = await treeFixture({ activeId: 'cat_b' });
        const changes = collect<{ items: ShopTreeReorderItem[] }>(el, 'tree-change');
        const movebar = el.shadowRoot.querySelector('.movebar') as HTMLElement;
        expect(movebar, 'movebar у активной строки').to.exist;
        (movebar.querySelectorAll('platform-button')[0] as HTMLElement | undefined)!.click();
        expect(changes[0]!.items[0]!).to.deep.equal({ category_id: 'cat_b', parent_id: null });
    });

    it('indent вкладывает под предыдущего sibling', async () => {
        const el = await treeFixture({ activeId: 'cat_b' });
        const changes = collect<{ items: ShopTreeReorderItem[] }>(el, 'tree-change');
        const movebar = el.shadowRoot.querySelector('.movebar') as HTMLElement;
        (movebar.querySelectorAll('platform-button')[2] as HTMLElement | undefined)!.click();
        const moved = changes[0]!.items.find((i) => i.category_id === 'cat_b');
        expect(moved?.parent_id).to.equal('cat_a');
    });

    it('outdent поднимает на уровень родителя — сразу после него', async () => {
        const el = await treeFixture({ activeId: 'cat_a2' });
        const changes = collect<{ items: ShopTreeReorderItem[] }>(el, 'tree-change');
        const movebar = el.shadowRoot.querySelector('.movebar') as HTMLElement;
        (movebar.querySelectorAll('platform-button')[3] as HTMLElement | undefined)!.click();
        const items = changes[0]!.items;
        const moved = items.find((i) => i.category_id === 'cat_a2');
        expect(moved?.parent_id).to.equal(null);
        const aIdx = items.findIndex((i) => i.category_id === 'cat_a');
        expect(items.findIndex((i) => i.category_id === 'cat_a2')).to.equal(aIdx + 2);
    });
});
