/**
 * Evaluation layout rhythm — side panel width aligned with CRM Networkle (324px).
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../apps/flows/ui/components/evaluation/flows-evaluation-suite-sidebar.js';
import '../../../../apps/flows/ui/components/evaluation/flows-evaluation-results-matrix.js';
import {q, qs, shadow, type TestEl} from '../helpers/dom.js';

describe('flows evaluation layout rhythm', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('evaluation sidebar rail uses side-panel width token at 1440px viewport', async () => {
        const wrap = await fixture<TestEl>(html`
            <div style="width: 1440px; --flows-side-panel-width: 324px; --flows-side-panel-min-width: 320px;">
                <flows-evaluation-suite-sidebar
                    .suites=${[{ suite_id: 's1', name: 'Suite' }]}
                    .cases=${[]}
                    .catalog=${[]}
                    selected-suite-id="s1"
                ></flows-evaluation-suite-sidebar>
            </div>
        `);
        await elementUpdated(wrap);

        const sidebar = qs(wrap!, 'flows-evaluation-suite-sidebar');
        const rail = qs(shadow(sidebar)!, '.rail');
        expect(rail).to.not.equal(null);

        const width = rail!.getBoundingClientRect().width;
        expect(width).to.be.at.least(320);
        expect(width).to.be.closeTo(324, 4);
    });

    it('results matrix case column matches side-panel width token', async () => {
        const wrap = await fixture<TestEl>(html`
            <div style="width: 1440px; --flows-side-panel-width: 324px; --flows-side-panel-min-width: 320px;">
                <flows-evaluation-results-matrix
                    .matrix=${{
                        cases: [{ case_id: 'c1', name: 'Case', tags: [] }],
                        runs: [{ run_id: 'run-abc12345', state: 'passed', average_score: 1 }],
                        cells: [],
                    }}
                    selected-run-id="run-abc12345"
                ></flows-evaluation-results-matrix>
            </div>
        `);
        await elementUpdated(wrap);

        const matrix = qs(wrap!, 'flows-evaluation-results-matrix');
        const caseCell = qs(shadow(matrix)!, '.case-cell');
        expect(caseCell).to.not.equal(null);

        const width = caseCell!.getBoundingClientRect().width;
        expect(width).to.be.at.least(320);
        expect(width).to.be.closeTo(324, 4);
    });
});
