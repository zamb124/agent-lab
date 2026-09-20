/**
 * flows-employee-settings-modal — настройки flow как AI-сотрудника компании.
 *
 * Включение пишет `FlowConfig.employee` через `PUT /flows/api/v1/flows/{flow_id}`
 * и провижнит `User` flow_employee_{flow_id} на бэкенде.
 */

import { html, css, nothing } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { TEAM_EVENTS } from '@platform/lib/events/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-spinner.js';
import { asArray, isPlainObject } from '../_helpers/flows-resolvers.js';

const DEFAULT_EMPLOYEE_ROLES = ['member'];

function emptyEmployee() {
    return {
        enabled: false,
        roles: [],
        curator_user_ids: [],
        display_name: null,
        avatar_url: null,
    };
}

export class FlowsEmployeeSettingsModal extends PlatformFormModal {
    static modalKind = 'flows.employee_settings';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        flowId: { type: String },
        _enabled: { state: true },
        _displayName: { state: true },
        _avatarUrl: { state: true },
        _curatorUserIds: { state: true },
        _membersFilter: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .hero {
                display: flex;
                align-items: flex-start;
                gap: var(--space-4);
                margin-bottom: var(--space-4);
                padding: var(--space-4);
                border-radius: var(--radius-lg);
                background: var(--flows-employee-chip-active-bg);
                border: 1px solid var(--flows-employee-chip-active-border);
            }

            .hero-icon {
                flex-shrink: 0;
                width: 48px;
                height: 48px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                background: var(--glass-solid-strong);
                box-shadow: var(--flows-employee-badge-glow);
            }

            .hero-copy {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-width: 0;
            }

            .hero-title {
                margin: 0;
                font-size: var(--text-md);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .hero-subtitle {
                margin: 0;
                font-size: var(--text-xs);
                line-height: 1.5;
                color: var(--text-secondary);
            }

            .field {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                margin-bottom: var(--space-3);
            }

            .toggle-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
            }

            .toggle-label {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
            }

            .toggle-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }

            .toggle-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
            }

            .section-title {
                margin: 0 0 var(--space-2);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .section-hint {
                margin: 0 0 var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.5;
            }

            .members-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                max-height: 240px;
                overflow-y: auto;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
            }

            .member-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                border-radius: var(--radius-sm);
                cursor: pointer;
                border: 1px solid transparent;
            }

            .member-row:hover {
                background: var(--glass-solid-medium);
            }

            .member-row[data-selected='true'] {
                border-color: var(--flows-employee-chip-active-border);
                background: var(--flows-employee-chip-active-bg);
            }

            .member-check {
                flex-shrink: 0;
                width: 20px;
                height: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--accent);
            }

            .member-row[data-selected='true'] .member-check {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }

            .members-empty {
                padding: var(--space-3);
                text-align: center;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .flow-id {
                font-family: var(--font-mono);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.flowId = '';
        this._enabled = false;
        this._displayName = '';
        this._avatarUrl = '';
        this._curatorUserIds = [];
        this._membersFilter = '';
        this._hydrated = false;
        this._flows = this.useResource('flows/flows');
        this._update = this.useOp('flows/flow_update');
        this._editor = this.useOp('flows/editor');
        this._teamMembersSel = this.select((s) => s.team.members);
        this._teamLoadingSel = this.select((s) => s.team.loading);
        this._authSel = this.select((s) => s.auth.user);
    }

    connectedCallback() {
        super.connectedCallback();
        const members = this._teamMembersSel.value;
        const loading = this._teamLoadingSel.value;
        if (!Array.isArray(members) || members.length === 0) {
            if (!loading) {
                this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
            }
        }
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('flowId') && this.flowId) {
            this._hydrated = false;
            this._enabled = false;
            this._displayName = '';
            this._avatarUrl = '';
            this._curatorUserIds = [];
            this._membersFilter = '';
        }
        if (!this._hydrated && this.flowId) {
            const item = asArray(this._flows.items).find((f) => f && f.flow_id === this.flowId);
            if (item) {
                this._hydrateFromItem(item);
            } else {
                this._flows.get(this.flowId);
            }
        }
    }

    _hydrateFromItem(item) {
        const employee = isPlainObject(item.employee) ? item.employee : emptyEmployee();
        this._enabled = employee.enabled === true;
        this._displayName =
            typeof employee.display_name === 'string' && employee.display_name.length > 0
                ? employee.display_name
                : '';
        this._avatarUrl =
            typeof employee.avatar_url === 'string' && employee.avatar_url.length > 0
                ? employee.avatar_url
                : '';
        this._curatorUserIds = Array.isArray(employee.curator_user_ids)
            ? employee.curator_user_ids.filter((id) => typeof id === 'string' && id.length > 0)
            : [];
        if (this._enabled && this._curatorUserIds.length === 0) {
            const me = this._authSel.value;
            const myId =
                me && typeof me.user_id === 'string' && me.user_id.length > 0 ? me.user_id : null;
            if (myId) {
                this._curatorUserIds = [myId];
            }
        }
        this._hydrated = true;
        this.isDirty = false;
    }

    _humanMembers() {
        const members = this._teamMembersSel.value;
        if (!Array.isArray(members)) {
            return [];
        }
        const q = this._membersFilter.trim().toLowerCase();
        return members
            .filter((m) => m && typeof m.user_id === 'string' && m.user_id.length > 0)
            .filter((m) => m.is_flow_employee !== true)
            .filter((m) => {
                if (q.length === 0) {
                    return true;
                }
                const name = typeof m.name === 'string' ? m.name.toLowerCase() : '';
                const email = typeof m.email === 'string' ? m.email.toLowerCase() : '';
                return name.includes(q) || email.includes(q) || m.user_id.toLowerCase().includes(q);
            });
    }

    _isSelected(userId) {
        return this._curatorUserIds.indexOf(userId) !== -1;
    }

    _toggleCurator(userId) {
        const idx = this._curatorUserIds.indexOf(userId);
        const next = this._curatorUserIds.slice();
        if (idx === -1) {
            next.push(userId);
        } else {
            next.splice(idx, 1);
        }
        this._curatorUserIds = next;
        this.isDirty = true;
    }

    _onEnableChange(checked) {
        this._enabled = checked === true;
        if (this._enabled && this._curatorUserIds.length === 0) {
            const me = this._authSel.value;
            const myId =
                me && typeof me.user_id === 'string' && me.user_id.length > 0 ? me.user_id : null;
            if (myId) {
                this._curatorUserIds = [myId];
            }
        }
        this.isDirty = true;
    }

    _buildEmployeePayload() {
        if (!this._enabled) {
            return {
                enabled: false,
                roles: [],
                curator_user_ids: [],
                display_name: null,
                avatar_url: null,
            };
        }
        const display = this._displayName.trim();
        const avatar = this._avatarUrl.trim();
        return {
            enabled: true,
            roles: DEFAULT_EMPLOYEE_ROLES.slice(),
            curator_user_ids: this._curatorUserIds.slice(),
            display_name: display.length > 0 ? display : null,
            avatar_url: avatar.length > 0 ? avatar : null,
        };
    }

    _canSubmit() {
        if (!this._hydrated || !this.flowId) {
            return false;
        }
        if (!this._enabled) {
            return true;
        }
        return this._curatorUserIds.length > 0;
    }

    renderHeader() {
        return html`
            <h3>
                ${this.t('employee_settings_modal.title')}
                <span class="flow-id">${this.flowId}</span>
            </h3>
        `;
    }

    renderBody() {
        if (!this._hydrated) {
            return html`<div class="members-empty"><glass-spinner></glass-spinner></div>`;
        }
        const candidates = this._humanMembers();
        const teamLoading = this._teamLoadingSel.value === true;
        return html`
            <div class="hero">
                <div class="hero-icon">
                    <platform-icon name="ai" size="28"></platform-icon>
                </div>
                <div class="hero-copy">
                    <p class="hero-title">${this.t('employee_settings_modal.hero_title')}</p>
                    <p class="hero-subtitle">${this.t('employee_settings_modal.hero_subtitle')}</p>
                </div>
            </div>

            <div class="toggle-row">
                <div class="toggle-label">
                    <span class="toggle-title">${this.t('employee_settings_modal.enable')}</span>
                    <span class="toggle-hint">${this.t('employee_settings_modal.enable_hint')}</span>
                </div>
                <platform-switch
                    .checked=${this._enabled}
                    @change=${(e) => {
                        if (!e.detail || typeof e.detail.value !== 'boolean') {
                            throw new Error('employee_settings: switch expects detail.value boolean');
                        }
                        this._onEnableChange(e.detail.value);
                    }}
                ></platform-switch>
            </div>

            ${this._enabled
                ? html`
                      <div class="field">
                          <platform-field
                              type="string"
                              mode="edit"
                              .label=${this.t('employee_settings_modal.display_name')}
                              .value=${this._displayName}
                              placeholder=${this.t('employee_settings_modal.display_name_placeholder')}
                              @change=${(e) => {
                                  if (!e.detail || typeof e.detail.value !== 'string') {
                                      throw new Error('employee_settings: display_name expects string');
                                  }
                                  this._displayName = e.detail.value;
                                  this.isDirty = true;
                              }}
                          ></platform-field>
                      </div>
                      <div class="field">
                          <platform-field
                              type="string"
                              input-type="url"
                              mode="edit"
                              .label=${this.t('employee_settings_modal.avatar_url')}
                              .value=${this._avatarUrl}
                              placeholder=${this.t('employee_settings_modal.avatar_url_placeholder')}
                              @change=${(e) => {
                                  if (!e.detail || typeof e.detail.value !== 'string') {
                                      throw new Error('employee_settings: avatar_url expects string');
                                  }
                                  this._avatarUrl = e.detail.value;
                                  this.isDirty = true;
                              }}
                          ></platform-field>
                      </div>
                      <h4 class="section-title">${this.t('employee_settings_modal.curators')}</h4>
                      <p class="section-hint">${this.t('employee_settings_modal.curators_hint')}</p>
                      <div class="field">
                          <platform-field
                              type="string"
                              mode="edit"
                              .label=${this.t('employee_settings_modal.curators_filter')}
                              .value=${this._membersFilter}
                              placeholder=${this.t('employee_settings_modal.curators_filter_placeholder')}
                              @change=${(e) => {
                                  if (!e.detail || typeof e.detail.value !== 'string') {
                                      throw new Error('employee_settings: filter expects string');
                                  }
                                  this._membersFilter = e.detail.value;
                              }}
                          ></platform-field>
                      </div>
                      <div class="members-list">
                          ${teamLoading && candidates.length === 0
                              ? html`<div class="members-empty"><glass-spinner></glass-spinner></div>`
                              : nothing}
                          ${!teamLoading && candidates.length === 0
                              ? html`<div class="members-empty">
                                    ${this.t('employee_settings_modal.curators_empty')}
                                </div>`
                              : nothing}
                          ${candidates.map(
                              (m) => html`
                                  <article
                                      class="member-row"
                                      role="button"
                                      tabindex="0"
                                      data-selected=${this._isSelected(m.user_id) ? 'true' : 'false'}
                                      @click=${() => this._toggleCurator(m.user_id)}
                                      @keydown=${(e) => {
                                          if (e.key === 'Enter' || e.key === ' ') {
                                              e.preventDefault();
                                              this._toggleCurator(m.user_id);
                                          }
                                      }}
                                  >
                                      <span class="member-check" aria-hidden="true">
                                          ${this._isSelected(m.user_id)
                                              ? html`<platform-icon name="check" size="12"></platform-icon>`
                                              : nothing}
                                      </span>
                                      <platform-user-chip
                                          user-id=${m.user_id}
                                          size="md"
                                          ?interactive=${false}
                                      ></platform-user-chip>
                                  </article>
                              `,
                          )}
                      </div>
                  `
                : nothing}
        `;
    }

    renderFooter() {
        const busy = this._update.busy === true;
        const canSubmit = this._canSubmit();
        return html`
            <platform-button @click=${() => this.close()}>
                ${this.t('common.action_cancel')}
            </platform-button>
            <platform-button
                variant="primary"
                ?disabled=${!canSubmit || busy}
                @click=${() => {
                    void this._onSubmit();
                }}
            >
                ${this.t('employee_settings_modal.action_save')}
            </platform-button>
        `;
    }

    async _onSubmit() {
        if (!this.flowId || !this._canSubmit()) {
            return;
        }
        if (this._enabled && this._curatorUserIds.length === 0) {
            this.toast('employee_settings_modal.error_curators_required', { type: 'error' });
            return;
        }
        const item = asArray(this._flows.items).find((f) => f && f.flow_id === this.flowId);
        if (!item) {
            throw new Error('flows-employee-settings-modal: flow item not loaded');
        }
        const employee = this._buildEmployeePayload();
        const body = { ...item, employee };
        await this._update.run({ ...body, flow_id: this.flowId });

        const editorState = this._editor.state;
        if (
            isPlainObject(editorState) &&
            isPlainObject(editorState.flowConfig) &&
            editorState.flowConfig.flow_id === this.flowId
        ) {
            const wasDirty = editorState.isDirty === true;
            this._editor.patchFlowConfig({ patch: { employee } });
            if (!wasDirty) {
                this._editor.setDirty({ dirty: false });
            }
        }

        this.toast('employee_settings_modal.toast_saved', { type: 'success' });
        this.closeAfterSave();
    }
}

customElements.define('flows-employee-settings-modal', FlowsEmployeeSettingsModal);
registerModalKind(FlowsEmployeeSettingsModal.modalKind, 'flows-employee-settings-modal');
