/**
 * Browser: selection overlay renders handles, insertion slot, structure outlines,
 * and kebab menu trigger on selection / hover.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, oneEvent } from '../helpers/render.js';
import '@platform/lib/flow-ui/editor/selection-overlay.js';

describe('flow-ui selection overlay handles', () => {
    afterEach(() => {
        fixtureCleanup();
    });

    it('renders only allowed resize handles', async () => {
        const el = await fixture(html`
            <flow-ui-selection-overlay
                .rect=${{ x: 40, y: 40, width: 120, height: 80 }}
                label="Card"
                .handles=${['move', 'e', 'w']}
                interactive
            ></flow-ui-selection-overlay>
        `);
        await elementUpdated(el);
        const handles = [...el.shadowRoot.querySelectorAll('.handle')].map(
            (node) => node.getAttribute('data-kind'),
        );
        expect(handles.sort()).to.deep.equal(['e', 'w']);
        expect(el.shadowRoot.querySelector('.box')?.getAttribute('data-locked')).to.equal('false');
    });

    it('hides handles when policy is empty', async () => {
        const el = await fixture(html`
            <flow-ui-selection-overlay
                .rect=${{ x: 10, y: 10, width: 80, height: 40 }}
                label="Root"
                .handles=${[]}
                interactive
            ></flow-ui-selection-overlay>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelectorAll('.handle')).to.have.length(0);
        expect(el.shadowRoot.querySelector('.box')?.getAttribute('data-locked')).to.equal('true');
    });

    it('renders the target cell and structure outlines', async () => {
        const el = await fixture(html`
            <flow-ui-selection-overlay
                .rect=${{ x: 20, y: 20, width: 100, height: 60 }}
                label="a"
                .handles=${['move']}
                .targetCell=${{ x: 0, y: 0, width: 200, height: 300 }}
                .structureRects=${[
                    { componentId: 'a', rect: { x: 20, y: 20, width: 100, height: 60 } },
                    { componentId: 'b', rect: { x: 20, y: 100, width: 100, height: 40 } },
                ]}
                interactive
            ></flow-ui-selection-overlay>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.target-cell')).to.exist;
        expect(el.shadowRoot.querySelector('.target-cell').dataset.valid).to.equal('true');
        expect(el.shadowRoot.querySelectorAll('.structure')).to.have.length(2);
    });

    it('marks an occupied target cell as refused', async () => {
        const el = await fixture(html`
            <flow-ui-selection-overlay
                .rect=${{ x: 20, y: 20, width: 100, height: 60 }}
                label="a"
                .handles=${['move']}
                .targetCell=${{ x: 0, y: 0, width: 200, height: 48 }}
                .targetCellValid=${false}
                interactive
            ></flow-ui-selection-overlay>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.target-cell').dataset.valid).to.equal('false');
    });

    it('renders no structure outlines when host passes empty list', async () => {
        const el = await fixture(html`
            <flow-ui-selection-overlay
                .rect=${{ x: 20, y: 20, width: 100, height: 60 }}
                label="card"
                .handles=${['move']}
                .structureRects=${[]}
                interactive
            ></flow-ui-selection-overlay>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelectorAll('.structure')).to.have.length(0);
        expect(el.shadowRoot.querySelector('.box')).to.exist;
    });

    it('renders kebab on selection and emits component-menu-open', async () => {
        const el = await fixture(html`
            <flow-ui-selection-overlay
                .rect=${{ x: 20, y: 20, width: 100, height: 60 }}
                label="btn"
                .handles=${['move']}
                menuLabel="Component menu"
                interactive
            ></flow-ui-selection-overlay>
        `);
        await elementUpdated(el);
        const kebab = el.shadowRoot.querySelector('.kebab');
        expect(kebab).to.exist;
        expect(kebab.getAttribute('aria-label')).to.equal('Component menu');
        setTimeout(() => kebab.click());
        const event = await oneEvent(el, 'component-menu-open');
        expect(event.detail.componentId).to.equal('btn');
        expect(typeof event.detail.clientX).to.equal('number');
        expect(typeof event.detail.clientY).to.equal('number');
    });

    it('renders kebab on hovered component distinct from selection', async () => {
        const el = await fixture(html`
            <flow-ui-selection-overlay
                .rect=${{ x: 20, y: 20, width: 100, height: 60 }}
                label="root"
                hoveredComponentId="child"
                .handles=${['move']}
                .structureRects=${[
                    { componentId: 'child', rect: { x: 30, y: 80, width: 80, height: 40 } },
                ]}
                interactive
            ></flow-ui-selection-overlay>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelectorAll('.kebab')).to.have.length(2);
    });

    it('hides kebab when menuEnabled is false', async () => {
        const el = await fixture(html`
            <flow-ui-selection-overlay
                .rect=${{ x: 20, y: 20, width: 100, height: 60 }}
                label="btn"
                .handles=${['move']}
                .menuEnabled=${false}
                interactive
            ></flow-ui-selection-overlay>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.kebab')).to.not.exist;
    });
});
