import { fixture, fixtureCleanup, html, expect, nextFrame } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-date-picker.js';
import '../../../../apps/flows/ui/components/editors/flows-searchable-combobox.js';

describe('flows filters field height canon', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });
    afterEach(() => fixtureCleanup());

    it('labeled compact filter controls share the same height', async () => {
        const el = await fixture(html`
            <div
                style="
                    --field-pill-bg: rgba(15, 23, 42, 0.04);
                    --field-pill-border: rgba(15, 23, 42, 0.06);
                    --field-pill-radius: 18px;
                    --field-pill-padding-y: 14px;
                    --field-pill-padding-x: 18px;
                    --field-pill-gap: 8px;
                    --field-pill-label-size: 11px;
                    --field-pill-label-line: 1.1;
                    --field-pill-label-weight: 600;
                    --field-pill-label-letter: 0.04em;
                    --field-pill-input-size: 17px;
                    --field-pill-input-weight: 600;
                    --field-pill-input-line: 1.45;
                    --field-pill-compact-padding-y: 6px;
                    --field-pill-compact-padding-x: 12px;
                    --field-pill-compact-radius: 12px;
                    --field-pill-compact-gap: 4px;
                    --field-pill-compact-input-size: 13px;
                    --field-pill-compact-input-weight: 500;
                    --field-pill-number-spin-height: 40px;
                    display: flex;
                    gap: 8px;
                    align-items: flex-start;
                    width: 960px;
                "
            >
                <flows-searchable-combobox
                    compact
                    .label=${'user_id'}
                    .placeholder=${'user_id'}
                ></flows-searchable-combobox>
                <platform-field
                    type="string"
                    mode="edit"
                    pill-density="compact"
                    .label=${'branch_id'}
                    .placeholder=${'branch_id'}
                ></platform-field>
                <platform-date-picker
                    compact
                    mode="datetime"
                    .label=${'Создано от'}
                ></platform-date-picker>
            </div>
        `);
        await nextFrame();

        const controls = [
            el.querySelector('flows-searchable-combobox'),
            el.querySelector('platform-field'),
            el.querySelector('platform-date-picker'),
        ];
        const heights = controls.map((control) => control.getBoundingClientRect().height);
        const delta = Math.max(...heights) - Math.min(...heights);
        expect(delta).to.be.lessThan(1);
    });
});
