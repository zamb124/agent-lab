/**
 * CreateChannelModal — модалка создания канала
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { SyncStore } from '../store/sync.store.js';
import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';

export class CreateChannelModal extends PlatformElement {
    static properties = {
        _open: { state: true },
        _spaceId: { state: true },
        _name: { state: true },
        _creating: { state: true },
        _error: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        buttonStyles,
        css`
            .backdrop {
                position: fixed;
                inset: 0;
                z-index: 50;
                background: rgba(0, 0, 0, 0.4);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-6);
            }

            .modal {
                width: 100%;
                max-width: 480px;
                border-radius: var(--radius-2xl);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                backdrop-filter: blur(var(--glass-blur-strong));
                padding: var(--space-5);
            }

            .modal-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-4);
            }

            .space-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-3);
            }

            .field {
                margin-bottom: var(--space-3);
            }

            .label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
                display: block;
            }

            .input {
                width: 100%;
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
                outline: none;
                box-sizing: border-box;
                transition: border-color var(--duration-fast);
            }

            .input:focus { border-color: var(--accent); }

            .error {
                background: rgba(239, 68, 68, 0.1);
                border: 1px solid rgba(239, 68, 68, 0.2);
                border-radius: var(--radius-lg);
                padding: var(--space-2) var(--space-3);
                color: rgb(239, 68, 68);
                font-size: var(--text-sm);
                margin-top: var(--space-2);
            }

            .actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
                margin-top: var(--space-5);
            }

            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .btn:hover { background: var(--glass-solid-medium); color: var(--text-primary); }

            .btn-primary {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-medium);
            }

            .btn-primary:hover:not(:disabled) { background: var(--accent); color: white; }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        `
    ];

    constructor() {
        super();
        const s = SyncStore.state;
        this._open = s.ui.showCreateChannel;
        this._spaceId = s.chat.selectedSpaceId;
        this._name = '';
        this._creating = false;
        this._error = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = SyncStore.subscribe(state => {
            this._open = state.ui.showCreateChannel;
            this._spaceId = state.chat.selectedSpaceId;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback?.();
        this._unsubscribe?.();
    }

    _close() {
        SyncStore.setShowCreateChannel(false);
        this._name = '';
        this._error = null;
    }

    async _create() {
        this._error = null;
        const spaceId = this._spaceId;
        if (!spaceId) {
            this._error = 'Сначала выбери пространство.';
            return;
        }
        const name = this._name.trim();
        if (!name) {
            this._error = 'Название канала обязательно.';
            return;
        }

        this._creating = true;
        try {
            const syncApi = ServiceRegistry.get('syncApi');
            const created = await syncApi.createChannel(spaceId, name);
            await SyncStore.loadChannels(syncApi);
            SyncStore.sanitizeChatSelectionAfterLoad();
            SyncStore.selectChannel(spaceId, created.id);
            this._close();
        } catch (e) {
            this._error = e.message ?? 'Ошибка создания канала.';
        } finally {
            this._creating = false;
        }
    }

    render() {
        if (!this._open) return html``;

        return html`
            <div class="backdrop" @click=${this._close}>
                <div class="modal" @click=${(e) => e.stopPropagation()}>
                    <div class="modal-title">Создать канал</div>
                    <div class="space-hint">Пространство: ${this._spaceId ?? '— (выбери пространство слева)'}</div>

                    <div class="field">
                        <label class="label">Название</label>
                        <input
                            class="input"
                            .value=${this._name}
                            @input=${(e) => { this._name = e.target.value; }}
                        >
                    </div>

                    ${this._error ? html`<div class="error">${this._error}</div>` : ''}

                    <div class="actions">
                        <button class="btn" @click=${this._close}>Отмена</button>
                        <button
                            class="btn btn-primary"
                            ?disabled=${this._creating}
                            @click=${this._create}
                        >
                            ${this._creating ? 'Создаём...' : 'Создать'}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('create-channel-modal', CreateChannelModal);
