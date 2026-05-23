import { expect, fixtureCleanup } from '../helpers/render.js';
import '../../../../core/frontend/static/lib/flows-chat/flows-chat-input.js';

describe('flows-chat-input', () => {
    afterEach(() => {
        document.querySelectorAll('flows-chat-input').forEach((el) => el.remove());
        fixtureCleanup();
    });

    it('emits one canonical send event with text and files', async () => {
        const el = document.createElement('flows-chat-input');
        document.body.appendChild(el);
        await el.updateComplete;

        const file = new File(['x'], 'note.txt', { type: 'text/plain' });
        const dt = new DataTransfer();
        dt.items.add(file);
        const fileInput = el.shadowRoot.querySelector('input[type=file]');
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
        el.setDraft(' hello ');
        await el.updateComplete;

        let detail = null;
        el.addEventListener('send', (event) => {
            detail = event.detail;
        });
        el.shadowRoot.querySelector('.send-btn').click();
        await el.updateComplete;
        expect(detail).to.deep.equal({ message: 'hello', files: [file] });
        expect(el.shadowRoot.querySelector('textarea').value).to.equal('');
    });

    it('delegates TTS toggle and stop as events without transport logic', async () => {
        const el = document.createElement('flows-chat-input');
        el.loading = true;
        document.body.appendChild(el);
        await el.updateComplete;

        let stopped = false;
        let ttsDetail = null;
        el.addEventListener('stop', () => { stopped = true; });
        el.addEventListener('tts-output-toggle', (event) => { ttsDetail = event.detail; });

        el.shadowRoot.querySelector('.stop-btn').click();
        expect(stopped).to.equal(true);

        el.loading = false;
        el.showVoice = true;
        await el.updateComplete;
        el.shadowRoot.querySelector('.circle-btn.active, .circle-btn:not(.attach-btn)').click();
        expect(ttsDetail).to.deep.equal({ enabled: !el.ttsOutputEnabled });
    });
});
