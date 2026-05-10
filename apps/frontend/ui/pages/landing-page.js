/**
 * Landing Page — главная страница.
 *
 * Auth-модалка живёт глобально в platform-modal-stack — открывается через
 * helper openModal из landing-header, landing-hero, landing-plans.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/auth-modal.js';

import { takePendingLandingSectionTarget } from '../components/landing/landing-section-scroll.js';

export class LandingPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                width: 100%;
                max-width: 100%;
                box-sizing: border-box;
                background: var(--landing-bg, #0F0F0F);
                color: var(--landing-text, #FFFFFF);
            }
            .landing-container {
                max-width: 100%;
                overflow-x: clip;
                box-sizing: border-box;
            }
            section { position: relative; scroll-margin-top: 88px; }
        `,
    ];

    firstUpdated(changedProps) {
        super.firstUpdated(changedProps);
        requestAnimationFrame(() => {
            requestAnimationFrame(() => this._consumePendingLandingScroll());
        });
    }

    _consumePendingLandingScroll() {
        const sectionId = takePendingLandingSectionTarget();
        if (sectionId === null) {
            return;
        }
        const root = this.shadowRoot;
        if (!root) {
            return;
        }
        const target = root.getElementById(sectionId);
        if (!target) {
            return;
        }
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    render() {
        return html`
            <div class="landing-container">
                <landing-header></landing-header>
                <section id="hero"><landing-hero></landing-hero></section>
                <section id="trust"><landing-trust></landing-trust></section>
                <section id="demo-agents"><landing-home-demo-agents></landing-home-demo-agents></section>
                <section id="about"><landing-about></landing-about></section>
                <section id="abilities"><landing-abilities></landing-abilities></section>
                <section id="advantages"><landing-advantages></landing-advantages></section>
                <section id="roi"><landing-roi-calculator></landing-roi-calculator></section>
                <section id="plans"><landing-plans></landing-plans></section>
                <section id="cases"><landing-cases></landing-cases></section>
                <section id="reviews"><landing-reviews></landing-reviews></section>
                <section id="faq"><landing-faq></landing-faq></section>
                <section id="cta"><landing-cta></landing-cta></section>
                <landing-footer></landing-footer>
                <landing-floating-cta></landing-floating-cta>
            </div>
        `;
    }
}

customElements.define('landing-page', LandingPage);
