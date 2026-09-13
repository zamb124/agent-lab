/**
 * Холст редактора: ``<platform-flow-ui editing>`` рендерит документ грамматики без сети,
 * подставляет тестовый state в шаблоны, помечает контейнеры и выделение, переключает страницы.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, waitUntil } from '../helpers/render.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import { blockElement, blockIdFromEvent, pageRenderRoot } from '@platform/lib/flow-ui/editor/selection.js';

const DOCUMENT = {
    start_page_id: 'main',
    pages: [
        {
            page_id: 'main',
            title: 'Заявка',
            blocks: [
                { block_id: 'title', type: 'heading', visible_when: null, text: 'Заявка {customer.name}', level: 2 },
                {
                    block_id: 'form',
                    type: 'section',
                    visible_when: null,
                    title: 'Контакты',
                    blocks: [
                        { block_id: 'email', type: 'text_input', visible_when: null, field: 'email', label: 'Email', required: true, error_message: '', action: null, placeholder: '', default: '', pattern: '', multiline: false, secret: false },
                    ],
                },
                { block_id: 'hidden', type: 'text', visible_when: { path: 'never', equals: null }, markdown: 'скрытый в рантайме' },
                { block_id: 'send', type: 'button', visible_when: null, label: 'Отправить', action: { name: 'submit', payload: {} }, variant: 'primary' },
            ],
        },
        { page_id: 'done', title: 'Готово', blocks: [{ block_id: 'thanks', type: 'text', visible_when: null, markdown: 'Спасибо, {email}' }] },
    ],
};

async function mountEditing(sampleState = {}) {
    const element = await fixture(html`<platform-flow-ui editing .initialDocument=${DOCUMENT} .sampleState=${sampleState}></platform-flow-ui>`);
    await waitUntil(() => pageRenderRoot(element) !== null && blockElement(element, 'title') !== null, 'page did not render');
    return element;
}

describe('platform-flow-ui editing canvas', () => {
    afterEach(() => fixtureCleanup());

    it('renders grammar blocks with sample state and keeps hidden blocks visible for the author', async () => {
        const element = await mountEditing({ customer: { name: 'Анна' } });
        expect(blockElement(element, 'title').textContent).to.contain('Заявка Анна');
        expect(blockElement(element, 'title').dataset.span).to.equal('12');
        expect(blockElement(element, 'title').dataset.align).to.equal('start');
        expect(blockElement(element, 'hidden')).to.not.equal(null);
        expect(blockElement(element, 'form').querySelector('[data-container-key="form"]')).to.not.equal(null);
        expect(blockElement(element, 'email')).to.not.equal(null);
        expect(element.store.document).to.equal(DOCUMENT);
        expect(element.store.state).to.deep.equal({ customer: { name: 'Анна' } });
    });

    it('shows unresolved template paths as-is on the canvas', async () => {
        const element = await mountEditing({});
        expect(blockElement(element, 'title').textContent).to.contain('Заявка {customer.name}');
    });

    it('marks the selected block and navigates between pages', async () => {
        const element = await mountEditing({});
        element.selectedBlockId = 'send';
        await elementUpdated(element);
        await waitUntil(() => blockElement(element, 'send')?.dataset.selected === 'true', 'selection did not render');
        element.navigate('done');
        await waitUntil(() => blockElement(element, 'thanks') !== null, 'second page did not render');
        expect(element.store.pageId).to.equal('done');
        expect(blockElement(element, 'title')).to.equal(null);
        expect(() => element.navigate('missing')).to.throw(/unknown page_id/);
    });

    it('hides the page heading when show_title is off', async () => {
        const element = await mountEditing({});
        expect(pageRenderRoot(element).querySelector('h1.page-title').textContent).to.equal('Заявка');
        element.initialDocument = {
            ...DOCUMENT,
            pages: [{ ...DOCUMENT.pages[0], show_title: false }, DOCUMENT.pages[1]],
        };
        await elementUpdated(element);
        await waitUntil(() => pageRenderRoot(element).querySelector('h1.page-title') === null, 'page title stayed on the canvas');
    });

    it('follows page-id when the editing document gains a page', async () => {
        const element = await mountEditing({});
        element.pageId = 'page-2';
        element.initialDocument = {
            start_page_id: 'main',
            pages: [
                DOCUMENT.pages[0],
                { page_id: 'page-2', title: 'Вторая', blocks: [{ block_id: 'extra', type: 'text', visible_when: null, markdown: 'вторая' }] },
            ],
        };
        await elementUpdated(element);
        await waitUntil(() => blockElement(element, 'extra') !== null, 'page-2 did not render');
        expect(element.store.pageId).to.equal('page-2');
        expect(blockElement(element, 'title')).to.equal(null);
    });

    it('keeps empty columns, sections and tabs tall enough to drop a block into', async () => {
        const document = {
            start_page_id: 'main',
            pages: [{
                page_id: 'main',
                title: '',
                blocks: [
                    { block_id: 'cols', type: 'columns', visible_when: null, columns: [{ width: 6, blocks: [] }, { width: 6, blocks: [] }] },
                    { block_id: 'box', type: 'section', visible_when: null, title: '', blocks: [] },
                    { block_id: 'tabs', type: 'tabs', visible_when: null, tabs: [{ title: 'A', blocks: [] }, { title: 'B', blocks: [] }] },
                ],
            }],
        };
        const element = await fixture(html`<platform-flow-ui editing locale="en" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => blockElement(element, 'cols') !== null, 'columns did not render');
        const column = blockElement(element, 'cols').querySelector('[data-container-key="cols/0"]');
        const hint = column.querySelector('.fu-container-empty');
        expect(hint).to.not.equal(null);
        expect(hint.textContent).to.contain('Drop a block here');
        expect(column.getBoundingClientRect().height).to.be.at.least(64);
        expect(blockElement(element, 'box').querySelector('.fu-container-empty').textContent).to.contain('Drop a block here');
        expect(blockElement(element, 'tabs').querySelector('.fu-tab-panel .fu-container-empty').textContent).to.contain('Drop a block here');
    });

    it('shows an error state instead of an uncaught rejection when live chat has no base-url', async () => {
        const element = await fixture(html`<platform-flow-ui flow-id="flow-1"></platform-flow-ui>`);
        await waitUntil(() => element._status === 'error', 'missing base-url did not surface');
        expect(element._error).to.be.instanceOf(Error);
        expect(element._error.message).to.match(/baseUrl is required/);
        expect(element.client).to.equal(null);
    });

    it('sizes a block by span and centers it in the parent', async () => {
        const document = {
            start_page_id: 'main',
            pages: [{
                page_id: 'main',
                title: '',
                blocks: [
                    { block_id: 'narrow', type: 'heading', visible_when: null, text: 'Half', level: 2, span: 6, align: 'center', valign: 'start' },
                ],
            }],
        };
        const element = await fixture(html`<platform-flow-ui editing locale="en" style="display:block;width:1100px" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => blockElement(element, 'narrow') !== null, 'heading did not render');
        const block = blockElement(element, 'narrow');
        expect(block.dataset.span).to.equal('6');
        expect(block.dataset.align).to.equal('center');
        const parent = block.parentElement.getBoundingClientRect();
        const box = block.getBoundingClientRect();
        expect(box.width).to.be.closeTo(parent.width / 2, parent.width * 0.08);
        expect(box.left).to.be.greaterThan(parent.left + 8);
        expect(box.right).to.be.lessThan(parent.right - 8);
    });

    it('right-aligns a narrow block on a conversation page', async () => {
        const document = {
            start_page_id: 'main',
            pages: [{
                page_id: 'main',
                title: '',
                blocks: [
                    { block_id: 'narrow', type: 'heading', visible_when: null, text: 'Half', level: 2, span: 6, align: 'end', valign: 'start' },
                    {
                        block_id: 'conversation',
                        type: 'conversation',
                        visible_when: null,
                        settings: {
                            greeting: '', suggested_prompts: [], placeholder: '',
                            show_reasoning: false, tool_calls: 'compact', show_activity: true,
                            show_skill_loads: true, show_reflection: true, errors: 'generic',
                            show_run_trace: false, show_trace_actions: false,
                            show_browser_previews: true, show_files_panel: true,
                            allow_cancel: true, allow_voice: true,
                        },
                    },
                ],
            }],
        };
        const element = await fixture(html`<platform-flow-ui editing locale="en" style="display:block;width:1100px" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => blockElement(element, 'narrow') !== null, 'heading did not render');
        const block = blockElement(element, 'narrow');
        const parentEl = block.parentElement;
        const parent = parentEl.getBoundingClientRect();
        const style = getComputedStyle(parentEl);
        const innerLeft = parent.left + parseFloat(style.paddingLeft);
        const innerRight = parent.right - parseFloat(style.paddingRight);
        const innerWidth = innerRight - innerLeft;
        const box = block.getBoundingClientRect();
        expect(style.display).to.equal('grid');
        expect(box.width).to.be.closeTo(innerWidth / 2, innerWidth * 0.08);
        expect(box.left).to.be.greaterThan(innerLeft + innerWidth * 0.3);
        expect(box.right).to.be.closeTo(innerRight, 8);
    });

    it('vertically centers a block in a taller neighbour column', async () => {
        const field = (blockId, name) => ({
            block_id: blockId, type: 'text_input', visible_when: null, field: name, label: name,
            required: false, error_message: '', action: null, placeholder: '', default: '', pattern: '',
            multiline: false, secret: false,
        });
        const document = {
            start_page_id: 'main',
            pages: [{
                page_id: 'main',
                title: '',
                blocks: [{
                    block_id: 'cols',
                    type: 'columns',
                    visible_when: null,
                    columns: [
                        { width: 6, blocks: [field('a', 'a'), field('b', 'b'), field('c', 'c'), field('d', 'd')] },
                        {
                            width: 6,
                            blocks: [{
                                block_id: 'side', type: 'heading', visible_when: null, text: 'Side', level: 2,
                                span: 12, align: 'start', valign: 'center',
                            }],
                        },
                    ],
                }],
            }],
        };
        const element = await fixture(html`<platform-flow-ui editing locale="en" style="display:block;width:1100px" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => blockElement(element, 'side') !== null, 'column heading did not render');
        const column = blockElement(element, 'side').parentElement.getBoundingClientRect();
        const side = blockElement(element, 'side').getBoundingClientRect();
        expect(column.height).to.be.above(side.height + 40);
        expect(side.top).to.be.greaterThan(column.top + 8);
        expect(side.bottom).to.be.lessThan(column.bottom - 8);
        const columnMid = (column.top + column.bottom) / 2;
        const sideMid = (side.top + side.bottom) / 2;
        expect(sideMid).to.be.closeTo(columnMid, column.height * 0.2);
    });

    it('lets default video fill the reading column past 520px', async () => {
        const document = {
            start_page_id: 'main',
            pages: [{
                page_id: 'main',
                title: '',
                blocks: [
                    { block_id: 'clip', type: 'video', visible_when: null, url: 'https://example.com/intro.mp4' },
                    { block_id: 'send', type: 'button', visible_when: null, label: 'Отправить', action: { name: 'submit', payload: {} }, variant: 'primary' },
                    { block_id: 'phone', type: 'text_input', visible_when: null, field: 'phone', label: 'Телефон', required: false, error_message: '', action: null, placeholder: '', default: '', pattern: '', multiline: false, secret: false },
                    { block_id: 'plan', type: 'select', visible_when: null, field: 'plan', label: 'Тариф', required: false, error_message: '', action: null, options: [{ value: 'a', label: 'A' }], multiple: false, default: null },
                    { block_id: 'note', type: 'text_input', visible_when: null, field: 'note', label: 'Комментарий', required: false, error_message: '', action: null, placeholder: '', default: '', pattern: '', multiline: true, secret: false },
                    { block_id: 'go', type: 'button', visible_when: null, label: 'Дальше', action: { name: 'next', payload: {} }, variant: 'primary' },
                ],
            }],
        };
        const element = await fixture(html`<platform-flow-ui editing locale="en" style="display:block;width:1100px" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => blockElement(element, 'go') !== null, 'form did not render');
        const video = blockElement(element, 'clip').querySelector('video');
        expect(video.getBoundingClientRect().width).to.be.above(520);
        const host = element.getBoundingClientRect();
        const last = blockElement(element, 'go').getBoundingClientRect();
        expect(last.bottom).to.be.at.most(host.bottom + 2);
        expect(host.height).to.be.above(480);
    });

    it('keeps a narrow button hit box at least as wide as the visible control', async () => {
        const document = {
            start_page_id: 'main',
            pages: [{
                page_id: 'main',
                title: '',
                blocks: [{
                    block_id: 'next', type: 'button', visible_when: null, label: 'Далее',
                    action: { name: 'submit', payload: {} }, variant: 'secondary',
                    span: 1, align: 'center', valign: 'start',
                }],
            }],
        };
        const element = await fixture(html`<platform-flow-ui editing locale="en" style="display:block;width:1100px" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => blockElement(element, 'next') !== null, 'button did not render');
        const block = blockElement(element, 'next');
        const control = block.querySelector('.fu-button');
        const box = block.getBoundingClientRect();
        const visible = control.getBoundingClientRect();
        expect(control.disabled).to.equal(true);
        expect(box.width).to.be.at.least(visible.width - 0.5);
        expect(box.height).to.be.at.least(visible.height - 0.5);
        expect(box.left).to.be.at.most(visible.left + 0.5);
        expect(box.right).to.be.at.least(visible.right - 0.5);
        const hit = pageRenderRoot(element).elementFromPoint(visible.left + visible.width / 2, visible.top + visible.height / 2);
        expect(hit).to.equal(block);
    });

    it('renders a page-target button without a ui-action name', async () => {
        const document = {
            start_page_id: 'main',
            pages: [
                {
                    page_id: 'main',
                    title: '',
                    blocks: [{
                        block_id: 'next', type: 'button', visible_when: null, label: 'Далее',
                        action: null, page_id: 'done', url: '', variant: 'primary',
                    }],
                },
                { page_id: 'done', title: 'Готово', blocks: [{ block_id: 'thanks', type: 'text', visible_when: null, markdown: 'Ок' }] },
            ],
        };
        const element = await fixture(html`<platform-flow-ui editing locale="en" style="display:block;width:1100px" .initialDocument=${document}></platform-flow-ui>`);
        await waitUntil(() => blockElement(element, 'next') !== null, 'button did not render');
        const control = blockElement(element, 'next').querySelector('.fu-button');
        expect(control.getAttribute('data-page-id')).to.equal('done');
        expect(control.hasAttribute('data-action')).to.equal(false);
    });

    it('lets the author select an html block whose iframe would otherwise eat clicks', async () => {
        const document = {
            start_page_id: 'main',
            pages: [{
                page_id: 'main',
                title: '',
                blocks: [{
                    block_id: 'card', type: 'html', visible_when: null,
                    source: '<p data-bind="title"></p><div style="height:48px">pad</div>',
                    height: 'auto', fields: [], field: null,
                }],
            }],
        };
        const element = await fixture(html`<platform-flow-ui editing locale="en" style="display:block;width:1100px" .initialDocument=${document} .sampleState=${{ title: 'Hi' }}></platform-flow-ui>`);
        await waitUntil(() => blockElement(element, 'card') !== null, 'html block did not render');
        const block = blockElement(element, 'card');
        const host = block.querySelector('flow-ui-html-block');
        expect(getComputedStyle(host).pointerEvents).to.equal('none');
        await waitUntil(() => host.getBoundingClientRect().height > 0, 'html host has no size');
        const box = host.getBoundingClientRect();
        const hit = pageRenderRoot(element).elementFromPoint(box.left + Math.min(24, box.width / 2), box.top + 8);
        expect(hit?.closest('.fu-block')?.dataset.blockId).to.equal('card');
        const event = new MouseEvent('click', { bubbles: true, composed: true });
        Object.defineProperty(event, 'composedPath', { value: () => [hit, block] });
        expect(blockIdFromEvent(event)).to.equal('card');
    });
});
