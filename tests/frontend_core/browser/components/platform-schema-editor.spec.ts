/**
 * platform-schema-editor — Form/JSON dual-mode smoke + emit contract.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/schema/platform-schema-editor.js';
import {q, qs, shadow, type TestEl} from '../helpers/dom.js';

describe('platform-schema-editor', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('Form mode renders empty state and emits on add parameter', async () => {
        const el = await fixture<TestEl>(html`
            <platform-schema-editor .value=${{ type: 'object', properties: {} }}></platform-schema-editor>
        `);
        await elementUpdated(el);
        expect(qs(shadow(el), '.empty')).to.exist;
        const addBtn = qs(shadow(el), 'platform-button');
        expect(addBtn).to.exist;
        setTimeout(() => (addBtn as TestEl).click());
        const ev = await oneEvent(el, 'schema-change');
        expect((ev as CustomEvent).detail.valid).to.equal(true);
        expect((ev as CustomEvent).detail.value).to.have.property('type', 'object');
        expect((ev as CustomEvent).detail.value).to.have.property('properties');
        await elementUpdated(el);
        expect(qs(shadow(el), 'platform-schema-parameter-card')).to.exist;
    });

    it('advanced schema forces JSON mode and shows banner', async () => {
        const el = await fixture<TestEl>(html`
            <platform-schema-editor
                .value=${{
                    type: 'object',
                    $defs: { Lane: { type: 'string', enum: ['text'] } },
                    properties: { lane: { $ref: '#/$defs/Lane' } },
                }}
            ></platform-schema-editor>
        `);
        await elementUpdated(el);
        expect(q(shadow(el), '.banner')).to.exist;
        expect(q(shadow(el), 'platform-json-editor')).to.exist;
        expect(q(shadow(el), 'platform-schema-parameter-card')).to.not.exist;
    });

    it('Form edits emit schema-change with required + description', async () => {
        const el = await fixture<TestEl>(html`
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
        const card = qs(shadow(el), 'platform-schema-parameter-card');
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
        expect((ev as CustomEvent).detail.valid).to.equal(true);
        expect((ev as CustomEvent).detail.value.properties.query.description).to.equal('Search query');
        expect((ev as CustomEvent).detail.value.required).to.deep.equal(['query']);
    });
});
