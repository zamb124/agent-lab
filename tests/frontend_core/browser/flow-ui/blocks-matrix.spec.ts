/**
 * Матрица блоков: каждый тип грамматики (``schema.json`` == ``core/flow_ui/document.py``)
 * рендерится на холсте редактора из дефолтного блока каталога и внутри каждого контейнера;
 * в рантайме ``visible_when`` скрывает блоки, а обязательные поля блокируют действие.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, waitUntil } from '../helpers/render.js';
import { installFetchMock } from '../helpers/fake-fetch.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import { blockElement, pageRenderRoot } from '@platform/lib/flow-ui/editor/selection.js';
import { FLOW_UI_BLOCK_RENDERERS } from '@platform/lib/flow-ui/blocks/registry.js';
import { CONTAINER_TYPES, blockCatalog, catalogEntry, defaultBlock, uniqueBlockId } from '../../../../apps/flows/ui/_helpers/interface-editor-domain.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import schema from '../../../fixtures/flow_ui/schema.json' with { type: 'json' };
import {q, qs, qsa, type TestEl} from '../helpers/dom.js';
import type { FlowUiBlock } from '../../../../apps/flows/ui/_helpers/interface-editor-domain.js';

const catalog = blockCatalog(schema);

/** Те же строки, что редактор берёт из i18n: у каждого обязательного шаблона есть стартовый текст. */
const labels = {
    tab: flowsEn.interface_editor.default_tab,
    option: flowsEn.interface_editor.default_option,
    text: (type: any, property: any) => {
        const value = (flowsEn.interface_editor as Record<string, string>)[`default_text_${type}_${property}`];
        if (typeof value !== 'string') throw new Error(`missing i18n default_text_${type}_${property}`);
        return value;
    },
};

function interfaceResponse(document: any) {
    return {
        flow_id: 'flow-1',
        branch_id: 'default',
        document,
        viewer: { can_edit_flow: false, can_interact: true, can_share: false, auth_mode: 'platform' },
        look: null,
        capabilities: { cancel: true, files: false, voice: false },
        flow_identity: { title: 'Flow', image_url: null },
    };
}

function allDefaultBlocks() {
    const page = { page_id: 'main', title: '', blocks: [] };
    const blocks: any[] = [];
    for (const entry of catalog) {
        const block = defaultBlock(entry, uniqueBlockId(page, entry.type), labels);
        (page.blocks as FlowUiBlock[]).push(block!);
        blocks.push(block);
    }
    return blocks;
}

function documentWith(blocks: any, extraPages = []) {
    return { start_page_id: 'main', pages: [{ page_id: 'main', title: 'Matrix', blocks }, ...extraPages] };
}

async function mount(document: any, { sampleState = {} } = {}) {
    const element = await fixture<TestEl>(html`<platform-flow-ui editing .initialDocument=${document} .sampleState=${sampleState}></platform-flow-ui>`);
    await waitUntil(() => pageRenderRoot(element) !== null, 'page did not render', { timeout: 8000 });
    return element;
}

/** Рантайм без сети: ``GET .../interface`` отвечает документом, дальше state задаёт тест. */
async function mountRuntime(document: any, state: any) {
    const fetchMock = installFetchMock();
    fetchMock.respondJson('GET', (url: string) => url.includes('/flows/api/v1/flow-1/interface'), interfaceResponse(document));
    const element = await fixture<TestEl>(html`<platform-flow-ui flow-id="flow-1" base-url="/flows"></platform-flow-ui>`);
    await waitUntil(() => element._status === 'ready', 'runtime did not open the interface', { timeout: 8000 });
    element.store.setState(state);
    await waitUntil(() => pageRenderRoot(element) !== null, 'runtime page did not render', { timeout: 8000 });
    return { element, fetchMock };
}

function renderedIds(element: any) {
    return [...qsa(pageRenderRoot(element)!, '[data-block-id]')].map((node) => (node as TestEl).dataset.blockId);
}

describe('flow-ui blocks matrix', function () {
    this.timeout(20_000);

    afterEach(() => fixtureCleanup());

    it('registry covers exactly the grammar block types', () => {
        const grammarTypes = catalog.map((entry) => entry.type).sort();
        expect(Object.keys(FLOW_UI_BLOCK_RENDERERS).sort()).to.deep.equal(grammarTypes);
        expect(grammarTypes.length).to.be.greaterThan(40);
    });

    it('renders a default block of every type on the editing canvas without errors', async () => {
        const blocks = allDefaultBlocks();
        const element = await mount(documentWith(blocks), { sampleState: { items: [{ name: 'a' }], rows: [], file: null } });
        const expected = blocks.map((block) => block.block_id);
        await waitUntil(() => expected.every((id) => blockElement(element, id) !== null), 'not every block rendered', { timeout: 8000 });
        const seen = renderedIds(element);
        for (const id of expected) expect(seen, id).to.include(id);
        for (const block of blocks) {
            const node = blockElement(element, block.block_id);
            expect((node as TestEl).dataset.blockType, block.block_id).to.equal(block.type);
            expect((node as TestEl).dataset.renderError, block.block_id).to.equal(undefined);
        }
        // Блоки данных без sample state остаются выбираемыми на холсте через заглушку
        for (const type of ['chart', 'json_view', 'file_list', 'file_card']) {
            const node = blockElement(element, blocks.find((block) => block.type === type).block_id);
            expect(qs(node!, '.fu-block-empty').textContent, type).to.contain(`The ${type} block is empty`);
        }
        expect(q(element.renderRoot, 'flow-ui-error-boundary')).to.equal(null);
    });

    it('renders every block type nested inside each container type', async () => {
        const leafEntries = catalog.filter((entry) => !CONTAINER_TYPES.includes(entry.type));
        const containers: any[] = [];
        for (const containerType of CONTAINER_TYPES) {
            const container = defaultBlock(catalogEntry(catalog, containerType), `wrap-${containerType}`, labels);
            const children = leafEntries.map((entry) => defaultBlock(entry, `${containerType}-${entry.type}`, labels));
            if (containerType === 'section') container.blocks = children;
            if (containerType === 'columns') container.columns = [{ width: 6, blocks: children.slice(0, 10) }, { width: 6, blocks: children.slice(10) }];
            if (containerType === 'tabs') container.tabs = [{ title: 'A', blocks: children.slice(0, 10) }, { title: 'B', blocks: children.slice(10) }];
            containers.push(container);
        }
        const element = await mount(documentWith(containers));
        for (const container of containers) {
            await waitUntil(() => blockElement(element, container.block_id) !== null, container.block_id, { timeout: 8000 });
        }
        const seen = new Set(renderedIds(element));
        for (const containerType of CONTAINER_TYPES) {
            for (const entry of leafEntries) {
                const id = `${containerType}-${entry.type}`;
                // Вкладка B не активна: её блоки появляются только после переключения вкладки
                if (containerType === 'tabs' && leafEntries.indexOf(entry) >= 10) continue;
                expect(seen.has(id), id).to.equal(true);
            }
        }
        const tabs = blockElement(element, 'wrap-tabs');
        const secondTab = qsa(tabs!, 'nav button')[1];
        (secondTab as TestEl).click();
        await elementUpdated(element);
        await waitUntil(() => blockElement(element, `tabs-${leafEntries[10]!.type}`) !== null, 'second tab did not render', { timeout: 8000 });
        expect(blockElement(element, `tabs-${leafEntries[0]!.type}`)).to.equal(null);
        expect(qs(blockElement(element, 'wrap-tabs')!, 'nav button[aria-selected="true"]').dataset.tabIndex).to.equal('1');
    });

    it('keeps a renderer error inside its block and treats an unresolved URL template as no URL yet', async () => {
        const element = await mount(documentWith([
            { block_id: 'before', type: 'heading', visible_when: null, text: 'До {customer.name}', level: 2 },
            { block_id: 'img', type: 'image', visible_when: null, url: '{file.url}', alt: '' },
            { block_id: 'avatar', type: 'avatar', visible_when: null, name: '{?contact.name|Support}', image_url: '{?contact.image_url}' },
            { block_id: 'relative', type: 'video', visible_when: null, url: 'movie.mp4' },
            { block_id: 'scheme', type: 'audio', visible_when: null, url: 'javascript:alert(1)' },
            { block_id: 'ok', type: 'image', visible_when: null, url: 'https://example.com/a.png', alt: 'a' },
            { block_id: 'after', type: 'text', visible_when: null, markdown: 'После' },
        ]));
        await waitUntil(() => blockElement(element, 'after') !== null, 'page did not render around the broken block', { timeout: 8000 });
        // Текстовые шаблоны показывают структуру, URL-шаблоны — нет: {path} не адрес
        expect(blockElement(element, 'before')!.textContent).to.contain('До {customer.name}');
        expect(qs(blockElement(element, 'img')!, '.fu-block-empty').textContent).to.contain('The image block is empty');
        expect(qs(blockElement(element, 'avatar')!, '.initials').textContent).to.equal('S');
        expect(q(blockElement(element, 'avatar')!, 'img')).to.equal(null);
        expect(qs(blockElement(element, 'ok')!, 'img').getAttribute('src')).to.equal('https://example.com/a.png');

        const relative = blockElement(element, 'relative');
        expect((relative as TestEl).dataset.renderError).to.equal('true');
        expect(qs(relative!, '.fu-block-error').textContent).to.contain('expected absolute path or http(s) URL, got "movie.mp4"');
        expect(qs(blockElement(element, 'scheme')!, '.fu-block-error').textContent).to.contain('blocked scheme javascript');

        // Появление значения в state рисует картинку без перезагрузки холста
        element.sampleState = { file: { url: 'https://example.com/b.png' }, contact: { image_url: 'https://example.com/c.png' } };
        await elementUpdated(element);
        await waitUntil(() => q(blockElement(element, 'img')!, 'img') !== null, 'image did not recover', { timeout: 4000 });
        expect(qs(blockElement(element, 'img')!, 'img').getAttribute('src')).to.equal('https://example.com/b.png');
        expect(qs(blockElement(element, 'avatar')!, 'img').getAttribute('src')).to.equal('https://example.com/c.png');
    });

    it('runtime hides blocks by visible_when, keeps zero and false as values and blocks actions on missing required fields', async () => {
        const submitted: any[] = [];
        const document = documentWith([
            { block_id: 'shown', type: 'text', visible_when: { path: 'flag' }, markdown: 'shown' },
            { block_id: 'hidden', type: 'text', visible_when: { path: 'other' }, markdown: 'hidden' },
            { block_id: 'zero', type: 'text', visible_when: { path: 'count', equals: 0 }, markdown: 'zero' },
            { block_id: 'off', type: 'text', visible_when: { path: 'count' }, markdown: 'off' },
            { block_id: 'nested', type: 'section', visible_when: null, title: '', blocks: [
                { block_id: 'inner-hidden', type: 'text', visible_when: { path: 'other' }, markdown: 'inner' },
            ] },
            { block_id: 'name', type: 'text_input', visible_when: null, field: 'name', label: 'Имя', required: true, error_message: 'Заполните имя', action: null, placeholder: '', default: '', pattern: '', multiline: false, secret: false },
            { block_id: 'send', type: 'button', visible_when: null, label: 'Отправить', action: { name: 'submit', payload: { plan: 'pro' } }, variant: 'primary' },
        ]);
        const { element, fetchMock } = await mountRuntime(document, { flag: true, count: 0 });
        // Отправка хода — A2A SendStreamingMessage; здесь фиксируем только собранный ui-action
        element._submit = async (turn: any) => { submitted.push(turn); };
        await waitUntil(() => blockElement(element, 'shown') !== null, 'runtime blocks did not render', { timeout: 8000 });
        expect(fetchMock.calls.map((call) => call.method)).to.deep.equal(['GET']);
        expect(blockElement(element, 'hidden')).to.equal(null);
        expect(blockElement(element, 'inner-hidden')).to.equal(null);
        expect(blockElement(element, 'zero')).to.not.equal(null);
        expect(blockElement(element, 'off')).to.equal(null);

        qs(blockElement(element, 'send')!, 'button').click();
        await elementUpdated(element);
        expect(submitted).to.deep.equal([]);
        expect(element.store.fieldErrors.has('name')).to.equal(true);
        await waitUntil(() => blockElement(element, 'name')!.textContent.includes('Заполните имя'), 'required error not shown', { timeout: 4000 });

        const input = qs(blockElement(element, 'name')!, 'input');
        (input as TestEl).value = 'Анна';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(element);
        qs(blockElement(element, 'send')!, 'button').click();
        await waitUntil(() => submitted.length === 1, 'action was not submitted', { timeout: 4000 });
        expect(submitted[0]).to.deep.equal({
            action: { action: 'submit', source: 'send', fields: { name: 'Анна' }, payload: { plan: 'pro' } },
        });
        fetchMock.uninstall();
    });
});
