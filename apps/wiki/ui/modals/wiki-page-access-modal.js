/**
 * Доступ к странице: публикация, участники и публичная ссылка.
 *
 * Ограничение доступа задаётся флагом `company_visible` на самой странице:
 * `false` — видят только явные участники (FGA `viewer`/`editor` + `owner`),
 * `true` — видна всей компании. Переключатель «только участники» просто
 * патчит `company_visible`; владелец страницы уже имеет `can_admin` через
 * FGA `owner` relation, добавлять его отдельным участником не нужно.
 *
 * Адрес публичной ссылки в базе лежит хешем, поэтому показать его можно только
 * сразу после выпуска. Позже остаётся перевыпуск с новым адресом.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { TEAM_EVENTS } from '@platform/lib/events/index.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-user-chip.js';

const RELATION_VIEWER = 'viewer';
const LINK_PERMISSION_VIEWER = 'viewer';

export class WikiPageAccessModal extends PlatformModal {
    static modalKind = 'wiki.page_access';
    static i18nNamespace = 'wiki';

    static properties = {
        pageId: { type: String, attribute: 'page-id' },
        _newMemberId: { state: true },
        _newRelation: { state: true },
        /** Адрес известен только в этой сессии — сразу после выпуска ссылки. */
        _issuedLinkUrl: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .grid {
                display: grid;
                gap: var(--space-5);
            }

            .row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
            }

            .section-title {
                margin-bottom: var(--space-2);
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

            .hint {
                margin-top: var(--space-1);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .warning {
                margin-top: var(--space-1);
                color: var(--warning);
                font-size: var(--text-xs);
            }

            .muted {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            .link-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-top: var(--space-2);
            }

            .link-url {
                flex: 1;
                min-width: 0;
                padding: var(--space-2);
                border-radius: var(--radius-sm);
                background: var(--wiki-surface-muted);
                color: var(--text-secondary);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                overflow-wrap: anywhere;
            }

            .link-icon-actions {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
            }

            .add-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) 12rem auto;
                gap: var(--space-2);
                align-items: end;
                margin-top: var(--space-3);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.pageId = '';
        this._newMemberId = '';
        this._newRelation = RELATION_VIEWER;
        this._issuedLinkUrl = '';
        this._access = this.useOp('wiki/access_read');
        this._page = this.useOp('wiki/page_read');
        this._companyVisible = this.useOp('wiki/company_visible');
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
        void this._page.run({ wiki_page_id: this.pageId });
        const members = this._teamMembersSel.value;
        const loading = this._teamLoadingSel.value;
        if ((!Array.isArray(members) || members.length === 0) && !loading) {
            this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        }
    }

    _accessState() {
        return this._access.lastResult;
    }

    _members() {
        const access = this._accessState();
        return access && Array.isArray(access.members) ? access.members : [];
    }

    _isRestricted() {
        const access = this._accessState();
        return Boolean(access) && access.company_visible === false;
    }

    /** Ограничение с предка снимается только на самом предке. */
    _inheritedFromAncestorId() {
        const access = this._accessState();
        if (!access || typeof access.inherited_from_page_id !== 'string') {
            return '';
        }
        return access.inherited_from_page_id === this.pageId ? '' : access.inherited_from_page_id;
    }

    _isPublished() {
        const page = this._page.lastResult;
        return Boolean(page) && page.is_published === true;
    }

    _linkEnabled() {
        const access = this._accessState();
        return Boolean(access) && access.link_enabled === true;
    }

    _linkPermission() {
        const access = this._accessState();
        return access && typeof access.link_permission === 'string'
            ? access.link_permission
            : LINK_PERMISSION_VIEWER;
    }

    async _reload() {
        await this._access.run({ wiki_page_id: this.pageId });
        void this._pages.load();
    }

    // --- публикация ---

    async _onPublishToggle(event) {
        await this._properties.run({
            wiki_page_id: this.pageId,
            is_published: Boolean(event.detail.value),
        });
        await this._page.run({ wiki_page_id: this.pageId });
        void this._pages.load();
    }

    // --- участники ---

    async _onRestrictedToggle(event) {
        await this._companyVisible.run({
            wiki_page_id: this.pageId,
            company_visible: !Boolean(event.detail.value),
        });
        await this._reload();
    }

    async _addMember() {
        if (this._newMemberId === '') {
            return;
        }
        await this._memberAdd.run({
            wiki_page_id: this.pageId,
            user_id: this._newMemberId,
            relation: this._newRelation,
        });
        this._newMemberId = '';
        await this._reload();
    }

    async _removeMember(userId) {
        await this._memberRemove.run({ wiki_page_id: this.pageId, member_user_id: userId });
        await this._reload();
    }

    // --- публичная ссылка ---

    async _onLinkToggle(event) {
        const result = await this._publicLink.run({
            wiki_page_id: this.pageId,
            enabled: Boolean(event.detail.value),
            permission: this._linkPermission(),
            origin: location.origin,
        });
        this._issuedLinkUrl = result && typeof result.url === 'string' ? result.url : '';
        await this._reload();
    }

    async _onLinkPermissionChange(event) {
        const result = await this._publicLink.run({
            wiki_page_id: this.pageId,
            enabled: true,
            permission: event.detail.value,
            origin: location.origin,
        });
        this._issuedLinkUrl = result && typeof result.url === 'string' ? result.url : '';
        await this._reload();
    }

    async _rotateLink() {
        const confirmed = await platformConfirm(this.t('access.link_rotate_confirm_body'), {
            title: this.t('access.link_rotate_confirm_title'),
        });
        if (!confirmed) {
            return;
        }
        const result = await this._publicLink.run({
            wiki_page_id: this.pageId,
            enabled: true,
            permission: this._linkPermission(),
            origin: location.origin,
        });
        this._issuedLinkUrl = result && typeof result.url === 'string' ? result.url : '';
        await this._reload();
    }

    /** Сайт открывается отдельной вкладкой: в текущей остаётся редактирование. */
    _openSite() {
        if (this._issuedLinkUrl === '') {
            return;
        }
        window.open(this._issuedLinkUrl, '_blank', 'noopener');
    }

    _copyLink() {
        if (this._issuedLinkUrl === '') {
            return;
        }
        this.copyToClipboard(this._issuedLinkUrl, {
            success_i18n_key: 'wiki:access.link_copied',
            error_i18n_key: 'wiki:toast.access.link_failed',
        });
    }

    // --- справочники полей ---

    _relationConfig() {
        return {
            values: [
                { value: 'viewer', label: this.t('access.relation_viewer') },
                { value: 'editor', label: this.t('access.relation_editor') },
            ],
        };
    }

    _linkPermissionConfig() {
        return {
            values: [
                { value: 'viewer', label: this.t('access.link_permission_viewer') },
                { value: 'editor', label: this.t('access.link_permission_editor') },
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

    renderHeader() {
        return this.t('access.title');
    }

    renderBody() {
        if (!this._accessState()) {
            return html`<div class="muted">${this.t('access.loading')}</div>`;
        }
        return html`
            <div class="grid">
                ${this._renderPublish()}
                ${this._renderVisibility()}
                ${this._isRestricted() ? this._renderMembers() : nothing}
                ${this._renderPublicLink()}
            </div>
        `;
    }

    _renderPublish() {
        return html`
            <div>
                <div class="section-title">${this.t('access.publish_title')}</div>
                <div class="row">
                    <platform-switch
                        data-wiki-publish
                        ?checked=${this._isPublished()}
                        label=${this.t('access.publish_label')}
                        @change=${this._onPublishToggle}
                    ></platform-switch>
                </div>
                <div class="hint">${this.t('access.publish_hint')}</div>
            </div>
        `;
    }

    _renderVisibility() {
        const inheritedFrom = this._inheritedFromAncestorId();
        return html`
            <div>
                <div class="section-title">${this.t('access.visibility_label')}</div>
                <div class="row">
                    <platform-switch
                        data-wiki-visibility
                        ?checked=${this._isRestricted()}
                        ?disabled=${inheritedFrom !== ''}
                        label=${this.t('access.visibility_restricted')}
                        @change=${this._onRestrictedToggle}
                    ></platform-switch>
                </div>
                <div class="hint">
                    ${this._isRestricted()
                        ? this.t('access.visibility_restricted_hint')
                        : this.t('access.visibility_company_hint')}
                </div>
                ${inheritedFrom === ''
                    ? nothing
                    : html`<div class="warning">
                          ${this.t('access.inherited')}
                          <platform-button
                              variant="ghost"
                              size="sm"
                              data-wiki-inherited-open
                              @click=${() => {
                                  this.close();
                                  this.navigate('wiki_page', { pageId: inheritedFrom });
                              }}
                          >${this.t('access.inherited_open')}</platform-button>
                      </div>`}
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
                                  ${this.t(`access.relation_${member.relation}`)}
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
                        label=${this.t('access.relation_label')}
                        .value=${this._newRelation}
                        .config=${this._relationConfig()}
                        @change=${(event) => { this._newRelation = event.detail.value; }}
                    ></platform-field>
                    <platform-button variant="primary" data-wiki-member-add @click=${this._addMember}>
                        <platform-icon name="plus" size="16"></platform-icon>
                    </platform-button>
                </div>
            </div>
        `;
    }

    _renderPublicLink() {
        const enabled = this._linkEnabled();
        return html`
            <div>
                <div class="section-title">${this.t('access.link_title')}</div>
                <div class="row">
                    <platform-switch
                        data-wiki-public-link
                        ?checked=${enabled}
                        label=${this.t('access.link_enable')}
                        @change=${this._onLinkToggle}
                    ></platform-switch>
                    ${enabled ? nothing : html`<span class="muted">${this.t('access.link_disabled')}</span>`}
                </div>
                ${enabled ? this._renderLinkDetails() : nothing}
            </div>
        `;
    }

    _renderLinkDetails() {
        return html`
            <platform-field
                type="enum"
                mode="edit"
                label=${this.t('access.link_permission_label')}
                .value=${this._linkPermission()}
                .config=${this._linkPermissionConfig()}
                @change=${this._onLinkPermissionChange}
            ></platform-field>
            <div class="hint">${this.t('access.link_subtree_hint')}</div>
            ${this._isPublished() ? nothing : html`<div class="warning">${this.t('access.link_draft_warning')}</div>`}
            ${this._issuedLinkUrl === ''
                ? html`
                    <div class="hint">${this.t('access.link_hidden')}</div>
                    <platform-button
                        variant="ghost"
                        size="sm"
                        data-wiki-rotate-link
                        @click=${this._rotateLink}
                    >${this.t('access.link_rotate')}</platform-button>
                `
                : html`
                    <div class="link-actions">
                        <div class="link-url" data-wiki-link-url>${this._issuedLinkUrl}</div>
                        <div class="link-icon-actions">
                            <platform-button
                                variant="ghost"
                                icon-only
                                size="sm"
                                data-wiki-copy-link
                                title=${this.t('access.link_copy')}
                                aria-label=${this.t('access.link_copy')}
                                @click=${this._copyLink}
                            >
                                <platform-icon name="copy" size="16"></platform-icon>
                            </platform-button>
                            <platform-button
                                variant="ghost"
                                icon-only
                                size="sm"
                                data-wiki-open-site
                                title=${this.t('access.link_open_site')}
                                aria-label=${this.t('access.link_open_site')}
                                @click=${this._openSite}
                            >
                                <platform-icon name="external-link" size="16"></platform-icon>
                            </platform-button>
                        </div>
                    </div>
                `}
        `;
    }
}

customElements.define('wiki-page-access-modal', WikiPageAccessModal);
registerModalKind(WikiPageAccessModal.modalKind, 'wiki-page-access-modal');
