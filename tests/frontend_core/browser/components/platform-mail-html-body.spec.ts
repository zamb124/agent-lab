/**
 * platform-mail-html-body — iframe srcdoc, не escaped HTML source.
 */
import {
    fixture,
    fixtureCleanup,
    html,
    expect,
    elementUpdated,
} from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { sanitizeMailHtml } from '@platform/lib/utils/mail-html.js';
import mailEn from '../../../../core/i18n/translations/en/mail.json' with { type: 'json' };
import '@platform/lib/components/platform-mail-html-body.js';
import {q, qs, shadow, type TestEl} from '../helpers/dom.js';

async function seedMailI18n() {
    const bus = getPlatformBus();
    for (const locale of ['en', 'ru']) {
        const prev = bus.getState().i18n.translations[locale] || {};
        bus.dispatch(
            CoreEvents.I18N_LOCALE_LOADED,
            {
                locale,
                bundle: {
                    ...prev,
                    mail: mailEn,
                },
            },
            { source: 'system' },
        );
    }
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'mail' },
        { source: 'system' },
    );
}

describe('sanitizeMailHtml', () => {
    it('strips script, remote img until allow, cid to data, wrap has CSP', () => {
        const withCid = sanitizeMailHtml(
            '<html><body><script>alert(1)</script><p>Hi</p>'
            + '<img src="https://evil.example/pixel.gif">'
            + '<img src="cid:logo@tbank"></body></html>',
            {
                allowRemoteImages: false,
                cidMap: { 'logo@tbank': 'data:image/png;base64,aaa' },
            },
        );
        expect(withCid).to.include('Hi');
        expect(withCid).to.not.include('alert(1)');
        expect(withCid).to.not.match(/src="https:\/\/evil\.example/);
        expect(withCid).to.include('data:image/png;base64,aaa');
        expect(withCid).to.include("script-src 'none'");
        expect(withCid).to.include('Content-Security-Policy');
    });
});

describe('platform-mail-html-body', () => {
    beforeEach(async () => {
        resetPlatformState();
        bootstrapTestBus();
        setDefaultI18nNamespace('mail');
        await seedMailI18n();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('registers custom element', () => {
        expect(customElements.get('platform-mail-html-body')).to.exist;
    });

    it('iframe srcdoc contains visible text, not escaped html source', async () => {
        const el = await fixture<TestEl>(html`
            <platform-mail-html-body
                .html=${'<html><body><p>T-Bank receipt</p></body></html>'}
                .text=${''}
                .cidMap=${{}}
            ></platform-mail-html-body>
        `);
        await elementUpdated(el);
        const iframe = qs(shadow(el), 'iframe');
        expect(iframe).to.exist;
        expect(iframe.srcdoc).to.include('T-Bank receipt');
        expect(iframe.srcdoc).to.not.include('&lt;html');
        expect(iframe.srcdoc).to.include("script-src 'none'");
    });

    it('shows load-images banner for remote http images', async () => {
        const el = await fixture<TestEl>(html`
            <platform-mail-html-body
                .html=${'<img src="https://cdn.example/x.png" alt="x">'}
                .text=${''}
                .cidMap=${{}}
            ></platform-mail-html-body>
        `);
        await elementUpdated(el);
        expect(shadow(el).textContent).to.include(mailEn.images_blocked_hint);
        const button = qs(shadow(el), 'platform-button');
        expect(button).to.exist;
        expect(button.textContent.trim()).to.equal(mailEn.load_images);
    });

    it('plaintext uses pre-wrap, not iframe', async () => {
        const el = await fixture<TestEl>(html`
            <platform-mail-html-body
                .html=${''}
                .text=${'hello **not markdown** https://example.com'}
                .cidMap=${{}}
            ></platform-mail-html-body>
        `);
        await elementUpdated(el);
        expect(q(shadow(el), 'iframe')).to.equal(null);
        const plain = qs(shadow(el), '.mail-plain');
        expect(plain).to.exist;
        expect(plain.textContent).to.include('hello **not markdown**');
        expect(qs(plain!, 'a').getAttribute('href')).to.equal('https://example.com');
    });
});
