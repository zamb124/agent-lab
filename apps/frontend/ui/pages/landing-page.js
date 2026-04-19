/**
 * Landing Page — главная страница.
 *
 * Подписана на `frontend/ui/plan_selected` для скролла к CTA-секции.
 * Auth-модалка живёт глобально в platform-modal-stack — открывается через
 * dispatch CoreEvents.UI_MODAL_OPEN { kind: 'auth.login' } из landing-header,
 * landing-hero, landing-plans.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { FrontendLeadFormModal } from '../modals/lead-form-modal.js';
import '@platform/lib/components/auth-modal.js';

const PLAN_SELECTED_EVENT = 'frontend/ui/plan_selected';

export class LandingPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; width: 100%; background: var(--landing-bg, #0F0F0F); color: var(--landing-text, #FFFFFF); }
            section { position: relative; scroll-margin-top: 88px; }
        `,
    ];

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(PLAN_SELECTED_EVENT, (event) => {
            const plan = event.payload && event.payload.plan;
            if (plan !== 'expert') return;
            this.openModal(FrontendLeadFormModal);
            const section = this.shadowRoot?.getElementById('cta');
            if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }

    render() {
        return html`
            <div class="landing-container">
                <landing-header></landing-header>
                <section id="hero"><landing-hero></landing-hero></section>
                <section id="about"><landing-about></landing-about></section>
                <section id="abilities"><landing-abilities></landing-abilities></section>
                <section id="advantages"><landing-advantages></landing-advantages></section>
                <section id="plans"><landing-plans></landing-plans></section>
                <section id="reviews"><landing-reviews></landing-reviews></section>
                <section id="faq"><landing-faq></landing-faq></section>
                <section id="cta"><landing-cta></landing-cta></section>
                <landing-footer></landing-footer>
            </div>
        `;
    }
}

customElements.define('landing-page', LandingPage);
