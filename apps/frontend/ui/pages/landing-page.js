/**
 * Landing Page - Главная страница лендинга Humanitec
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/auth-modal.js';

export class LandingPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                background: var(--landing-bg, #0F0F0F);
                color: var(--landing-text, #FFFFFF);
            }
            
            .landing-container {
                width: 100%;
                overflow-x: hidden;
            }
            
            section {
                position: relative;
            }
        `
    ];

    static properties = {
        currentSection: { type: String }
    };

    constructor() {
        super();
        this.currentSection = 'hero';
    }

    connectedCallback() {
        super.connectedCallback();
        this._setupSmoothScroll();
        this.addEventListener('open-auth-modal', this._handleOpenAuthModal);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._removeSmoothScroll();
        this.removeEventListener('open-auth-modal', this._handleOpenAuthModal);
    }

    _setupSmoothScroll() {
        setTimeout(() => {
            const links = this.shadowRoot?.querySelectorAll('a[href^="#"]');
            links?.forEach(anchor => {
                anchor.addEventListener('click', this._handleSmoothScroll);
            });
        }, 100);
    }

    _removeSmoothScroll() {
        const links = this.shadowRoot?.querySelectorAll('a[href^="#"]');
        links?.forEach(anchor => {
            anchor.removeEventListener('click', this._handleSmoothScroll);
        });
    }

    _handleSmoothScroll = (e) => {
        e.preventDefault();
        const targetId = e.currentTarget.getAttribute('href').slice(1);
        const targetElement = this.shadowRoot?.getElementById(targetId);
        
        if (targetElement) {
            targetElement.scrollIntoView({ 
                behavior: 'smooth',
                block: 'start'
            });
        }
    };

    _handleOpenAuthModal = () => {
        console.log('🟢 Open auth modal event received');
        const authModal = this.shadowRoot?.querySelector('auth-modal');
        if (authModal) {
            console.log('✅ Auth modal found, opening...');
            authModal.open = true;
        } else {
            console.error('❌ Auth modal not found');
        }
    };

    render() {
        return html`
            <div class="landing-container">
                <landing-header></landing-header>
                
                <section id="hero">
                    <landing-hero></landing-hero>
                </section>
                
                <section id="about">
                    <landing-about></landing-about>
                </section>
                
                <section id="abilities">
                    <landing-abilities></landing-abilities>
                </section>
                
                <section id="advantages">
                    <landing-advantages></landing-advantages>
                </section>
                
                <section id="plans">
                    <landing-plans></landing-plans>
                </section>
                
                <section id="reviews">
                    <landing-reviews></landing-reviews>
                </section>
                
                <section id="faq">
                    <landing-faq></landing-faq>
                </section>
                
                <section id="cta">
                    <landing-cta></landing-cta>
                </section>
                
                <landing-footer></landing-footer>
            </div>
            
            <auth-modal></auth-modal>
        `;
    }
}

customElements.define('landing-page', LandingPage);

