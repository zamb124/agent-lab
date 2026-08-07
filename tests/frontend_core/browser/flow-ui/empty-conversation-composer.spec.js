/**
 * Empty conversation surface must still show the composer (and not throw).
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import '@platform/lib/flow-ui/components/flow-ui-surface.js';

describe('flow-ui empty conversation composer', () => {
    afterEach(() => {
        fixtureCleanup();
    });

    it('renders composer for default chat document with empty greeting and no tasks', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: '' });
        const surface = document.surfaces.main;
        const host = await fixture(html`
            <div style="height:480px;width:420px;display:flex;flex-direction:column;overflow:hidden">
                <flow-ui-surface
                    style="flex:1 1 0;min-height:0;height:100%"
                    .surface=${surface}
                    .tasks=${[]}
                    locale="ru"
                ></flow-ui-surface>
            </div>
        `);
        await elementUpdated(host);
        const surfaceEl = host.querySelector('flow-ui-surface');
        await elementUpdated(surfaceEl);

        const root = surfaceEl.shadowRoot;
        expect(root).to.exist;
        const shell = root.querySelector('.page-shell--conversation');
        expect(shell).to.exist;
        const composer = root.querySelector('.field-group--composer');
        expect(composer).to.exist;
        expect(composer.clientHeight).to.be.greaterThan(20);
        expect(composer.clientWidth).to.be.greaterThan(100);
        const textarea = root.querySelector('textarea[data-canon="composer"]');
        expect(textarea).to.exist;

        const formNode = root.querySelector('[data-flow-ui-component="message-form"]');
        expect(formNode).to.exist;
        // Composer owns its geometry: Form must not reserve empty CSS-grid rows for
        // file-upload / message-input / submit (that inflated the editor selection box).
        expect(formNode.classList.contains('flow-grid')).to.equal(false);
        expect(formNode.clientHeight).to.be.lessThan(composer.clientHeight + 48);
        expect(formNode.clientHeight).to.be.lessThan(120);
    });

    it('stays compact when Form container_layout was migrated to multi-row grid', async () => {
        const document = buildDefaultChatDocument({ greetingMessage: '' });
        const base = document.surfaces.main;
        const gridLayout = {
            mode: 'grid',
            grid: {
                columns_by_band: { compact: 4, medium: 8, wide: 12 },
                column_gap_token: 'space.4',
                row_gap_token: 'space.4',
                outer_padding_inline_token: 'space.4',
                outer_padding_block_token: 'space.4',
                max_content_width_token: null,
                auto_rows: 'content',
                auto_flow: 'row',
                align_items: 'stretch',
                justify_items: 'stretch',
                baseline_step_token: 'space.1',
            },
            stack: null,
            flex: null,
        };
        function rowPlacement(row) {
            return {
                base: {
                    column_start: 1,
                    column_span: 'full',
                    row_start: row,
                    row_span: 1,
                    order: 0,
                    align_self: 'auto',
                    justify_self: 'auto',
                },
                overrides: {},
            };
        }
        const surface = {
            ...base,
            components: {
                ...base.components,
                'message-form': {
                    ...base.components['message-form'],
                    container_layout: gridLayout,
                },
                'file-upload': {
                    ...base.components['file-upload'],
                    placement: rowPlacement(1),
                },
                'message-input': {
                    ...base.components['message-input'],
                    placement: rowPlacement(2),
                },
                submit: {
                    ...base.components.submit,
                    placement: rowPlacement(3),
                },
            },
        };

        const host = await fixture(html`
            <div style="height:480px;width:420px;display:flex;flex-direction:column;overflow:hidden">
                <flow-ui-surface
                    style="flex:1 1 0;min-height:0;height:100%"
                    .surface=${surface}
                    .tasks=${[]}
                    locale="ru"
                ></flow-ui-surface>
            </div>
        `);
        await elementUpdated(host);
        const surfaceEl = host.querySelector('flow-ui-surface');
        await elementUpdated(surfaceEl);
        const root = surfaceEl.shadowRoot;
        const formNode = root.querySelector('[data-flow-ui-component="message-form"]');
        const composer = root.querySelector('.field-group--composer');
        expect(formNode).to.exist;
        expect(composer).to.exist;
        expect(formNode.classList.contains('flow-grid')).to.equal(false);
        expect(getComputedStyle(formNode).gridTemplateRows).to.equal('none');
        expect(formNode.clientHeight).to.be.lessThan(120);
        expect(formNode.clientHeight).to.be.lessThan(composer.clientHeight + 48);
    });
});
