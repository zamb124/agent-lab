/**
 * platform-variable-input — single-line CM at-ref highlight + change contract.
 */
import {
    fixture,
    fixtureCleanup,
    html,
    expect,
    waitUntil,
} from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { installFetchMock } from '../helpers/fake-fetch.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import platformEn from '../../../../core/i18n/translations/en/platform.json' with { type: 'json' };
import { secretsVariablesResource } from '@platform/lib/events/resources/secrets-variables.resource.js';
import '@platform/lib/components/platform-variable-input.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

function seedI18n() {
    const bus = getPlatformBus();
    for (const locale of ['en', 'ru']) {
        const prev = bus.getState().i18n.translations[locale] || {};
        bus.dispatch(
            CoreEvents.I18N_LOCALE_LOADED,
            {
                locale,
                bundle: {
                    ...prev,
                    ...platformEn,
                    platform: platformEn,
                },
            },
            { source: 'system' },
        );
    }
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'platform' },
        { source: 'system' },
    );
}

async function prepare() {
    resetPlatformState();
    const fetchMock = installFetchMock();
    fetchMock.respondJson(
        'GET',
        (url: string) => String(url).includes('/secrets/api/v1/variables'),
        { items: [], next_cursor: null, has_more: false },
    );
    bootstrapTestBus({ factories: [secretsVariablesResource] });
    setDefaultI18nNamespace('platform');
    seedI18n();
    return fetchMock;
}

describe('platform-variable-input at-ref', function () {
    this.timeout(20_000);

    let fetchMock: { uninstall(): void } | null = null;

    afterEach(() => {
        fixtureCleanup();
        if (fetchMock) {
            fetchMock.uninstall();
            fetchMock = null;
        }
    });

    it('mounts CodeMirror and highlights @state:content', async () => {
        fetchMock = await prepare();
        const el = await fixture<TestEl>(html`
            <platform-variable-input
                .value=${'Оператор: @state:content'}
                .statePreview=${{ content: 'hello' }}
                .statePaths=${['content']}
                .previewValues=${{ topic: 'AI' }}
                .variableCatalog=${[{ name: 'topic', source: 'flow', type: 'string', hasValue: true }]}
            ></platform-variable-input>
        `);
        await waitUntil(
            () => el._editorView !== null && Boolean(q(shadow(el), '#cm-host .cm-editor')),
            'CodeMirror editor mounted',
            { timeout: 15_000 },
        );
        expect(customElements.get('platform-variable-input')).to.exist;
        const marked = qsa(shadow(el), '.cm-ref-state');
        expect(marked.length, '@state:content should be highlighted').to.be.greaterThan(0);
        expect((el as TestEl).value).to.equal('Оператор: @state:content');
    });

    it('emits change when document edits', async () => {
        fetchMock = await prepare();
        const el = await fixture<TestEl>(html`
            <platform-variable-input .value=${'@var:topic'}></platform-variable-input>
        `);
        await waitUntil(() => el._editorView !== null, 'editor view ready', { timeout: 15_000 });
        let last = null;
        el.addEventListener('change', (e) => {
            last = (e as CustomEvent).detail;
        });
        const doc = el._editorView.state.doc;
        el._editorView.dispatch({
            changes: { from: 0, to: doc.length, insert: '@var:topic @state:content' },
        });
        expect(last).to.deep.equal({ value: '@var:topic @state:content' });
        expect((el as TestEl).value).to.equal('@var:topic @state:content');
    });
});
