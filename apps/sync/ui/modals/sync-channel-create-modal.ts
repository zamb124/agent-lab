/**
 * sync-channel-create-modal — создание группового канала Sync.
 *
 * Канал всегда создаётся типа `group`. `namespace` приходит prop'ом из
 * активного пространства sidebar/picker (если опущен — backend подставит
 * 'default'); это нужно, чтобы канал сразу появился в текущей вкладке
 * пространства. Имя обязательно. Опциональный набор участников
 * выбирается чек-боксами из `state.team.members` (всех пользователей
 * активной компании, кроме самого создателя; владелец всегда
 * добавляется автоматически в `_create_channel`). Включается приватность
 * канала, авто-транскрипция голосовых и речь звонка в ленту.
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { AuthUser } from '@platform/lib/events/reducers/auth.js';
import type { TeamMemberRecord } from '@platform/lib/events/reducers/team.js';
import type { ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations} from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { TEAM_EVENTS } from '@platform/lib/events/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-empty-state.js';

export class SyncChannelCreateModal extends PlatformFormModal {
    static modalKind = 'sync.channel_create';
    static i18nNamespace = 'sync';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        namespace: { type: String },
        _name: { state: true },
        _isPrivate: { state: true },
        _selectedUserIds: { state: true },
        _transcribe: { state: true },
        _speechToChat: { state: true },
        _membersFilter: { state: true },
    };
    declare namespace: string;
    declare _name: string;
    declare _isPrivate: boolean;
    declare _selectedUserIds: string[];
    declare _transcribe: boolean;
    declare _speechToChat: boolean;
    declare _membersFilter: string;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .channel-create-block {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-bottom: var(--space-6);
            }
            .members-list {
                max-height: 240px;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            .member-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-1) var(--space-2);
                cursor: pointer;
                border-radius: var(--radius-sm);
            }
            .member-row:hover {
                background: var(--glass-solid-medium);
            }
            .member-row input[type='checkbox'] {
                margin: 0;
            }
            .member-row platform-user-chip {
                pointer-events: none;
            }
            .members-empty {
                padding: var(--space-2);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                text-align: center;
            }
            .toggle-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) 0;
            }
            .toggle-row .toggle-label {
                display: flex;
                flex-direction: column;
                gap: var(--space-0_5);
            }
            .toggle-row .toggle-title {
                font-weight: 500;
            }
            .toggle-row .toggle-hint {
                color: var(--text-secondary);
                font-size: var(--text-xs);
            }
        `,
    ];
    private _channels: ControllerFor<'sync/channels'>;
    private _teamMembersSel: SelectController<TeamMemberRecord[]>;
    private _teamLoadingSel: SelectController<boolean>;
    private _authSel: SelectController<AuthUser | null>;

    constructor() {
        super();
        this.namespace = '';
        this._name = '';
        this._isPrivate = false;
        this._selectedUserIds = [];
        this._transcribe = false;
        this._speechToChat = false;
        this._membersFilter = '';
        this._channels = this.useResource('sync/channels');
        this._teamMembersSel = this.select((s) => s.team.members);
        this._teamLoadingSel = this.select((s) => s.team.loading);
        this._authSel = this.select((s) => s.auth.user);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        const members = this._teamMembersSel.value;
        const loading = this._teamLoadingSel.value;
        if (members.length === 0 && loading === false) {
            this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        }
    }

    _selectableMembers() {
        const me = this._authSel.value;
        const myId = me === null ? null : me.user_id;
        const members = this._teamMembersSel.value;
        const q = this._membersFilter.trim().toLowerCase();
        return members
            .filter((m: Record<string, unknown>) => m && m.user_id !== myId)
            .filter((m: Record<string, unknown>) => {
                if (q.length === 0) return true;
                const rawName = m.name as string | undefined;
                const rawEmail = m.email as string | undefined;
                const name = (rawName === undefined ? '' : rawName).toLowerCase();
                const email = (rawEmail === undefined ? '' : rawEmail).toLowerCase();
                return name.includes(q) || email.includes(q);
            });
    }

    _isSelected(userId: string) {
        return this._selectedUserIds.indexOf(userId) !== -1;
    }

    _toggleMember(userId: string) {
        const idx = this._selectedUserIds.indexOf(userId);
        const next = this._selectedUserIds.slice();
        if (idx === -1) next.push(userId);
        else next.splice(idx, 1);
        this._selectedUserIds = next;
        this.isDirty = true;
    }

    _isSubmittable() {
        return this._name.trim().length > 0;
    }

    override renderHeader() {
        return html`<h3>${this.t('channel_modal.title_create')}</h3>`;
    }

    override renderBody() {
        const candidates = this._selectableMembers();
        const teamLoading = this._teamLoadingSel.value;
        return html`
            <div class="channel-create-block">
                <platform-field
                    type="string"
                    mode="edit"
                    label=${this.t('channel_modal.field_name')}
                    placeholder=${this.t('channel_settings.placeholder_name')}
                    .value=${this._name}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('sync channel create: name expects detail.value string');
                        }
                        this._name = e.detail.value;
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>

            <div class="channel-create-block">
                <platform-field
                    type="string"
                    mode="edit"
                    label=${this.t('channel_modal.field_members')}
                    placeholder=${this.t('channel_modal.members_filter_placeholder')}
                    .value=${this._membersFilter}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => {
                        if (!e.detail || typeof e.detail.value !== 'string') {
                            throw new Error('sync channel create: members filter expects detail.value string');
                        }
                        this._membersFilter = e.detail.value;
                    }}
                ></platform-field>
                <div class="members-list">
                    ${teamLoading && candidates.length === 0 ? html`
                        <platform-empty-state loading></platform-empty-state>
                    ` : ''}
                    ${!teamLoading && candidates.length === 0 ? html`
                        <platform-empty-state icon="users" title=${this.t('channel_modal.members_empty')}></platform-empty-state>
                    ` : ''}
                    ${candidates.map((m: Record<string, unknown>) => html`
                        <label class="member-row" @click=${(e: Event) => {
                            const target = e.target;
                            if (target instanceof HTMLInputElement) return;
                            this._toggleMember(m.user_id);
                        }}>
                            <input
                                type="checkbox"
                                .checked=${this._isSelected(m.user_id)}
                                @change=${() => this._toggleMember(m.user_id)}
                            />
                            <platform-user-chip
                                user-id=${m.user_id}
                                size="md"
                                ?interactive=${false}
                            ></platform-user-chip>
                        </label>
                    `)}
                </div>
            </div>

            <div class="toggle-row">
                <div class="toggle-label">
                    <span class="toggle-title">${this.t('channel_modal.field_is_private')}</span>
                    <span class="toggle-hint">${this.t('channel_modal.field_is_private_hint')}</span>
                </div>
                <platform-switch
                    .checked=${this._isPrivate}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._isPrivate = !!e.detail.value; this.isDirty = true; }}
                ></platform-switch>
            </div>

            <div class="toggle-row">
                <div class="toggle-label">
                    <span class="toggle-title">${this.t('channel_modal.field_transcribe')}</span>
                    <span class="toggle-hint">${this.t('channel_modal.field_transcribe_hint')}</span>
                </div>
                <platform-switch
                    .checked=${this._transcribe}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._transcribe = !!e.detail.value; this.isDirty = true; }}
                ></platform-switch>
            </div>

            <div class="toggle-row">
                <div class="toggle-label">
                    <span class="toggle-title">${this.t('channel_modal.field_speech_to_chat')}</span>
                    <span class="toggle-hint">${this.t('channel_modal.field_speech_to_chat_hint')}</span>
                </div>
                <platform-switch
                    .checked=${this._speechToChat}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._speechToChat = !!e.detail.value; this.isDirty = true; }}
                ></platform-switch>
            </div>
        `;
    }

    override renderFooter() {
        return html`
            <div class="form-actions">
                <platform-button variant="secondary" @click=${() => this.close()}>${this.t('channel_modal.action_cancel')}</platform-button>
                <platform-button variant="primary" @click=${this._onSubmit} ?disabled=${!this._isSubmittable()}>
                    ${this.t('channel_modal.action_create')}
                </platform-button>
            </div>
        `;
    }

    override async _onSubmit(): Promise<void> {
        if (!this._isSubmittable()) return;
        const body: Record<string, unknown> = {
            type: 'group',
            name: this._name.trim(),
            is_private: this._isPrivate,
            transcribe_voice_messages: this._transcribe,
            speech_to_chat_enabled: this._speechToChat,
        };
        if (typeof this.namespace === 'string' && this.namespace !== '') {
            body.namespace = this.namespace;
        }
        if (this._selectedUserIds.length > 0) {
            body.member_ids = this._selectedUserIds.slice();
        }
        this._channels.create(body);
        this.closeAfterSave();
    }
}

customElements.define('sync-channel-create-modal', SyncChannelCreateModal);
registerModalKind(SyncChannelCreateModal.modalKind, 'sync-channel-create-modal');
