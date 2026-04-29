/**
 * Страница создания сущности: unified crm-entity-card в режиме create.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '../components/entity-card.js';

export class CRMEntityCreatePage extends PlatformPage {
    static i18nNamespace = 'crm';

    static styles = [
        PlatformPage.styles,
        css`
            :host { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; }
            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .header-wrap { flex-shrink: 0; padding: 0 var(--space-4); }
            .body {
                flex: 1;
                min-height: 0;
                padding: var(--space-4);
                overflow: auto;
                display: flex;
                justify-content: center;
            }
            .body crm-entity-card {
                flex: 1;
                max-width: 880px;
                width: 100%;
                height: min(100%, 900px);
                min-height: 420px;
            }
        `,
    ];

    render() {
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${this.t('routes.entity_new')}></platform-breadcrumbs>
            </div>
            <div class="header-wrap">
                <page-header title=${this.t('entity_detail_page.create_title')}></page-header>
            </div>
            <div class="body">
                <crm-entity-card
                    surface="page"
                    panel-mode="create"
                    @entity-created=${this._onEntityCreated}
                    @create-cancelled=${() => this.navigate('entities')}
                ></crm-entity-card>
            </div>
        `;
    }

    _onEntityCreated(event) {
        const d = event.detail;
        if (!d || typeof d.entity_id !== 'string') {
            throw new Error('entity-created: entity_id required');
        }
        this.navigate('entity', { itemId: d.entity_id });
    }
}

customElements.define('crm-entity-create-page', CRMEntityCreatePage);
