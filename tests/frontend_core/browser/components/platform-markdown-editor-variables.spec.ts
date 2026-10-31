/**
 * platform-markdown-editor — enable-variables preview resolution & chips (strict).
 */

import {
    fixture,
    fixtureCleanup,
    html,
    expect,
    elementUpdated,
    waitUntil,
} from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { seedPlatformMarkdownEditorI18n, platformEn } from '../helpers/seed-platform-i18n.js';
import '@platform/lib/components/platform-markdown-editor.js';
import { qs, qsa, shadow, type TestEl } from '../helpers/dom.js';

async function prepare() {
    resetPlatformState();
    bootstrapTestBus();
    setDefaultI18nNamespace('platform');
    await seedPlatformMarkdownEditorI18n();
}

async function mountVariables({ value, variables, variableCatalog }: any) {
    const editor = await fixture<TestEl>(html`
        <platform-markdown-editor
            ?enable-variables=${true}
            .value=${value}
            .variables=${variables}
            .variableCatalog=${variableCatalog}
        ></platform-markdown-editor>
    `);
    await waitUntil(() => editor._editorView !== null, 'CodeMirror initialized', { timeout: 15_000 });
    return editor;
}

async function previewText(editor: any) {
    editor._setMode('preview');
    await elementUpdated(editor);
    const preview = qs(shadow(editor), '.preview-container');
    if (!preview) {
        throw new Error('preview-container missing');
    }
    return preview.textContent;
}

describe('platform-markdown-editor variable contract', () => {
    beforeEach(async function prepareHook() {
        this.timeout(20_000);
        await prepare();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('resolves concrete node variables and marks runtime-only catalog entries', async () => {
        const editor = await mountVariables({
            value: 'Topic: {topic}\nDate: {current_date}\nUser: {user_name}',
            variables: { topic: 'reliable UX', current_date: '2026-07-15' },
            variableCatalog: [
                { name: 'topic', source: 'input', type: 'string', hasValue: true },
                { name: 'current_date', source: 'system', type: 'string', hasValue: true },
                { name: 'user_name', source: 'system', type: 'string', hasValue: false },
            ],
        });
        const text = await previewText(editor);
        expect(text).to.contain('Topic: reliable UX');
        expect(text).to.contain('Date: 2026-07-15');
        expect(text).to.contain('user_name:');
        expect(text).to.contain(platformEn.markdown_editor.runtime_value);
        expect(text).not.to.contain('⚠️{current_date}');
    });

    it('renders available-variable chips and inserts the exact placeholder', async () => {
        const editor = await mountVariables({
            value: '',
            variables: { customer_name: 'Ada' },
            variableCatalog: [
                { name: 'customer_name', source: 'upstream', type: 'string', hasValue: true },
            ],
        });

        const chip = qs(shadow(editor), '.syntax-chip[data-source="upstream"]');
        expect(chip).to.exist;
        expect(chip.textContent.trim()).to.equal('{customer_name}');
        expect(chip.title).to.include('customer_name');
        (chip as TestEl).click();
        await waitUntil(() => editor.getValue() === '{customer_name}', 'variable inserted');

        const text = await previewText(editor);
        expect(text.trim()).to.equal('Ada');
    });

    it('keeps truly unavailable variables visibly unresolved', async () => {
        const editor = await mountVariables({
            value: 'Known {known}; unknown {typo}',
            variables: { known: 'yes' },
            variableCatalog: [{ name: 'known', source: 'flow', type: 'string', hasValue: true }],
        });
        const text = await previewText(editor);
        expect(text).to.contain('Known yes');
        expect(text).to.contain('⚠️{typo}');
    });

    it('resolves optional, default, @var: and leaves @state: marked', async () => {
        const editor = await mountVariables({
            value: [
                'opt:{?missing}',
                'opt2:{?present}',
                'def:{gone|fallback}',
                'var:@var:topic',
                'state:@state:path.to',
            ].join('\n'),
            variables: { present: 'here', topic: 'T' },
            variableCatalog: [
                { name: 'present', source: 'local', type: 'string', hasValue: true },
                { name: 'topic', source: 'input', type: 'string', hasValue: true },
            ],
        });
        const text = await previewText(editor);
        expect(text).to.contain('opt:');
        expect(text).not.to.contain('{?missing}');
        expect(text).to.contain('opt2:here');
        expect(text).to.contain('def:fallback');
        expect(text).to.contain('var:T');
        expect(text).to.contain('📍@state:path.to');
    });

    it('resolves {for} loops over arrays and fails closed on non-array', async () => {
        const editor = await mountVariables({
            value: [
                '{for item in items}[{item}]{endfor}',
                '{for row in rows}{row.name};{endfor}',
                '{for x in notlist}x{endfor}',
            ].join('\n'),
            variables: {
                items: ['a', 'b'],
                rows: [{ name: 'n1' }, { name: 'n2' }],
                notlist: 'string',
            },
            variableCatalog: [
                { name: 'items', source: 'flow', type: 'array', hasValue: true },
                { name: 'rows', source: 'flow', type: 'array', hasValue: true },
                { name: 'notlist', source: 'flow', type: 'string', hasValue: true },
            ],
        });
        const text = await previewText(editor);
        expect(text).to.contain('[a][b]');
        expect(text).to.contain('n1;n2;');
        expect(text).to.contain('notlist is not an array');
    });

    it('unwraps VariableMap { value } wrappers and stringifies objects', async () => {
        const editor = await mountVariables({
            value: 'v={wrapped} obj={payload}',
            variables: {
                wrapped: { value: 'inner' },
                payload: { a: 1 },
            },
            variableCatalog: [
                { name: 'wrapped', source: 'local', type: 'string', hasValue: true },
                { name: 'payload', source: 'local', type: 'object', hasValue: true },
            ],
        });
        const text = await previewText(editor);
        expect(text).to.contain('v=inner');
        expect(text).to.contain('obj={"a":1}');
    });

    it('shows no_available_variables when catalog empty', async () => {
        const editor = await mountVariables({
            value: '',
            variables: {},
            variableCatalog: [],
        });
        const status = qs(shadow(editor), '.syntax-list .editor-status');
        expect(status.textContent).to.equal(platformEn.markdown_editor.no_available_variables);
    });

    it('toolbar variable insert buttons inject placeholders', async () => {
        const editor = await mountVariables({
            value: '',
            variables: {},
            variableCatalog: [],
        });
        const monoButtons = [...qsa(shadow(editor), '.tool-btn.mono')];
        expect(monoButtons.length).to.be.at.least(3);
        monoButtons[0]!.click();
        await waitUntil(() => editor.getValue().includes('{variable}'), 'placeholder inserted');
    });
});
