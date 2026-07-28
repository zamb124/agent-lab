/**
 * Доступ к странице: видимость, участники и публичная ссылка.
 *
 * Ограниченная видимость и список участников — одно решение: пока страница
 * видна всей компании, персональные гранты не имеют смысла, поэтому список
 * появляется только вместе с ограничением.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { TEAM_EVENTS } from '@platform/lib/events/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-user-chip.js';

const VISIBILITY_COMPANY = 'company';
const VISIBILITY_RESTRICTED = 'restricted';

export class WikiPageAccessModal extends PlatformModal {
    static modalKind = 'wiki.page_access';
    static i18nNamespace = 'wiki';

    static properties = {
        pageId: { type: String, attribute: 'page-id' },
        _newMemberId: { state: true },
        _newPermission: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .grid {
                display: grid;
                gap: var(--space-4);
            }

            .row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
            }

            .section-title {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: var(--tracking-wide);
                text-transform: uppercase;
            }

            .member {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .member-permission {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .muted {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            .add-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) 10rem auto;
                gap: var(--space-2);
                align-items: end;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.pageId = '';
        this._newMemberId = '';
        this._newPermission = 'view';
        this._access = this.useOp('wiki/access_read');
        this._memberAdd = this.useOp('wiki/member_add');
        this._memberRemove = this.useOp('wiki/member_remove');
        this._publicLink = this.useOp('wiki/public_link');
        this._properties = this.useOp('wiki/page_properties');
        this._pages = this.useResource('wiki/pages');
        this._teamMembersSel = this.select((s) => s.team.members);
        this._teamLoadingSel = this.select((s) => s.team.loading);
    }

    connectedCallback() {
        super.connectedCallback();
        void this._access.run({ wiki_page_id: this.pageId });
        const members = this._teamMembersSel.value;
        const loading = this._teamLoadingSel.value;
        if ((!Array.isArray(members) || members.length === 0) && !loading) {
            this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        }
    }

    _state() {
        return this._access.state;
    }

    _isRestricted() {
        return this._state().visibility === VISIBILITY_RESTRICTED;
    }

    async _onVisibilityToggle(event) {
        const restricted = event.detail.checked;
        await this._properties.run({
            wiki_page_id: this.pageId,
            visibility: restricted ? VISIBILITY_RESTRICTED : VISIBILITY_COMPANY,
        });
        await this._access.run({ wiki_page_id: this.pageId });
        void this._pages.load();
    }

    async _addMember() {
        if (this._newMemberId === '') {
            return;
        }
        await this._memberAdd.run({
            wiki_page_id: this.pageId,
            user_id: this._newMemberId,
            permission: this._newPermission,
        });
        this._newMemberId = '';
        await this._access.run({ wiki_page_id: this.pageId });
    }

    async _removeMember(userId) {
        await this._memberRemove.run({ wiki_page_id: this.pageId, member_user_id: userId });
        await this._access.run({ wiki_page_id: this.pageId });
    }

    async _togglePublicLink(event) {
        await this._publicLink.run({
            wiki_page_id: this.pageId,
            enabled: event.detail.checked,
            permission: 'view',
        });
        await this._access.run({ wiki_page_id: this.pageId });
    }

    _copyLink() {
        const token = this._state().public_link_token;
        if (typeof token !== 'string' || token === '') {
            return;
        }
        const url = `${window.location.origin}/wiki/s/${token}`;
        this.copyToClipboard(url, {
            success_i18n_key: 'wiki:access.link_copied',
            error_i18n_key: 'wiki:toast.access.link_failed',
        });
    }

    _permissionConfig() {
        return {
            values: [
                { value: 'view', label: this.t('access.permission_view') },
                { value: 'comment', label: this.t('access.permission_comment') },
                { value: 'edit', label: this.t('access.permission_edit') },
            ],
        };
    }

    _memberConfig() {
        const granted = new Set(this._members().map((member) => member.user_id));
        const team = this._teamMembersSel.value;
        if (!Array.isArray(team)) {
            throw new Error('wiki page access: state.team.members must be array');
        }
        const values = team
            .filter((member) => member && typeof member.user_id === 'string' && !granted.has(member.user_id))
            .map((member) => ({
                value: member.user_id,
                label: typeof member.name === 'string' && member.name.length > 0
                    ? member.name
                    : member.user_id,
            }));
        return { values };
    }

    _members() {
        const members = this._state().members;
        return Array.isArray(members) ? members : [];
    }

    renderHeader() {
        return this.t('access.title');
    }

    renderBody() {
        const linkEnabled = this._state().public_link_enabled === true;
        return html`
            <div class="grid">
                <div class="row">
                    <span>${this.t('access.visibility_label')}</span>
                    <platform-switch
                        data-wiki-visibility
                        ?checked=${this._isRestricted()}
                        label=${this.t('access.visibility_restricted')}
                        @change=${this._onVisibilityToggle}
                    ></platform-switch>
                </div>

                ${this._isRestricted() ? this._renderMembers() : nothing}

                <div>
                    <div class="section-title">${this.t('access.link_title')}</div>
                    <div class="row">
                        <platform-switch
                            data-wiki-public-link
                            ?checked=${linkEnabled}
                            label=${this.t('access.link_enable')}
                            @change=${this._togglePublicLink}
                        ></platform-switch>
                        ${linkEnabled
                            ? html`<platform-button
                                  variant="ghost"
                                  size="sm"
                                  data-wiki-copy-link
                                  @click=${this._copyLink}
                              >${this.t('access.link_copy')}</platform-button>`
                            : html`<span class="muted">${this.t('access.link_disabled')}</span>`}
                    </div>
                </div>
            </div>
        `;
    }

    _renderMembers() {
        const members = this._members();
        return html`
            <div>
                <div class="section-title">${this.t('access.members_title')}</div>
                ${members.length === 0
                    ? html`<div class="muted">${this.t('access.members_empty')}</div>`
                    : members.map((member) => html`
                          <div class="member" data-wiki-member=${member.user_id}>
                              <platform-user-chip user-id=${member.user_id} size="sm"></platform-user-chip>
                              <span class="member-permission">
                                  ${this.t(`access.permission_${member.permission}`)}
                              </span>
                              <platform-button
                                  variant="ghost"
                                  size="sm"
                                  @click=${() => this._removeMember(member.user_id)}
                              >${this.t('access.member_remove')}</platform-button>
                          </div>
                      `)}
                <div class="add-row">
                    <platform-field
                        type="enum"
                        mode="edit"
                        label=${this.t('access.member_add')}
                        .value=${this._newMemberId}
                        .config=${this._memberConfig()}
                        @change=${(event) => { this._newMemberId = event.detail.value; }}
                    ></platform-field>
                    <platform-field
                        type="enum"
                        mode="edit"
                        label=${this.t('access.visibility_label')}
                        .value=${this._newPermission}
                        .config=${this._permissionConfig()}
                        @change=${(event) => { this._newPermission = event.detail.value; }}
                    ></platform-field>
                    <platform-button variant="primary" data-wiki-member-add @click=${this._addMember}>
                        <platform-icon name="plus" size="16"></platform-icon>
                    </platform-button>
                </div>
            </div>
        `;
    }
}

customElements.define('wiki-page-access-modal', WikiPageAccessModal);
registerModalKind(WikiPageAccessModal.modalKind, 'wiki-page-access-modal');
