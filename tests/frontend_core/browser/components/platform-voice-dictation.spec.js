/**
 * platform-voice-dictation — mic UI + platform/voice_dictation op → transcribed event.
 */

import {
    fixture,
    fixtureCleanup,
    html,
    expect,
    elementUpdated,
    oneEvent,
} from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { getPlatformBus } from '@platform/lib/events/index.js';
import { seedPlatformMarkdownEditorI18n, platformVoiceDictationOp } from '../helpers/seed-platform-i18n.js';
import '@platform/lib/components/platform-voice-dictation.js';

async function prepare() {
    resetPlatformState();
    bootstrapTestBus({ factories: [platformVoiceDictationOp] });
    setDefaultI18nNamespace('platform');
    await seedPlatformMarkdownEditorI18n();
}

describe('platform-voice-dictation', () => {
    beforeEach(async function prepareHook() {
        this.timeout(20_000);
        await prepare();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('registers custom element and renders idle mic button', async () => {
        expect(customElements.get('platform-voice-dictation')).to.exist;
        const el = await fixture(html`<platform-voice-dictation></platform-voice-dictation>`);
        await elementUpdated(el);
        const btn = el.shadowRoot.querySelector('button');
        expect(btn).to.exist;
        expect(btn.disabled).to.equal(false);
        expect(btn.classList.contains('recording')).to.equal(false);
        expect(btn.classList.contains('processing')).to.equal(false);
    });

    it('disabled reflects to button', async () => {
        const el = await fixture(html`<platform-voice-dictation .disabled=${true}></platform-voice-dictation>`);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('button').disabled).to.equal(true);
    });

    it('emits transcribed on op succeeded', async () => {
        const el = await fixture(html`<platform-voice-dictation></platform-voice-dictation>`);
        await elementUpdated(el);
        const transcribedPromise = oneEvent(el, 'transcribed');
        getPlatformBus().dispatch(
            platformVoiceDictationOp.events.SUCCEEDED,
            {
                result: { text: '  hello voice  ', provider: 'mock_stt' },
                request_id: 'test-req-1',
            },
            { source: 'system' },
        );
        const event = await transcribedPromise;
        expect(event.detail).to.deep.equal({ text: 'hello voice', provider: 'mock_stt' });
        expect(el._phase).to.equal('idle');
    });

    it('does not emit transcribed on empty text', async () => {
        const el = await fixture(html`<platform-voice-dictation></platform-voice-dictation>`);
        await elementUpdated(el);
        let fired = false;
        el.addEventListener('transcribed', () => {
            fired = true;
        });
        getPlatformBus().dispatch(
            platformVoiceDictationOp.events.SUCCEEDED,
            {
                result: { text: '   ', provider: 'mock_stt' },
                request_id: 'test-req-2',
            },
            { source: 'system' },
        );
        await elementUpdated(el);
        expect(fired).to.equal(false);
        expect(el._phase).to.equal('idle');
    });

    it('resets phase on op failed', async () => {
        const el = await fixture(html`<platform-voice-dictation></platform-voice-dictation>`);
        el._phase = 'processing';
        await elementUpdated(el);
        getPlatformBus().dispatch(
            platformVoiceDictationOp.events.FAILED,
            {
                error: 'boom',
                message: 'boom',
                request_id: 'test-req-3',
            },
            { source: 'system' },
        );
        await elementUpdated(el);
        expect(el._phase).to.equal('idle');
    });
});
