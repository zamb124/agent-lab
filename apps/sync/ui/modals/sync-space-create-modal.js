/**
 * sync-space-create-modal — создание Sync-пространства, привязанного к
 * платформенному namespace (1:1).
 *
 * Поток:
 *   1. Пользователь выбирает namespace из списка платформенных
 *      (`sync/platform_namespaces`) — те же, что в CRM-sidebar; либо
 *      создаёт новый, указав slug.
 *   2. По умолчанию выбран глобально активный namespace (если ещё нет
 *      sync-space для него) или первый namespace без sync-space.
 *   3. После create — переключаем глобальный селект на namespace
 *      созданного space (`setPlatformNamespaceSelection`).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import {
    setPlatformNamespaceSelection,
    getPlatformNamespaceSidebarSelection,
} from '@platform/lib/utils/platform-namespace.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

const NAMESPACE_SLUG_RE = /^[a-z][a-z0-9_-]{0,99}$/;
const NEW_NAMESPACE_SENTINEL = '__new__';

function _slugify(value) {
    if (typeof value !== 'string') return '';
    let s = value.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/-+/g, '-').replace(/^-+|-+$/g, '');
    if (s.length === 0) return '';
    if (!/^[a-z]/.test(s)) s = 's-' + s;
    return s.slice(0, 100);
}

export class SyncSpaceCreateModal extends PlatformFormModal {
    static modalKind = 'sync.space_create';
    static i18nNamespace = 'sync';

    static properties = {
        ...PlatformFormModal.properties,
        _name: { state: true },
        _namespaceMode: { state: true },     // existing namespace name or NEW_NAMESPACE_SENTINEL
        _newNamespace: { state: true },
        _namespaceTouched: { state: true },
        _transcribe: { state: true },
        _speechToChat: { state: true },
        _initialized: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .form-input.invalid { border-color: var(--error, #f43f5e); }
            .ns-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
            .ns-hint.error { color: var(--error, #f43f5e); }
        `,
    ];

    constructor() {
        super();
        this._name = '';
        this._namespaceMode = '';
        this._newNamespace = '';
        this._namespaceTouched = false;
        this._transcribe = false;
        this._speechToChat = false;
        this._initialized = false;
        this._spaces = this.useResource('sync/spaces');
        this._namespaces = this.useResource('sync/platform_namespaces', { autoload: true });
        this._authSel = this.select((s) => s.auth && s.auth.user ? s.auth.user : null);
    }

    _availableNamespaces() {
        // Платформенные namespace, для которых ещё НЕТ привязанного sync-space.
        const used = new Set();
        for (const sp of this._spaces.items) {
            if (sp && typeof sp.namespace === 'string') used.add(sp.namespace);
        }
        return this._namespaces.items.filter((ns) => ns && typeof ns.name === 'string' && !used.has(ns.name));
    }

    updated(changed) {
        super.updated?.(changed);
        if (this._initialized) return;
        if (this._namespaces.loading || this._spaces.loading) return;
        const available = this._availableNamespaces();
        if (available.length === 0 && this._namespaces.items.length === 0) return;
        const user = this._authSel.value;
        let preferred = '';
        if (user && typeof user.company_id === 'string' && user.company_id !== '') {
            const active = getPlatformNamespaceSidebarSelection(user.company_id);
            if (active !== 'all' && available.some((ns) => ns.name === active)) {
                preferred = active;
            }
        }
        if (preferred === '' && available.length > 0) {
            preferred = available[0].name;
        }
        this._namespaceMode = preferred === '' ? NEW_NAMESPACE_SENTINEL : preferred;
        this._initialized = true;
    }

    _onNameInput(e) {
        this._name = e.target.value;
        if (this._namespaceMode === NEW_NAMESPACE_SENTINEL && !this._namespaceTouched) {
            this._newNamespace = _slugify(this._name);
        }
        this.isDirty = true;
    }

    _onNamespaceModeChange(e) {
        this._namespaceMode = e.target.value;
        this._namespaceTouched = false;
        if (this._namespaceMode === NEW_NAMESPACE_SENTINEL) {
            this._newNamespace = _slugify(this._name);
        }
        this.isDirty = true;
    }

    _onNewNamespaceInput(e) {
        this._newNamespace = e.target.value;
        this._namespaceTouched = true;
        this.isDirty = true;
    }

    _resolvedNamespace() {
        if (this._namespaceMode === NEW_NAMESPACE_SENTINEL) return this._newNamespace;
        return this._namespaceMode;
    }

    _isNamespaceValid() {
        const ns = this._resolvedNamespace();
        return NAMESPACE_SLUG_RE.test(ns);
    }

    _isSubmittable() {
        return this._name.trim().length > 0 && this._isNamespaceValid();
    }

    renderHeader() {
        return html`<h3>${this.t('space_modal.title_create')}</h3>`;
    }

    renderBody() {
        const available = this._availableNamespaces();
        const isNewMode = this._namespaceMode === NEW_NAMESPACE_SENTINEL;
        const nsValid = this._isNamespaceValid();
        return html`
            <div class="form-group">
                <label class="form-label">${this.t('space_modal.field_name')}</label>
                <input
                    class="form-input"
                    type="text"
                    .value=${this._name}
                    placeholder=${this.t('space_modal.field_name')}
                    @input=${this._onNameInput}
                />
            </div>
            <div class="form-group">
                <label class="form-label">${this.t('space_modal.field_namespace')}</label>
                <select
                    class="form-select"
                    .value=${this._namespaceMode}
                    @change=${this._onNamespaceModeChange}
                >
                    ${available.map((ns) => html`
                        <option value=${ns.name} ?selected=${ns.name === this._namespaceMode}>
                            ${typeof ns.description === 'string' && ns.description !== '' ? ns.description : ns.name}
                            ${ns.is_default ? html` (default)` : ''}
                        </option>
                    `)}
                    <option
                        value=${NEW_NAMESPACE_SENTINEL}
                        ?selected=${isNewMode}
                    >${this.t('space_modal.namespace_new_option')}</option>
                </select>
                ${isNewMode ? html`
                    <input
                        class=${nsValid || this._newNamespace === '' ? 'form-input' : 'form-input invalid'}
                        type="text"
                        .value=${this._newNamespace}
                        placeholder="my-team"
                        style="margin-top: var(--space-2);"
                        @input=${this._onNewNamespaceInput}
                    />
                    ${this._newNamespace !== '' && !nsValid
                        ? html`<div class="ns-hint error">${this.t('space_modal.namespace_invalid')}</div>`
                        : html`<div class="ns-hint">${this.t('space_modal.namespace_help')}</div>`}
                ` : ''}
            </div>
            <div
                class=${this._transcribe ? 'form-item selected' : 'form-item'}
                @click=${() => { this._transcribe = !this._transcribe; this.isDirty = true; }}
            >
                <div class="form-checkbox">
                    ${this._transcribe ? html`<platform-icon name="check" size="12"></platform-icon>` : ''}
                </div>
                <div class="form-item-content">
                    <div class="form-item-title">${this.t('space_modal.field_transcribe')}</div>
                </div>
            </div>
            <div
                class=${this._speechToChat ? 'form-item selected' : 'form-item'}
                @click=${() => { this._speechToChat = !this._speechToChat; this.isDirty = true; }}
            >
                <div class="form-checkbox">
                    ${this._speechToChat ? html`<platform-icon name="check" size="12"></platform-icon>` : ''}
                </div>
                <div class="form-item-content">
                    <div class="form-item-title">${this.t('space_modal.field_speech_to_chat')}</div>
                </div>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>${this.t('space_modal.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit} ?disabled=${!this._isSubmittable()}>
                    ${this.t('space_modal.action_create')}
                </platform-button>
            </div>
        `;
    }

    _onSubmit() {
        if (!this._isSubmittable()) return;
        const namespace = this._resolvedNamespace();
        this._spaces.create({
            name: this._name.trim(),
            namespace,
            transcribe_voice_messages: this._transcribe,
            speech_to_chat_enabled: this._speechToChat,
        });
        const user = this._authSel.value;
        if (user && typeof user.company_id === 'string' && user.company_id !== '') {
            setPlatformNamespaceSelection(user.company_id, namespace);
        }
        this.closeAfterSave();
    }
}

customElements.define('sync-space-create-modal', SyncSpaceCreateModal);
registerModalKind(SyncSpaceCreateModal.modalKind, 'sync-space-create-modal');
