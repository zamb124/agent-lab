/**
 * Редактор блока ``html``: preview-first (кадр + исходник), inspector State/Events/Help,
 * last-good при битом JSON, сниппеты в курсор, Apply disabled на пустом source.
 * Кнопки кликаются, не выставляются внутренние поля.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html, waitUntil } from '../helpers/render.js';
import { bootstrapTestBus, resetPlatformState } from '../helpers/reset.js';
import { CoreEvents, getPlatformBus } from '@platform/lib/events/index.js';
import { FLOW_UI_HTML_MIN_HEIGHT, FLOW_UI_HTML_THEME_TOKENS } from '@platform/lib/flow-ui/runtime/html-sandbox.js';
import { HTML_EDITOR_LIVE_MS, HTML_EDITOR_VIEWPORTS } from '@platform/lib/flow-ui/editor/html-editor-api.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import '@platform/lib/components/platform-modal-stack.js';
import '../../../../apps/flows/ui/modals/flows-interface-html-editor-modal.js';
import {ensureTokensLoaded, q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

const T = flowsEn.interface_editor;
const BLOCK = {
    block_id: 'card',
    type: 'html',
    visible_when: null,
    source: '<b data-bind="title"></b><i data-show="order.total"></i>',
    height: 'auto',
    fields: ['items'],
    field: 'card',
};

const SAMPLE_STATE = { title: 'Hello', order: { total: 42, currency: 'RUB' }, task_id: 'system-only' };
const LAYOUT_KEY = 'platform:flows:html_editor_layout';
const PANELS_KEY = 'platform:flows:html_editor_panels';

function seedTranslations(bus: any) {
    const locale = bus.getState().i18n.locale;
    const previous = bus.getState().i18n.translations[locale] || {};
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale, bundle: { ...previous, flows: flowsEn } }, { source: 'system' });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale, default_namespace: 'flows' }, { source: 'system' });
}

async function openModal(props: any) {
    const stack = await fixture<TestEl>(html`<platform-modal-stack></platform-modal-stack>`);
    getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'flows.interface_html_editor', props });
    await elementUpdated(stack);
    const modal = [...qsa(document!, 'flows-interface-html-editor-modal')].at(-1);
    expect(modal, 'modal mounted').to.exist;
    await waitUntil(() => q(modal!.renderRoot, '.workspace') !== null, 'modal body did not render', { timeout: 4000 });
    return modal;
}

async function clickSegment(control: any, valueOrLabel: any) {
    expect(control, `segmented control for ${valueOrLabel}`).to.exist;
    await elementUpdated(control);
    await waitUntil(
        () => (shadow(control) || control.renderRoot)?.querySelectorAll('button.segment').length > 0,
        `no segments for ${valueOrLabel}`,
        { timeout: 2000 },
    );
    const root = shadow(control) || control.renderRoot;
    const items = Array.isArray(control.items) ? control.items : [];
    const index = items.findIndex((item: any) => (
        (item as TestEl).value === valueOrLabel || item.label === valueOrLabel || item.title === valueOrLabel
    ));
    const buttons = [...qsa(root!, 'button.segment')];
    const byLabel = buttons.find((el) => {
        const text = el.textContent.replace(/\s+/g, ' ').trim();
        return el.getAttribute('aria-label') === valueOrLabel || el.title === valueOrLabel || text === valueOrLabel;
    });
    const button = byLabel || (index >= 0 ? buttons[index] : null);
    expect(button, `segment ${valueOrLabel} values=${JSON.stringify(items.map((item: any) => (item as TestEl).value))}`).to.exist;
    (button as TestEl).click();
}

async function clickInspectorTab(modal: any, valueOrLabel: any) {
    await clickSegment(qs(modal.renderRoot, '.inspector-tabs'), valueOrLabel);
    await elementUpdated(modal);
}

async function waitPreview(modal: any) {
    const preview = qs(modal.renderRoot, 'flow-ui-html-block');
    expect(preview, 'preview block').to.exist;
    await waitUntil(() => preview._bridge !== null, 'sandbox bridge missing', { timeout: 4000 });
    await waitUntil(() => preview._height > FLOW_UI_HTML_MIN_HEIGHT, 'preview iframe did not size itself', { timeout: 4000 });
    return preview;
}

function emitChange(element: any, value: any) {
    element.dispatchEvent(new CustomEvent('change', { detail: { value }, bubbles: true, composed: true }));
}

function rectsOverlap(a: any, b: any) {
    return a.right > b.left && a.left < b.right && a.bottom > b.top && a.top < b.bottom;
}

describe('flows-interface-html-editor-modal', function () {
    this.timeout(12_000);

    beforeEach(async () => {
        resetPlatformState();
        bootstrapTestBus({ factories: [] });
        await ensureTokensLoaded();
        seedTranslations(getPlatformBus());
        localStorage.removeItem(LAYOUT_KEY);
        localStorage.removeItem(PANELS_KEY);
    });

    afterEach(() => {
        fixtureCleanup();
        for (const leftover of qsa(document!, 'flows-interface-html-editor-modal')) leftover.remove();
    });

    it('opens the test state as the block projection with null placeholders for missing paths', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: ['title'], onApply: () => {} });
        expect(JSON.parse(modal!._stateText)).to.deep.equal({ items: null, title: 'Hello', order: { total: 42 } });
        await clickInspectorTab(modal, 'help');
        const sheet = qs(modal!.renderRoot, '.sheet');
        const sections = [...qsa(sheet!, 'section')];
        const chips = sections.map((section) => [...qsa(section!, '.chips code')].map((code) => code.textContent));
        expect(chips[0]).to.deep.equal(['items', 'title', 'order.total']);
        expect(chips[1]).to.deep.equal(['card']);
        expect([...qsa(sections[3]!, '.chips button')].map((button) => button.textContent)).to.deep.equal([...FLOW_UI_HTML_THEME_TOKENS]);
        const api = [...qsa(sheet!, '.api code')].map((code) => code.textContent);
        expect(api).to.include('flowUi.send(\'action\', { ... })');
        expect(api).to.include('data-bind="path"');
        expect(sheet.textContent).to.contain(T.html_api_send);
    });

    it('keeps preview tools on the stage and source tools on the source pane', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const root = modal!.renderRoot;
        expect(q(root!, '.modal-header .viewport-control'), 'viewport not in header').to.equal(null);
        expect(q(root!, '.modal-header .snippets-trigger'), 'snippets not in header').to.equal(null);
        expect(q(root!, '.modal-header [data-reload]'), 'reload not in header').to.equal(null);
        expect(qs(root!, '.stage-toolbar .viewport-control'), 'viewport on preview').to.exist;
        expect(qs(root!, '.stage-toolbar .theme-control'), 'theme on preview').to.exist;
        expect(qs(root!, '.stage-toolbar [data-reload]'), 'reload on preview').to.exist;
        expect(q(root!, '.source-toolbar .snippets-trigger'), 'snippets on source').to.exist;
        expect(q(root!, '.source-toolbar [data-replace]'), 'replace on source').to.exist;
        expect(q(root!, '.panel-switch [data-panel="preview"]'), 'panel switcher').to.exist;
        expect(q(root!, '.source-toolbar .layout-control'), 'layout on source').to.exist;
        expect(q(root!, '.snippets [data-replace]'), 'replace not inside snippets').to.equal(null);
        expect(q(root!, '.snippets [data-layout]'), 'layout not inside snippets').to.equal(null);
        expect(qs(root!, '[data-reload]').textContent).to.contain(T.html_reload);
    });

    it('hides the inspector so preview and source take the freed height', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const workspace = qs(modal!.renderRoot, '.workspace');
        workspace.style.height = '640px';
        workspace.style.width = '960px';
        await elementUpdated(modal!);
        const panes = qs(modal!.renderRoot, '.panes');
        const inspector = qs(modal!.renderRoot, '.inspector');
        const before = panes.getBoundingClientRect().height;
        qs(modal!.renderRoot, '[data-collapse="inspector"]').click();
        await elementUpdated(modal!);
        expect(workspace.getAttribute('data-inspector')).to.equal('off');
        expect(getComputedStyle(inspector).display).to.equal('none');
        expect(panes.getBoundingClientRect().height).to.be.greaterThan(before + 40);
        expect(JSON.parse(localStorage.getItem(PANELS_KEY)!).inspector).to.equal(false);
    });

    it('hides the source pane so the preview fills the row', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const workspace = qs(modal!.renderRoot, '.workspace');
        workspace.style.height = '640px';
        workspace.style.width = '960px';
        await elementUpdated(modal!);
        const source = qs(modal!.renderRoot, '.pane');
        qs(modal!.renderRoot, '[data-collapse="source"]').click();
        await elementUpdated(modal!);
        expect(workspace.getAttribute('data-source')).to.equal('off');
        expect(getComputedStyle(source).display).to.equal('none');
        const panesBox = qs(modal!.renderRoot, '.panes').getBoundingClientRect();
        const previewBox = qs(modal!.renderRoot, '.preview-pane').getBoundingClientRect();
        expect(Math.abs(previewBox.width - panesBox.width)).to.be.at.most(4);
        expect(previewBox.height).to.be.greaterThan(40);
        expect(q(modal!.renderRoot, '.layout-control')).to.equal(null);
    });

    it('restores a hidden preview from the panel switcher', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        qs(modal!.renderRoot, '[data-collapse="preview"]').click();
        await elementUpdated(modal!);
        expect(qs(modal!.renderRoot, '.workspace').getAttribute('data-preview')).to.equal('off');
        expect(getComputedStyle(qs(modal!.renderRoot, '.preview-pane')).display).to.equal('none');
        qs(modal!.renderRoot, '.panel-switch [data-panel="preview"]').click();
        await elementUpdated(modal!);
        expect(qs(modal!.renderRoot, '.workspace').getAttribute('data-preview')).to.equal('on');
        expect(getComputedStyle(qs(modal!.renderRoot, '.preview-pane')).display).to.not.equal('none');
    });

    it('keeps at least one panel visible', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        qs(modal!.renderRoot, '.panel-switch [data-panel="preview"]').click();
        await elementUpdated(modal!);
        qs(modal!.renderRoot, '.panel-switch [data-panel="source"]').click();
        await elementUpdated(modal!);
        const last = qs(modal!.renderRoot, '.panel-switch [data-panel="inspector"]');
        expect(last.hasAttribute('disabled')).to.equal(true);
        (last as TestEl).click();
        await elementUpdated(modal!);
        expect(qs(modal!.renderRoot, '.workspace').getAttribute('data-inspector')).to.equal('on');
        expect(getComputedStyle(qs(modal!.renderRoot, '.inspector')).display).to.not.equal('none');
    });

    it('restores saved panel visibility when the editor opens', async () => {
        localStorage.setItem(PANELS_KEY, JSON.stringify({ preview: true, source: false, inspector: false }));
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        expect(qs(modal!.renderRoot, '.workspace').getAttribute('data-source')).to.equal('off');
        expect(qs(modal!.renderRoot, '.workspace').getAttribute('data-inspector')).to.equal('off');
        expect(getComputedStyle(qs(modal!.renderRoot, '.pane')).display).to.equal('none');
        expect(getComputedStyle(qs(modal!.renderRoot, '.inspector')).display).to.equal('none');
        expect(getComputedStyle(qs(modal!.renderRoot, '.preview-pane')).display).to.not.equal('none');
    });

    it('clips the sandbox iframe so it does not paint over the inspector', async () => {
        const source = T.default_text_html_source;
        const modal = await openModal({
            source,
            block: { ...BLOCK, source, fields: ['items'] },
            sampleState: JSON.parse(T.html_example_state),
            statePaths: ['title'],
            onApply: () => {},
        });
        await waitPreview(modal);
        const workspace = qs(modal!.renderRoot, '.workspace');
        if (workspace.getBoundingClientRect().height < 200) {
            workspace.style.height = '640px';
            workspace.style.width = '960px';
        }
        await elementUpdated(modal!);
        const stage = qs(modal!.renderRoot, '.stage');
        const panes = qs(modal!.renderRoot, '.panes');
        const inspector = qs(modal!.renderRoot, '.inspector');
        const iframe = qs(qs(modal!.renderRoot, 'flow-ui-html-block').renderRoot, 'iframe');
        expect(stage.getBoundingClientRect().height, 'stage has layout height').to.be.greaterThan(40);
        expect(inspector.getBoundingClientRect().height, 'inspector has layout height').to.be.greaterThan(40);
        expect(panes.getBoundingClientRect().bottom).to.be.at.most(inspector.getBoundingClientRect().top + 1);
        expect(rectsOverlap(panes.getBoundingClientRect(), inspector.getBoundingClientRect())).to.equal(false);
        expect(getComputedStyle(stage).overflow).to.equal('hidden');
        expect(getComputedStyle(qs(modal!.renderRoot, '.stage .frame')).overflowY).to.match(/auto|scroll/);
        expect(getComputedStyle(panes).overflow).to.equal('hidden');
        expect(getComputedStyle(inspector).overflow).to.equal('hidden');
        expect(Number.parseInt(getComputedStyle(inspector).zIndex, 10)).to.be.at.least(1);
        const bg = getComputedStyle(inspector).backgroundColor;
        expect(bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent', `inspector background ${bg}`).to.equal(false);
        const box = inspector.getBoundingClientRect();
        const hit = document.elementFromPoint(box.left + Math.min(24, box.width / 2), box.top + 16);
        expect(hit, 'inspector hit target').to.exist;
        expect(hit!.tagName.toLowerCase(), 'preview iframe must not sit on the inspector').to.not.equal('iframe');
        expect(iframe.getBoundingClientRect().width).to.be.greaterThan(0);
    });

    it('scrolls a tall sandbox preview inside the stage frame', async () => {
        const source = '<p data-bind="title"></p><div style="height:800px">pad</div>';
        const modal = await openModal({
            source,
            block: { ...BLOCK, source },
            sampleState: SAMPLE_STATE,
            statePaths: ['title'],
            onApply: () => {},
        });
        await waitPreview(modal);
        const workspace = qs(modal!.renderRoot, '.workspace');
        if (workspace.getBoundingClientRect().height < 200) {
            workspace.style.height = '640px';
            workspace.style.width = '960px';
        }
        await elementUpdated(modal!);
        const frame = qs(modal!.renderRoot, '.stage .frame');
        expect(getComputedStyle(frame).overflowY).to.match(/auto|scroll/);
        await waitUntil(() => frame.scrollHeight > frame.clientHeight + 20, 'preview frame did not become scrollable', { timeout: 4000 });
        frame.scrollTop = 120;
        expect(frame.scrollTop).to.be.greaterThan(0);
    });

    it('sets the canvas frame width from the viewport control', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        await clickSegment(qs(modal!.renderRoot, '.viewport-control'), 'mobile');
        await elementUpdated(modal!);
        expect(qs(modal!.renderRoot, '.stage').getAttribute('style')).to.contain(`${HTML_EDITOR_VIEWPORTS.mobile}px`);
    });

    it('applies the light theme to the stage and pushes tokens into the sandbox', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const preview = await waitPreview(modal);
        let pushed = 0;
        const inner = preview.pushHost.bind(preview);
        preview.pushHost = (...args: any[]) => {
            pushed += 1;
            return inner(...args);
        };
        await clickSegment(qs(modal!.renderRoot, '.theme-control'), 'light');
        await elementUpdated(modal!);
        await waitUntil(() => qs(modal!.renderRoot, '.stage').getAttribute('data-theme') === 'light', 'stage theme did not switch');
        await waitUntil(() => pushed > 0, 'pushHost was not called after theme click');
        expect(getComputedStyle(qs(modal!.renderRoot, '.stage')).getPropertyValue('--flow-ui-text').trim()).to.equal('#1c1f2e');
    });

    it('reloads the sandbox iframe from the preview toolbar', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const preview = await waitPreview(modal);
        const seq = preview._reloadSeq;
        qs(modal!.renderRoot, '[data-reload]').click();
        await elementUpdated(modal!);
        expect(preview._reloadSeq).to.equal(seq + 1);
        await waitUntil(
            () => (q(preview.renderRoot, 'iframe')?.srcdoc || '').includes(`<!--r${seq + 1}-->`),
            'reload did not rewrite srcdoc',
            { timeout: 4000 },
        );
    });

    it('stores the split layout from the source toolbar', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        expect(qs(modal!.renderRoot, '.workspace').getAttribute('data-layout')).to.equal('preview');
        await clickSegment(qs(modal!.renderRoot, '.layout-control'), 'split');
        await elementUpdated(modal!);
        expect(qs(modal!.renderRoot, '.workspace').getAttribute('data-layout')).to.equal('split');
        expect(localStorage.getItem(LAYOUT_KEY)).to.equal('split');
    });

    it('inserts a snippet from the popover at the caret and merges test-state', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const before = modal!._draft;
        qs(modal!.renderRoot, '.snippets-trigger').click();
        await elementUpdated(modal!);
        await waitUntil(() => q(modal!.renderRoot, '.snippets-popover')?.matches(':popover-open'), 'snippets popover did not open');
        qs(modal!.renderRoot, '.snippets [data-snippet="bind"]').click();
        await elementUpdated(modal!);
        expect(modal!._draft).to.contain(before);
        expect(modal!._draft).to.contain('data-bind="title"');
        expect(JSON.parse(modal!._stateText).title).to.equal('Order #1042');
        expect(JSON.parse(modal!._stateText).order).to.deep.equal({ total: 42 });
        expect(modal!._snippetsOpen).to.equal(false);
    });

    it('fills an empty preview from an overlay snippet card', async () => {
        const modal = await openModal({
            source: '',
            block: { ...BLOCK, source: '' },
            sampleState: {},
            statePaths: [],
            onApply: () => {},
        });
        const overlay = qs(modal!.renderRoot, '.overlay[data-kind="empty"]');
        expect(overlay, 'empty overlay').to.exist;
        qs(overlay!, '[data-snippet="bind"]').click();
        await elementUpdated(modal!);
        expect(modal!._draft).to.contain('data-bind="title"');
        expect(q(modal!.renderRoot, '.overlay[data-kind="empty"]')).to.equal(null);
    });

    it('replace-all writes the starter example; apply hands the draft back', async () => {
        let applied = null;
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: {}, statePaths: [], onApply: (source: any) => { applied = source; } });
        qs(modal!.renderRoot, '.source-toolbar [data-replace]').click();
        await elementUpdated(modal!);
        expect(modal!._draft).to.equal(T.default_text_html_source);
        expect(modal!._draft).to.contain('flowUi.onChange(').and.contain('flowUi.send(').and.contain('flowUi.setValue(').and.contain('data-bind=').and.contain('data-show=');
        expect(JSON.parse(modal!._stateText)).to.deep.equal(JSON.parse(T.html_example_state));
        qs(modal!.renderRoot, '.modal-actions platform-button[primary]').click();
        expect(applied).to.equal(T.default_text_html_source);
    });

    it('asks before replace-all when the draft is dirty', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: {}, statePaths: [], onApply: () => {} });
        emitChange(qs(modal!.renderRoot, 'platform-code-editor[data-html-source]'), `${BLOCK.source}\n<!-- dirty -->`);
        await elementUpdated(modal!);
        qs(modal!.renderRoot, '.source-toolbar [data-replace]').click();
        await elementUpdated(modal!);
        expect(modal!._replaceConfirm).to.equal(true);
        expect(modal!._draft).to.contain('<!-- dirty -->');
        qs(modal!.renderRoot, '[data-replace-yes]').click();
        await elementUpdated(modal!);
        expect(modal!._draft).to.equal(T.default_text_html_source);
    });

    it('updates the live preview after the source debounce', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const preview = await waitPreview(modal);
        const next = `${modal!._draft}\n<!-- live-marker -->`;
        emitChange(qs(modal!.renderRoot, 'platform-code-editor[data-html-source]'), next);
        expect(modal!._liveSource).to.not.contain('live-marker');
        await waitUntil(() => modal!._liveSource.includes('live-marker'), 'live source did not debounce', { timeout: HTML_EDITOR_LIVE_MS + 800 });
        await elementUpdated(modal!);
        await waitUntil(
            () => (q(preview.renderRoot, 'iframe')?.srcdoc || '').includes('live-marker'),
            'preview srcdoc did not pick up the live draft',
            { timeout: 4000 },
        );
    });

    it('switches inspector tabs from the segmented control', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        await clickInspectorTab(modal, 'events');
        expect(qs(modal!.renderRoot, '.log'), 'events log').to.exist;
        await clickInspectorTab(modal, 'help');
        expect(qs(modal!.renderRoot, '.sheet'), 'help sheet').to.exist;
        await clickInspectorTab(modal, 'state');
        expect(qs(modal!.renderRoot, '.state-mode'), 'state mode').to.exist;
    });

    it('writes a field change into the test state used by the preview', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const field = [...qsa(modal!.renderRoot, '.inspector platform-field')].find((item) => item.label === 'title');
        expect(field, 'title field').to.exist;
        emitChange(field, 'Shipped');
        await elementUpdated(modal!);
        expect(modal!._lastGoodState.title).to.equal('Shipped');
        const preview = qs(modal!.renderRoot, 'flow-ui-html-block');
        expect(preview.state.title).to.equal('Shipped');
    });

    it('keeps the last-good preview when the test state JSON is invalid and accepts a later valid object', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const preview = qs(modal!.renderRoot, '.stage flow-ui-html-block');
        expect(preview, 'preview before invalid JSON').to.exist;
        await clickSegment(qs(modal!.renderRoot, '.state-mode'), 'json');
        await elementUpdated(modal!);
        const json = qs(modal!.renderRoot, '.inspector platform-code-editor');
        emitChange(json, '{ not json');
        await elementUpdated(modal!);
        expect(qs(modal!.renderRoot, '.stage flow-ui-html-block'), 'preview stays mounted').to.equal(preview);
        expect(modal!._stateError).to.not.equal('');
        expect(qs(modal!.renderRoot, '.badge').textContent).to.contain(T.html_state_invalid);
        expect(modal!._lastGoodState).to.deep.equal({ items: null, title: 'Hello', order: { total: 42 } });
        emitChange(json, JSON.stringify({ items: null, title: 'From JSON', order: { total: 42 } }));
        await elementUpdated(modal!);
        expect(modal!._stateError).to.equal('');
        expect(modal!._lastGoodState.title).to.equal('From JSON');
    });

    it('logs sandbox send events and clears them from the events tab', async () => {
        const source = '<script>flowUi.onChange((state) => { if (state.ready) flowUi.send("submit", { source: "html" }); });</script>';
        const modal = await openModal({
            source,
            block: { ...BLOCK, source, fields: ['ready'] },
            sampleState: { ready: 'yes' },
            statePaths: [],
            onApply: () => {},
        });
        await waitPreview(modal);
        await waitUntil(() => modal!._log.some((entry: any) => entry.kind === 'action')!, 'send did not reach the editor log', { timeout: 4000 });
        await clickInspectorTab(modal, 'events');
        expect(qs(modal!.renderRoot, '.log .entry[data-kind="action"]').textContent).to.contain('send("submit"');
        qs(modal!.renderRoot, '[data-log-clear]').click();
        await elementUpdated(modal!);
        expect(modal!._log).to.deep.equal([]);
        expect(qs(modal!.renderRoot, '.log .empty')).to.exist;
    });

    it('inserts a theme token from the help chips into the source', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        await clickInspectorTab(modal, 'help');
        qs(modal!.renderRoot, '[data-token="--flow-ui-accent"]').click();
        await elementUpdated(modal!);
        expect(modal!._draft).to.contain('var(--flow-ui-accent)');
    });

    it('marks Apply dirty, writes the draft, and leaves Cancel without applying', async () => {
        let applied = null;
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: {}, statePaths: [], onApply: (source: any) => { applied = source; } });
        emitChange(qs(modal!.renderRoot, 'platform-code-editor[data-html-source]'), `${BLOCK.source}\n<!-- applied -->`);
        await elementUpdated(modal!);
        const apply = q(modal!.renderRoot, '.modal-actions platform-button[primary]');
        expect(q(apply!, '.dirty'), 'dirty marker').to.exist;
        expect(typeof qs(modal!.renderRoot, 'platform-code-editor[data-html-source]').extensionsFactory).to.equal('function');
        qs(modal!.renderRoot, '.modal-actions platform-button[ghost]').click();
        expect(applied).to.equal(null);

        const again = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: {}, statePaths: [], onApply: (source: any) => { applied = source; } });
        emitChange(qs(again!.renderRoot, 'platform-code-editor[data-html-source]'), `${BLOCK.source}\n<!-- applied -->`);
        await elementUpdated(again!);
        qs(again!.renderRoot, '.modal-actions platform-button[primary]').click();
        expect(applied).to.equal(`${BLOCK.source}\n<!-- applied -->`);
    });

    it('disables Apply when the source is empty', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: {}, statePaths: [], onApply: () => {} });
        emitChange(qs(modal!.renderRoot, 'platform-code-editor[data-html-source]'), '');
        await elementUpdated(modal!);
        const apply = qs(modal!.renderRoot, '.modal-actions platform-button[primary]');
        expect(apply.hasAttribute('disabled')).to.equal(true);
        expect(apply.getAttribute('title')).to.equal(T.html_apply_empty);
    });

    it('renders the starter example in the sandbox with a visible card', async () => {
        const source = T.default_text_html_source;
        const modal = await openModal({
            source,
            block: { ...BLOCK, source, fields: ['items'] },
            sampleState: JSON.parse(T.html_example_state),
            statePaths: ['title'],
            onApply: () => {},
        });
        const preview = await waitPreview(modal);
        expect(qs(preview.renderRoot, 'iframe').srcdoc).to.contain('class="card"');
    });

    it('sizes the sandbox preview after the modal portals to document.body', async () => {
        const source = '<p data-bind="title"></p><div style="height:80px">pad</div>';
        const modal = await openModal({
            source,
            block: { ...BLOCK, source },
            sampleState: SAMPLE_STATE,
            statePaths: ['title'],
            onApply: () => {},
        });
        const preview = await waitPreview(modal);
        expect(qs(preview.renderRoot, 'iframe').srcdoc).to.contain('data-bind="title"');
        expect(qs(preview.renderRoot, 'iframe').srcdoc).to.contain('--flow-ui-text:');
        expect(q(modal!.renderRoot, '.overlay[data-kind="empty"]')).to.equal(null);
    });

    it('keeps the source and JSON editors writable', async () => {
        const modal = await openModal({ source: BLOCK.source, block: BLOCK, sampleState: SAMPLE_STATE, statePaths: [], onApply: () => {} });
        const source = qs(modal!.renderRoot, 'platform-code-editor[data-html-source]');
        expect(source.readonly, 'html source editor must be writable').to.equal(false);
        await clickSegment(qs(modal!.renderRoot, '.state-mode'), 'json');
        await elementUpdated(modal!);
        const json = qs(modal!.renderRoot, '.inspector platform-code-editor');
        expect(json, 'json editor').to.exist;
        expect(json.readonly, 'json state editor must be writable').to.equal(false);
        source.insertAtCursor('<!-- typed -->');
        await elementUpdated(modal!);
        expect(modal!._draft).to.contain('<!-- typed -->');
    });

    it('hydrates the code editor from block.source when the source prop is empty', async () => {
        const source = T.html_snippet_bind_source;
        const modal = await openModal({
            source: '',
            block: { ...BLOCK, source },
            sampleState: {},
            statePaths: [],
            onApply: () => {},
        });
        expect(modal!._draft).to.equal(source);
        expect(qs(modal!.renderRoot, 'platform-code-editor[data-html-source]').value).to.equal(source);
        expect(q(modal!.renderRoot, '.overlay[data-kind="empty"]')).to.equal(null);
    });

    it('keeps a finished snippet in the code editor after the modal portals', async () => {
        const source = T.default_text_html_source;
        const modal = await openModal({
            source,
            block: { ...BLOCK, source, fields: ['items'] },
            sampleState: {},
            statePaths: [],
            onApply: () => {},
        });
        expect(modal!.hasAttribute('data-portal')).to.equal(true);
        expect(modal!._draft).to.equal(source);
        expect(qs(modal!.renderRoot, 'platform-code-editor[data-html-source]').value).to.equal(source);
    });
});
