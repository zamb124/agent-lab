/**
 * platform-viz-host: switches to mermaid/echarts child hosts from document prop.
 * Does not wait for engine script load — asserts host wiring only.
 */

import {
    fixture,
    fixtureCleanup,
    html,
    expect,
    elementUpdated,
} from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-viz-host.js';
import {q, qs, shadow, type TestEl} from '../helpers/dom.js';

const MERMAID_DOC = {
    schema_version: 1,
    kind: 'flowchart',
    engine: 'mermaid',
    title: 'Flow',
    spec: { source: 'flowchart TD\n  A-->B' },
};

const ECHARTS_DOC = {
    schema_version: 1,
    kind: 'chart',
    engine: 'echarts',
    title: 'Bars',
    spec: {
        option: {
            xAxis: { type: 'category', data: ['A'] },
            yAxis: { type: 'value' },
            series: [{ type: 'bar', data: [1] }],
        },
    },
};

describe('platform-viz-host', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('renders platform-mermaid-host for mermaid document', async () => {
        const el = await fixture<TestEl>(html`
            <platform-viz-host .document=${MERMAID_DOC}></platform-viz-host>
        `);
        await elementUpdated(el);
        const child = q(shadow(el), 'platform-mermaid-host');
        expect(child).to.exist;
        expect(q(shadow(el), 'platform-echarts-host')).to.not.exist;
        expect(q(shadow(el), '.title')?.textContent).to.equal('Flow');
    });

    it('renders platform-echarts-host for echarts document', async () => {
        const el = await fixture<TestEl>(html`
            <platform-viz-host .document=${ECHARTS_DOC}></platform-viz-host>
        `);
        await elementUpdated(el);
        const child = q(shadow(el), 'platform-echarts-host');
        expect(child).to.exist;
        expect(q(shadow(el), 'platform-mermaid-host')).to.not.exist;
    });

    it('compact hides toolbar', async () => {
        const el = await fixture<TestEl>(html`
            <platform-viz-host compact .document=${MERMAID_DOC}></platform-viz-host>
        `);
        await elementUpdated(el);
        expect(el.compact).to.equal(true);
        expect(q(shadow(el), '.toolbar')).to.not.exist;
        expect(q(shadow(el), 'platform-mermaid-host')).to.exist;
    });
});
