/**
 * platform-cron-field + util cron-field: пресеты, своё выражение, emit.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import {
    findMatchingPresetId,
    getCronForPresetId,
    normalizeCronString,
    validateCronFiveField,
    CRON_FIELD_PRESET_CUSTOM,
} from '@platform/lib/utils/cron-field.js';
import '@platform/lib/components/platform-cron-field.js';

describe('cron-field util', () => {
    it('пресет hourly совпадает с 0 * * * *', () => {
        expect(findMatchingPresetId('0 * * * *')).to.equal('hourly');
        expect(getCronForPresetId('hourly')).to.equal('0 * * * *');
    });

    it('нестандартное выражение — нет пресета', () => {
        expect(findMatchingPresetId('0 */3 * * *')).to.equal(null);
    });

    it('normalizeCronString сжимает пробелы', () => {
        expect(normalizeCronString('  0   9  *  *  *  ')).to.equal('0 9 * * *');
    });

    it('validateCronFiveField: пять токенов', () => {
        expect(validateCronFiveField('0 * * * *')).to.be.true;
        expect(validateCronFiveField('0 * * *')).to.be.false;
    });
});

describe('platform-cron-field', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('смена пресета в select эмитит change с cron hourly', async () => {
        const el = await fixture(
            html`<platform-cron-field .value=${'0 9 * * *'}></platform-cron-field>`,
        );
        const select = el.shadowRoot.querySelector('select.form-select');
        expect(select).to.exist;
        const p = oneEvent(el, 'change');
        select.value = 'hourly';
        select.dispatchEvent(new Event('change', { bubbles: true }));
        const ev = await p;
        expect(ev.detail.value).to.equal('0 * * * *');
    });

    it('нестандартное value показывает поле custom и отображает строку', async () => {
        const customCron = '0 0 * * 2';
        const el = await fixture(
            html`<platform-cron-field .value=${customCron}></platform-cron-field>`,
        );
        await elementUpdated(el);
        const select = el.shadowRoot.querySelector('select.form-select');
        expect(select.value).to.equal(CRON_FIELD_PRESET_CUSTOM);
        const input = el.shadowRoot.querySelector('input.custom');
        expect(input).to.exist;
        expect(input.value).to.equal(customCron);
    });
});
