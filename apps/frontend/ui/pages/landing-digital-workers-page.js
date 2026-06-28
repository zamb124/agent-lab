/**
 * Публичный каталог демо-агентов: карточки + пробный чат через platform-embed-chat-drawer.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import '@platform/lib/embed-chat/platform-embed-chat-drawer.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

export class LandingDigitalWorkersPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static properties = {
        _drawerSpec: { state: true },
        _drawerOpen: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        ...marketingPublicContentPageStyles,
        css`
            .marketing-digital-workers {
                max-width: var(--marketing-content-max-width);
            }

            platform-breadcrumbs {
                display: block;
                margin-bottom: var(--space-6);
            }

            .marketing-digital-workers-disclaimer {
                max-width: 48rem;
                margin: 0 auto var(--space-10);
                padding: var(--space-4);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-bg-subtle);
                font-size: var(--text-sm);
                line-height: var(--leading-relaxed);
                color: var(--text-tertiary);
                text-align: center;
            }

            .marketing-digital-workers-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-6);
            }

            .marketing-digital-workers-card {
                overflow: hidden;
                padding: 0;
                display: flex;
                flex-direction: column;
            }

            .marketing-digital-workers-card-image {
                width: 100%;
                aspect-ratio: 16 / 10;
                object-fit: cover;
            }

            .marketing-digital-workers-card-body {
                padding: var(--space-6);
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                flex: 1;
            }

            .marketing-digital-workers-card-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                margin: 0;
                color: var(--text-primary);
            }

            .marketing-digital-workers-card-desc {
                font-size: var(--text-base);
                line-height: var(--leading-relaxed);
                color: var(--text-secondary);
                margin: 0;
                flex: 1;
            }

            .marketing-digital-workers-card-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3);
            }

            .marketing-digital-workers-state {
                display: grid;
                place-items: center;
                min-height: 12rem;
                color: var(--text-secondary);
            }

            .marketing-digital-workers-state.is-error {
                color: var(--error);
            }
        `,
    ];

    constructor() {
        super();
        this._drawerSpec = null;
        this._drawerOpen = false;
        this._load = this.useOp('frontend/landing_agents_load');
        this._session = this.useOp('frontend/landing_demo_session');
        if (typeof window === 'undefined' || typeof window.location.origin !== 'string') {
            throw new Error('landing_digital_workers_page: window.location.origin required');
        }
        this._flowsBaseUrl = new URL('/flows', window.location.origin).href;
        this._voiceBaseUrl = new URL('/voice', window.location.origin).href;
    }

    /** Публичные демо-виджеты: guest JWT с company_id `system`. */
    static embedDemoCompanyId = 'system';

    _onEmbedDrawerToast(e) {
        const detail = e && typeof e.detail === 'object' ? e.detail : null;
        const msg = typeof detail?.message === 'string' ? detail.message.trim() : '';
        if (msg === '') {
            return;
        }
        this.toast('digital_workers.embed_voice_message', { type: 'warning', vars: { detail: msg } });
    }

    _drawerVoiceEnabled() {
        const s = this._drawerSpec;
        return s !== null && s.voice_enabled === true;
    }

    _drawerVoiceDefaultOn() {
        const s = this._drawerSpec;
        return s !== null && s.voice_enabled === true && s.voice_default_on === true;
    }

    _onDrawerOpenChanged(e) {
        const d = e.detail;
        if (d && typeof d.open === 'boolean') {
            this._drawerOpen = d.open;
        }
    }

    connectedCallback() {
        super.connectedCallback();
        this._load.run(null);
    }

    _getDemoAuthHeaders = async () => {
        const spec = this._drawerSpec;
        if (!spec || typeof spec.embed_id !== 'string' || spec.embed_id === '') {
            throw new Error('landing_digital_workers: drawer embed context missing');
        }
        const result = await this._session.run({ embed_id: spec.embed_id });
        if (result === null) {
            const msg = this._session.error;
            if (typeof msg === 'string' && msg !== '') {
                this.toast('digital_workers.session_error', {
                    type: 'error',
                    vars: { detail: msg },
                });
            } else {
                this.toast('digital_workers.session_error_generic', { type: 'error' });
            }
            return {};
        }
        if (typeof result.token !== 'string' || result.token === '') {
            throw new Error('landing_digital_workers: session token missing');
        }
        return { Authorization: `Bearer ${result.token}` };
    };

    _tryAgent(card) {
        if (typeof card.embed_id !== 'string' || card.embed_id === '') {
            throw new Error('landing_digital_workers: card.embed_id required');
        }
        if (typeof card.flow_id !== 'string' || card.flow_id === '') {
            throw new Error('landing_digital_workers: card.flow_id required');
        }
        if (typeof card.branch_id !== 'string' || card.branch_id === '') {
            throw new Error('landing_digital_workers: card.branch_id required');
        }
        const title =
            typeof card.assistant_title === 'string' && card.assistant_title.trim() !== ''
                ? card.assistant_title.trim()
                : card.name;
        const theme = card.theme === 'light' || card.theme === 'dark' || card.theme === 'auto' ? card.theme : 'dark';
        const locale =
            card.interface_locale === 'ru' || card.interface_locale === 'en' ? card.interface_locale : 'auto';
        if (typeof card.voice_enabled !== 'boolean') {
            throw new Error('landing_digital_workers: card.voice_enabled must be boolean');
        }
        if (typeof card.voice_default_on !== 'boolean') {
            throw new Error('landing_digital_workers: card.voice_default_on must be boolean');
        }
        this._drawerSpec = {
            embed_id: card.embed_id,
            flow_id: card.flow_id,
            branch_id: card.branch_id,
            assistant_title: title,
            theme,
            interface_locale: locale,
            voice_enabled: card.voice_enabled,
            voice_default_on: card.voice_default_on === true,
        };
        this._drawerOpen = true;
        this.requestUpdate();
    }

    _hire() {
        this.openModal('auth.login');
    }

    _itemsList() {
        const raw = this._load.lastResult;
        if (raw === null || typeof raw !== 'object') {
            return [];
        }
        const items = raw.items;
        if (!Array.isArray(items)) {
            throw new Error('landing_digital_workers: items must be array');
        }
        return items;
    }

    render() {
        const busy = this._load.busy;
        const err = this._load.error;
        const items = this._itemsList();

        return html`
            <landing-header></landing-header>
            <div class="marketing-page-container">
                <div class="marketing-content marketing-digital-workers">
                    <platform-breadcrumbs></platform-breadcrumbs>
                    <header class="marketing-content-hero">
                        <h1 class="marketing-content-title">${this.t('digital_workers.title')}</h1>
                        <p class="marketing-content-lede">${this.t('digital_workers.subtitle')}</p>
                    </header>
                    <p class="marketing-digital-workers-disclaimer">${this.t('digital_workers.disclaimer')}</p>

                    ${busy && items.length === 0
                        ? html`<div class="marketing-digital-workers-state"><glass-spinner></glass-spinner></div>`
                        : ''}
                    ${err !== null && items.length === 0
                        ? html`<div class="marketing-digital-workers-state is-error">${this.t('digital_workers.load_error')}</div>`
                        : ''}
                    ${!busy && err === null && items.length === 0
                        ? html`<div class="marketing-digital-workers-state">${this.t('digital_workers.empty')}</div>`
                        : ''}

                    ${items.length > 0
                        ? html`
                              <div class="marketing-digital-workers-grid">
                                  ${items.map(
                                      (card) => html`
                                          <article class="marketing-content-card glass-medium marketing-digital-workers-card">
                                              <img
                                                  class="marketing-digital-workers-card-image"
                                                  src=${card.landing_card_image_url}
                                                  alt=""
                                                  loading="lazy"
                                              />
                                              <div class="marketing-digital-workers-card-body">
                                                  <h2 class="marketing-digital-workers-card-title">${card.name}</h2>
                                                  <p class="marketing-digital-workers-card-desc">
                                                      ${typeof card.greeting_message === 'string' &&
                                                      card.greeting_message !== ''
                                                          ? card.greeting_message
                                                          : this.t('digital_workers.card_fallback_desc')}
                                                  </p>
                                                  <div class="marketing-digital-workers-card-actions">
                                                      <platform-button
                                                          variant="primary"
                                                          density="compact"
                                                          @click=${() => this._tryAgent(card)}
                                                      >
                                                          ${this.t('digital_workers.cta_try')}
                                                      </platform-button>
                                                      <platform-button
                                                          variant="secondary"
                                                          density="compact"
                                                          @click=${this._hire}
                                                      >
                                                          ${this.t('digital_workers.cta_hire')}
                                                      </platform-button>
                                                  </div>
                                              </div>
                                          </article>
                                      `,
                                  )}
                              </div>
                          `
                        : ''}
                </div>
                <landing-footer></landing-footer>
            </div>
            <platform-embed-chat-drawer
                flows-base-url=${this._flowsBaseUrl}
                flow-id=${this._drawerSpec ? this._drawerSpec.flow_id : ''}
                embed-id=${this._drawerSpec ? this._drawerSpec.embed_id : ''}
                branch-id=${this._drawerSpec ? this._drawerSpec.branch_id : ''}
                assistant-title=${this._drawerSpec ? this._drawerSpec.assistant_title : ''}
                theme=${this._drawerSpec ? this._drawerSpec.theme : 'dark'}
                locale=${this._drawerSpec ? this._drawerSpec.interface_locale : 'auto'}
                ?show-launcher=${false}
                ?use-credentials=${false}
                .open=${this._drawerOpen}
                voice-base-url=${this._voiceBaseUrl}
                company-id=${LandingDigitalWorkersPage.embedDemoCompanyId}
                ?voice-enabled=${this._drawerVoiceEnabled()}
                ?voice-default-on=${this._drawerVoiceDefaultOn()}
                .getAuthToken=${this._getDemoAuthHeaders}
                @humanitec-embed-drawer-open-changed=${this._onDrawerOpenChanged}
                @embed-toast=${this._onEmbedDrawerToast}
            ></platform-embed-chat-drawer>
        `;
    }
}

customElements.define('landing-digital-workers-page', LandingDigitalWorkersPage);
