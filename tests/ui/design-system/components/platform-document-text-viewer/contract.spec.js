/**
 * platform-document-text-viewer — L1 contract: registration + presentation modes.
 */
import {
    expect,
    fixture,
    html,
    elementUpdated,
    waitUntil,
    fixtureCleanup,
} from '../../../../frontend_core/browser/helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../../../../frontend_core/browser/helpers/reset.js';
import '@platform/lib/components/platform-document-text-viewer.js';

const SAMPLE_HTML = '<!DOCTYPE html><html><body><p>Hello</p></body></html>';
const SAMPLE_MD = '# Title\n\nHello **world**.';

function installStreamFetchMock(body, contentType) {
    const previousFetch = window.fetch;
    window.fetch = async (rawUrl) => {
        const url = String(rawUrl);
        if (url.includes('viewer-stream')) {
            return new Response(body, {
                status: 200,
                headers: { 'content-type': contentType },
            });
        }
        return previousFetch(rawUrl);
    };
    return () => {
        window.fetch = previousFetch;
    };
}

describe('platform-document-text-viewer', () => {
    let uninstallFetch;

    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ slices: {}, effects: [] });
    });

    afterEach(() => {
        if (uninstallFetch) {
            uninstallFetch();
            uninstallFetch = undefined;
        }
        fixtureCleanup();
    });

    it('registers custom element', async () => {
        expect(customElements.get('platform-document-text-viewer')).to.exist;
    });

    it('renders sandboxed html preview when presentation=html and viewMode=preview', async () => {
        uninstallFetch = installStreamFetchMock(SAMPLE_HTML, 'text/html');
        const el = await fixture(html`
            <platform-document-text-viewer
                stream-url="/documents/api/v1/viewer-stream?file_id=html1"
                original-name="deck.html"
                content-type="text/html"
                presentation="html"
                view-mode="preview"
            ></platform-document-text-viewer>
        `);
        await waitUntil(
            () => Boolean(el.shadowRoot?.querySelector('iframe.html-preview-frame')),
            'html preview iframe',
        );
        const frame = el.shadowRoot.querySelector('iframe.html-preview-frame');
        expect(frame.getAttribute('sandbox')).to.equal('');
        expect(frame.getAttribute('srcdoc')).to.include('Hello');
    });

    it('renders markdown preview editor when presentation=markdown and viewMode=preview', async () => {
        uninstallFetch = installStreamFetchMock(SAMPLE_MD, 'text/markdown');
        const el = await fixture(html`
            <platform-document-text-viewer
                stream-url="/documents/api/v1/viewer-stream?file_id=md1"
                original-name="notes.md"
                content-type="text/markdown"
                presentation="markdown"
                view-mode="preview"
            ></platform-document-text-viewer>
        `);
        await waitUntil(
            () => Boolean(el.shadowRoot?.querySelector('platform-markdown-editor')),
            'markdown preview editor',
        );
        const md = el.shadowRoot.querySelector('platform-markdown-editor');
        expect(md.readonly).to.equal(true);
    });

    it('renders code editor for source mode even when presentation=html', async () => {
        uninstallFetch = installStreamFetchMock(SAMPLE_HTML, 'text/html');
        const el = await fixture(html`
            <platform-document-text-viewer
                stream-url="/documents/api/v1/viewer-stream?file_id=html2"
                original-name="deck.html"
                content-type="text/html"
                presentation="html"
                view-mode="source"
            ></platform-document-text-viewer>
        `);
        await waitUntil(
            () => Boolean(el.shadowRoot?.querySelector('platform-code-editor')),
            'source code editor',
        );
        expect(el.shadowRoot.querySelector('iframe.html-preview-frame')).to.equal(null);
        await elementUpdated(el);
    });
});
