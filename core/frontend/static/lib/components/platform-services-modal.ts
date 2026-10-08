/**
 * platform.services — модалка витрины продуктов (шторка выбора сервиса).
 */

import { html, css } from 'lit';
import type { CSSResultGroup, TemplateResult } from '../lit-shim.js';
import { PlatformModal } from './glass-modal.js';
import { registerModalKind } from '../utils/modal-registry.js';
import './platform-services-launcher.js';
import { buildServiceEntryUrl, isStandalonePwaMode } from '../utils/build-service-entry-url.js';

export class PlatformServicesModal extends PlatformModal {
    static modalKind = 'platform.services';
    static i18nNamespace = 'platform';

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        css`
            :host {
                --modal-width: min(480px, calc(100vw - 24px));
            }
            :host .modal.lg,
            :host .modal {
                max-width: var(--modal-width, min(480px, 100% - 2rem));
            }
            :host .fullscreen-btn {
                display: none !important;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this._onServiceLaunch = this._onServiceLaunch.bind(this);
    }

    _onServiceLaunch(e: CustomEvent<{ serviceId?: unknown }>): void {
        e.stopPropagation();
        const d = e.detail;
        if (!d || typeof d.serviceId !== 'string' || d.serviceId.length === 0) {
            throw new Error('platform-services-modal: service-launch without serviceId');
        }
        const url = buildServiceEntryUrl(d.serviceId);
        this.close();
        if (isStandalonePwaMode()) {
            window.location.href = url;
        } else {
            window.open(url, '_blank', 'noopener,noreferrer');
        }
    }

    override renderHeader(): unknown {
        return this.t('services_modal.title');
    }

    override renderBody(): TemplateResult {
        return html`
            <div class="platform-services-modal-body">
                <platform-services-launcher
                    layout="page"
                    navigate-mode="event-only"
                    @service-launch=${this._onServiceLaunch}
                ></platform-services-launcher>
            </div>
        `;
    }
}

customElements.define('platform-services-modal', PlatformServicesModal);
registerModalKind(PlatformServicesModal.modalKind, 'platform-services-modal');
