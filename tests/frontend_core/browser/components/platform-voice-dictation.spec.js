/**
 * platform-voice-dictation — mic UI + VoiceMediaSession STT-only (VAD final → transcribed).
 */
import {
    fixture,
    fixtureCleanup,
    html,
    expect,
    oneEvent,
    elementUpdated,
} from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { seedPlatformMarkdownEditorI18n } from '../helpers/seed-platform-i18n.js';
import '@platform/lib/components/platform-voice-dictation.js';

beforeEach(async () => {
    resetPlatformState();
    bootstrapTestBus();
    await seedPlatformMarkdownEditorI18n();
});

afterEach(() => {
    fixtureCleanup();
});

describe('platform-voice-dictation', () => {
    it('registers custom element and starts idle', async () => {
        expect(customElements.get('platform-voice-dictation')).to.exist;
        const el = await fixture(html`<platform-voice-dictation></platform-voice-dictation>`);
        expect(el._phase).to.equal('idle');
        const btn = el.shadowRoot.querySelector('button');
        expect(btn).to.exist;
        expect(btn.disabled).to.equal(false);
        expect(btn.querySelector('platform-icon').name).to.equal('mic');
    });

    it('disabled attribute disables the button', async () => {
        const el = await fixture(html`<platform-voice-dictation .disabled=${true}></platform-voice-dictation>`);
        const btn = el.shadowRoot.querySelector('button');
        expect(btn.disabled).to.equal(true);
    });

    it('emits transcribed on VAD final transcript', async () => {
        const el = await fixture(html`<platform-voice-dictation></platform-voice-dictation>`);
        const transcribedP = oneEvent(el, 'transcribed');
        el._onMediaTranscript(new CustomEvent('transcript', {
            detail: { text: 'hello world', final: true },
        }));
        const event = await transcribedP;
        expect(event.detail.text).to.equal('hello world');
        expect(event.detail.provider).to.equal('voice');
        expect(el._heardFinalText).to.equal(true);
    });

    it('does not emit transcribed when STT text is empty', async () => {
        const el = await fixture(html`<platform-voice-dictation></platform-voice-dictation>`);
        let emitted = false;
        el.addEventListener('transcribed', () => {
            emitted = true;
        });
        el._onMediaTranscript(new CustomEvent('transcript', {
            detail: { text: '   ', final: true },
        }));
        await elementUpdated(el);
        expect(emitted).to.equal(false);
        expect(el._heardFinalText).to.equal(false);
    });

    it('ignores partial transcript frames', async () => {
        const el = await fixture(html`<platform-voice-dictation></platform-voice-dictation>`);
        let emitted = false;
        el.addEventListener('transcribed', () => {
            emitted = true;
        });
        el._onMediaTranscript(new CustomEvent('transcript', {
            detail: { text: 'partial', final: false },
        }));
        await elementUpdated(el);
        expect(emitted).to.equal(false);
        expect(el._heardFinalText).to.equal(false);
    });
});
