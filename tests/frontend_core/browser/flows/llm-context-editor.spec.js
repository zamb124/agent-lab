/**
 * Smoke: platform-llm-context-editor — compact context policy editor.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { renderResourceDefinitionEditor } from '../../../../apps/flows/ui/components/editor/flows-resource-definition-editor-surface.js';
import '../../../../core/frontend/static/lib/components/llm/llm-context-editor.js';

describe('platform-llm-context-editor', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    afterEach(() => fixtureCleanup());

    it('рендерит четыре базовых настройки', async () => {
        const el = await fixture(html`
            <platform-llm-context-editor
                .config=${{ profile: 'standard', memory: 'session', retrieval: { mode: 'hybrid' }, budget: 'medium' }}
                .profiles=${['standard', 'enterprise']}
                .budgets=${['medium', 'enterprise']}
            ></platform-llm-context-editor>
        `);
        await elementUpdated(el);

        const fields = el.shadowRoot.querySelectorAll('platform-field');
        expect(fields.length).to.equal(4);
        expect(fields[0].type).to.equal('enum');
        expect(fields[0].config.values.some((item) => item.value === 'enterprise')).to.equal(true);
        expect(fields[3].config.values.some((item) => item.value === 'enterprise')).to.equal(true);
        expect(fields[3].value).to.equal('medium');
    });

    it('advanced открывает числовые поля и режимы сжатия/кэша', async () => {
        const el = await fixture(html`
            <platform-llm-context-editor .config=${{ retrieval: { top_k: 16, min_score: 0.7 } }}></platform-llm-context-editor>
        `);
        await elementUpdated(el);

        el.shadowRoot.querySelector('glass-button').click();
        await elementUpdated(el);

        const fields = Array.from(el.shadowRoot.querySelectorAll('platform-field'));
        expect(fields.length).to.equal(18);
        expect(fields.some((field) => field.type === 'integer' && field.value === 16)).to.equal(true);
        expect(fields.some((field) => field.type === 'number' && field.value === 0.7)).to.equal(true);
        expect(fields.filter((field) => field.type === 'integer')).to.have.lengthOf(9);
        expect(fields.filter((field) => field.type === 'boolean')).to.have.lengthOf(1);
    });

    it('advanced пишет точные token budget override без отдельного UI-контракта', async () => {
        const el = await fixture(html`
            <platform-llm-context-editor .config=${{ budget: 'large' }}></platform-llm-context-editor>
        `);
        await elementUpdated(el);

        let last = null;
        el.addEventListener('change', (e) => {
            last = e.detail.config;
        });

        el._setBudget('active_window_tokens', 12000);
        expect(last).to.deep.equal({ budget: { active_window_tokens: 12000 } });

        el.config = last;
        await elementUpdated(el);
        el._setBudget('active_window_tokens', null);
        expect(last).to.deep.equal({});

        el.config = last;
        await elementUpdated(el);
        el._onBudgetNumber('max_input_tokens')({ detail: { value: 0 } });
        expect(last).to.deep.equal({ budget: { max_input_tokens: 1 } });
    });

    it('rerank включает hybrid retrieval, если поиск был выключен', async () => {
        const el = await fixture(html`
            <platform-llm-context-editor .config=${{ retrieval: { mode: 'off' } }}></platform-llm-context-editor>
        `);
        await elementUpdated(el);

        let last = null;
        el.addEventListener('change', (e) => {
            last = e.detail.config;
        });

        el._setRetrieval('rerank', true);

        expect(last).to.deep.equal({ retrieval: { mode: 'hybrid', rerank: true } });
    });

    it('resource surface роутит llm_context в специализированный редактор', async () => {
        const host = await fixture(html`
            <div>
                ${renderResourceDefinitionEditor(
                    { resource_id: 'ctx', type: 'llm_context', name: 'Context', config: { profile: 'agent' } },
                    () => {},
                )}
            </div>
        `);
        await elementUpdated(host);

        const editor = host.querySelector('flows-llm-context-resource-editor');
        expect(editor).to.not.be.null;
        await elementUpdated(editor);
        expect(editor.shadowRoot.querySelector('platform-llm-context-editor')).to.not.be.null;
    });
});
