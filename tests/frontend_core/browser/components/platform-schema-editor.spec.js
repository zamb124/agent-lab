/**
 * platform-schema-editor — Form/JSON dual-mode smoke + emit contract.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/schema/platform-schema-editor.js';

describe('platform-schema-editor', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('Form mode renders empty state and emits on add parameter', async () => {
        const el = await fixture(html`
            <platform-schema-editor .value=${{ type: 'object', properties: {} }}></platform-schema-editor>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.empty')).to.exist;
        const addBtn = el.shadowRoot.querySelector('platform-button');
        expect(addBtn).to.exist;
        setTimeout(() => addBtn.click());
        const ev = await oneEvent(el, 'schema-change');
        expect(ev.detail.valid).to.equal(true);
        expect(ev.detail.value).to.have.property('type', 'object');
        expect(ev.detail.value).to.have.property('properties');
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('platform-schema-parameter-card')).to.exist;
    });

    it('advanced schema forces JSON mode and shows banner', async () => {
        const el = await fixture(html`
            <platform-schema-editor
                .value=${{
                    type: 'object',
                    $defs: { Lane: { type: 'string', enum: ['text'] } },
                    properties: { lane: { $ref: '#/$defs/Lane' } },
                }}
            ></platform-schema-editor>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.banner')).to.exist;
        expect(el.shadowRoot.querySelector('platform-json-editor')).to.exist;
        expect(el.shadowRoot.querySelector('platform-schema-parameter-card')).to.not.exist;
    });

    it('Form edits emit schema-change with required + description', async () => {
        const el = await fixture(html`
            <platform-schema-editor
                .value=${{
                    type: 'object',
                    properties: {
                        query: { type: 'string', description: 'q' },
                    },
                    required: ['query'],
                }}
            ></platform-schema-editor>
        `);
        await elementUpdated(el);
        const card = el.shadowRoot.querySelector('platform-schema-parameter-card');
        expect(card).to.exist;
        setTimeout(() => {
            card.dispatchEvent(
                new CustomEvent('row-change', {
                    detail: {
                        index: 0,
                        row: {
                            key: 'query',
                            required: true,
                            uiType: 'string',
                            description: 'Search query',
                            enumValues: [],
                            itemsUiType: 'string',
                            itemsEnumValues: [],
                            nestedRows: [],
                            extra: {},
                        },
                    },
                    bubbles: true,
                    composed: true,
                }),
            );
        });
        const ev = await oneEvent(el, 'schema-change');
        expect(ev.detail.valid).to.equal(true);
        expect(ev.detail.value.properties.query.description).to.equal('Search query');
        expect(ev.detail.value.required).to.deep.equal(['query']);
    });
});
