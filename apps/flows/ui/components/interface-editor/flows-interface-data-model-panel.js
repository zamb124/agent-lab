/**
 * Surface data model (content + values + system) as validated JSON draft.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';

export class FlowsInterfaceDataModelPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        surface: { attribute: false },
        draft: { state: true },
        error: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: grid; gap: 8px; padding: 10px; }
        .title {
            font-size: 11px; font-weight: 700; text-transform: uppercase;
            letter-spacing: .06em; color: var(--text-tertiary);
        }
        textarea {
            width: 100%; min-height: 220px; box-sizing: border-box;
            font: 11px/1.5 ui-monospace, monospace; white-space: pre;
            background: var(--bg-elevated); border: 1px solid var(--border-subtle);
            padding: 10px; border-radius: var(--radius-md); color: inherit; resize: vertical;
        }
        .error { color: var(--error); font-size: 11px; }
    `];

    constructor() {
        super();
        this.surface = null;
        this.draft = '';
        this.error = '';
    }

    willUpdate(changed) {
        if (changed.has('surface')) {
            this.draft = JSON.stringify(this.surface?.data_model || {}, null, 2);
            this.error = '';
        }
    }

    _apply() {
        let parsed;
        try {
            parsed = JSON.parse(this.draft);
        } catch (error) {
            this.error = error instanceof Error ? error.message : String(error);
            return;
        }
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            this.error = this.t('interface_editor.data_model_object_required');
            return;
        }
        for (const key of ['content', 'values', 'system']) {
            if (!(key in parsed) || typeof parsed[key] !== 'object' || parsed[key] === null || Array.isArray(parsed[key])) {
                this.error = this.t('interface_editor.data_model_section_required', { section: key });
                return;
            }
        }
        this.error = '';
        this.emit('data-model-change', { dataModel: parsed });
    }

    render() {
        return html`
            <div class="title">${this.t('interface_editor.data_model_title')}</div>
            <textarea
                data-canon="inline-edit"
                spellcheck="false"
                .value=${this.draft}
                @input=${(event) => { this.draft = event.target.value; this.error = ''; }}
            ></textarea>
            ${this.error ? html`<div class="error">${this.error}</div>` : nothing}
            <platform-button density="compact" variant="secondary" @click=${() => this._apply()}>
                ${this.t('interface_editor.data_model_apply')}
            </platform-button>
        `;
    }
}

if (!customElements.get('flows-interface-data-model-panel')) {
    customElements.define('flows-interface-data-model-panel', FlowsInterfaceDataModelPanel);
}
