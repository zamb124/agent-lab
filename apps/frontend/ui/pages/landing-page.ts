/**
 * Страница лендинга — главная страница.
 *
 * Космический слой: <cosmic-scope> монтирует WebGL-сцену, рельсу и
 * CosmicScrollController; секции размечены data-cosmic-chapter/hue/label —
 * сцена и рельса читают их через контроллер. Auth-модалка живёт глобально в
 * platform-modal-stack — открывается через helper openModal из
 * landing-header, landing-hero, landing-plans.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/auth-modal.js';
import { takePendingLandingSectionTarget } from '../components/landing/landing-section-scroll.js';
import { CosmicScope } from '../components/cosmic/cosmic-scope.js';
import { cosmicPinStyles } from '@platform/lib/styles/shared/cosmic-marketing.styles.js';
import '../components/cosmic/scramble-text.js';
import type { CSSResultGroup, PropertyValues, TemplateResult } from 'lit';

export class LandingPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        cosmicPinStyles,
        css`
            :host {
                display: block;
                width: 100%;
                max-width: 100%;
                box-sizing: border-box;
                background: var(--marketing-cosmic-bg);
                color: var(--marketing-cosmic-text);
            }
            .landing-container {
                max-width: 100%;
                overflow-x: clip;
                box-sizing: border-box;
            }
            section { position: relative; scroll-margin-top: 88px; }
        `,
    ];

    override firstUpdated(changedProps: PropertyValues<this>): void {
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
        const scope = root.querySelector('cosmic-scope');
        if (scope instanceof CosmicScope) {
            scope.scrollToSection(target);
            return;
        }
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    override render(): TemplateResult {
        return html`
            <cosmic-scope class="landing-container">
                <landing-header></landing-header>
                <section id="hero" data-cosmic-chapter data-cosmic-hue="196" data-cosmic-label=${this.t('cosmic.label_hero')}><landing-hero></landing-hero></section>
                <section id="trust" data-cosmic-chapter data-cosmic-hue="208" data-cosmic-label=${this.t('cosmic.label_trust')}><landing-trust></landing-trust></section>
                <section id="demo-agents" data-cosmic-chapter data-cosmic-hue="222" data-cosmic-label=${this.t('cosmic.label_agents')}><landing-home-demo-agents></landing-home-demo-agents></section>
                <section id="about" data-cosmic-chapter data-cosmic-hue="235" data-cosmic-label=${this.t('cosmic.label_about')}><landing-about></landing-about></section>
                <section id="abilities" data-cosmic-chapter data-cosmic-pin="2" data-cosmic-hue="252" data-cosmic-label=${this.t('cosmic.label_abilities')}><landing-abilities></landing-abilities></section>
                <section id="advantages" data-cosmic-chapter data-cosmic-hue="216" data-cosmic-label=${this.t('cosmic.label_advantages')}><landing-advantages></landing-advantages></section>
                <section id="roi" data-cosmic-chapter data-cosmic-hue="190" data-cosmic-label=${this.t('cosmic.label_roi')}><landing-roi-calculator></landing-roi-calculator></section>
                <section id="plans" data-cosmic-chapter data-cosmic-hue="242" data-cosmic-label=${this.t('cosmic.label_plans')}><landing-plans></landing-plans></section>
                <section id="cases" data-cosmic-chapter data-cosmic-pin="2" data-cosmic-hue="266" data-cosmic-label=${this.t('cosmic.label_cases')}><landing-cases></landing-cases></section>
                <section id="reviews" data-cosmic-chapter data-cosmic-hue="205" data-cosmic-label=${this.t('cosmic.label_reviews')}><landing-reviews></landing-reviews></section>
                <section id="faq" data-cosmic-chapter data-cosmic-hue="198" data-cosmic-label=${this.t('cosmic.label_faq')}><landing-faq></landing-faq></section>
                <section id="cta" data-cosmic-chapter data-cosmic-hue="186" data-cosmic-label=${this.t('cosmic.label_cta')}><landing-cta></landing-cta></section>
                <landing-footer></landing-footer>
                <landing-floating-cta></landing-floating-cta>
            </cosmic-scope>
        `;
    }
}

customElements.define('landing-page', LandingPage);
