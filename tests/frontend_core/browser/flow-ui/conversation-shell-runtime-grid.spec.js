/**
 * Runtime must force conversation flex shell even when the persisted document
 * lost presentation=conversation and was editor-promoted to grid (Lara blank UI).
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';
import { gridLayout } from '@platform/lib/flow-ui/templates/component-factory.js';
import { cloneSerializable } from '@platform/lib/flow-ui/utils/clone.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';

describe('flow-ui conversation shell runtime grid strip', () => {
    afterEach(() => fixtureCleanup());

    async function mountConversation(document, profile) {
        const el = await fixture(html`
            <div style="height:640px;width:480px;display:flex;flex-direction:column;overflow:hidden">
                <platform-flow-ui
                    style="flex:1 1 0;min-height:0;height:100%"
                    display="page"
                    profile=${profile}
                    theme="dark"
                    locale="ru"
                    .initialDocument=${document}
                ></platform-flow-ui>
            </div>
        `);
        const flowUi = el.querySelector('platform-flow-ui');
        await new Promise((resolve) => setTimeout(resolve, 80));
        await elementUpdated(flowUi);
        const surface = flowUi.shadowRoot.querySelector('flow-ui-surface');
        await elementUpdated(surface);
        return { flowUi, surface };
    }

    it('forces page-shell--conversation flex when root is grid without presentation', async () => {
        const document = cloneSerializable(buildDefaultChatDocument({ greetingMessage: '' }));
        const root = document.surfaces.main.components.root;
        // Mimic Lara durable doc after interface-editor promote-to-grid + stripped presentation.
        root.properties = {};
        root.container_layout = gridLayout({ compact: 4, medium: 8, wide: 12 });
        document.surfaces.main.components.header.properties = {};

        const { flowUi, surface } = await mountConversation(document, 'spa');
        const shell = surface.shadowRoot.querySelector('[data-flow-ui-component="root"]');
        expect(shell).to.exist;
        expect(shell.classList.contains('page-shell--conversation')).to.equal(true);
        expect(shell.classList.contains('flow-grid')).to.equal(false);
        expect(getComputedStyle(shell).display).to.equal('flex');

        const headerSection = surface.shadowRoot.querySelector(
            '[data-flow-ui-component="header"] section',
        );
        expect(headerSection?.classList.contains('section--chat-header')).to.equal(true);

        const composer = surface.shadowRoot.querySelector('.field-group--composer');
        expect(composer).to.exist;
        expect(composer.clientHeight).to.be.greaterThan(20);
        const viewport = flowUi.shadowRoot.querySelector('.viewport');
        expect(composer.getBoundingClientRect().bottom)
            .to.be.lessThanOrEqual(viewport.getBoundingClientRect().bottom + 2);
        // Composer pinned near the bottom of the tall viewport (not stuck under Share).
        expect(composer.getBoundingClientRect().top)
            .to.be.greaterThan(viewport.getBoundingClientRect().top + 120);
    });

    it('forces flex conversation shell in editor_test even with message-form at row 11', async () => {
        const document = cloneSerializable(buildDefaultChatDocument({ greetingMessage: '' }));
        const root = document.surfaces.main.components.root;
        root.container_layout = gridLayout({ compact: 4, medium: 8, wide: 12 });
        document.surfaces.main.components['message-form'].placement = {
            base: {
                column_start: 1,
                column_span: 'full',
                row_start: 11,
                row_span: 1,
                order: 0,
                align_self: 'auto',
                justify_self: 'auto',
            },
            overrides: {},
        };

        const { flowUi, surface } = await mountConversation(document, 'editor_test');
        const shell = surface.shadowRoot.querySelector('[data-flow-ui-component="root"]');
        expect(shell.classList.contains('flow-grid')).to.equal(false);
        expect(getComputedStyle(shell).display).to.equal('flex');
        expect(getComputedStyle(shell).gridTemplateRows).to.equal('none');

        const feed = surface.shadowRoot.querySelector(
            '[data-flow-ui-component="conversation"]',
        );
        const composer = surface.shadowRoot.querySelector('.field-group--composer');
        const viewport = flowUi.shadowRoot.querySelector('.viewport');
        expect(feed).to.exist;
        expect(composer).to.exist;
        expect(composer.getBoundingClientRect().bottom)
            .to.be.lessThanOrEqual(viewport.getBoundingClientRect().bottom + 2);
        expect(composer.getBoundingClientRect().top)
            .to.be.greaterThan(feed.getBoundingClientRect().bottom - 1);
    });
});
