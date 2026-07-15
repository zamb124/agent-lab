import { fixture, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/prompt-editor.js';

describe('prompt-editor variable contract', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('resolves concrete node variables and system datetime in Preview', async () => {
        const editor = await fixture(html`
            <prompt-editor
                .value=${'Topic: {topic}\nDate: {current_date}\nUser: {user_name}'}
                .variables=${{ topic: 'reliable UX', current_date: '2026-07-15' }}
                .variableCatalog=${[
                    { name: 'topic', source: 'input', type: 'string', hasValue: true },
                    { name: 'current_date', source: 'system', type: 'string', hasValue: true },
                    { name: 'user_name', source: 'system', type: 'string', hasValue: false },
                ]}
            ></prompt-editor>
        `);

        editor._setMode('preview');
        await elementUpdated(editor);
        const preview = editor.shadowRoot.querySelector('.preview-container');
        expect(preview.textContent).to.contain('Topic: reliable UX');
        expect(preview.textContent).to.contain('Date: 2026-07-15');
        expect(preview.textContent).to.contain('user_name:');
        expect(preview.textContent).not.to.contain('⚠️{current_date}');
    });

    it('renders real available-variable chips and inserts the exact placeholder', async () => {
        const editor = await fixture(html`
            <prompt-editor
                .value=${''}
                .variables=${{ customer_name: 'Ada' }}
                .variableCatalog=${[
                    { name: 'customer_name', source: 'upstream', type: 'string', hasValue: true },
                ]}
            ></prompt-editor>
        `);
        await waitUntil(() => editor._editorView !== null, 'CodeMirror initialized');

        const chip = editor.shadowRoot.querySelector('.syntax-chip[data-source="upstream"]');
        expect(chip).to.exist;
        expect(chip.textContent.trim()).to.equal('{customer_name}');
        chip.click();
        await waitUntil(() => editor.getValue() === '{customer_name}', 'variable inserted');

        editor._setMode('preview');
        await elementUpdated(editor);
        expect(editor.shadowRoot.querySelector('.preview-container').textContent.trim()).to.equal('Ada');
    });

    it('keeps truly unavailable variables visibly unresolved', async () => {
        const editor = await fixture(html`
            <prompt-editor
                .value=${'Known {known}; unknown {typo}'}
                .variables=${{ known: 'yes' }}
                .variableCatalog=${[{ name: 'known', source: 'flow', type: 'string', hasValue: true }]}
            ></prompt-editor>
        `);
        editor._setMode('preview');
        await elementUpdated(editor);
        const text = editor.shadowRoot.querySelector('.preview-container').textContent;
        expect(text).to.contain('Known yes');
        expect(text).to.contain('⚠️{typo}');
    });
});

