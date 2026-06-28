/**
 * Marketing / product landing section layouts — core Design System.
 * Только semantic tokens из tokens.css; без локальных brand hex.
 */
import { css } from 'lit';
import { glassStyles } from './glass.styles.js';

export const marketingPageHostStyles = css`
    :host {
        display: block;
        width: 100%;
        min-height: var(--app-vh, 100vh);
        background: var(--marketing-page-bg);
        color: var(--text-primary);
        --marketing-product-accent: var(--accent);
        --marketing-product-accent-subtle: var(--accent-subtle);
    }

    :host([product-accent='success']) {
        --marketing-product-accent: var(--success);
        --marketing-product-accent-subtle: var(--success-bg);
    }

    :host([product-accent='accent-secondary']) {
        --marketing-product-accent: var(--accent-secondary);
        --marketing-product-accent-subtle: var(--accent-secondary-subtle);
    }

    .marketing-page-container {
        width: 100%;
        overflow-x: hidden;
    }
`;

export const marketingHeroStyles = css`
    .marketing-hero {
        max-width: var(--marketing-content-max-width);
        margin: 0 auto;
        padding: var(--marketing-hero-padding-top) var(--marketing-section-padding-x)
            var(--space-12);
        text-align: center;
        background: var(--marketing-hero-bg);
    }

    .marketing-hero-badge {
        display: inline-block;
        padding: var(--space-2) var(--space-5);
        background: var(--marketing-product-accent-subtle);
        border: 1px solid var(--glass-border-medium);
        border-radius: var(--radius-full);
        font-size: var(--text-sm);
        font-weight: var(--font-medium);
        color: var(--marketing-product-accent);
        margin-bottom: var(--space-6);
    }

    .marketing-hero-title {
        font-size: var(--text-display-md);
        font-weight: var(--font-semibold);
        line-height: var(--leading-tight);
        letter-spacing: var(--tracking-tight);
        margin: 0 0 var(--space-6);
        background: var(--marketing-hero-title-gradient);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    .marketing-hero-shot {
        max-width: 62.5rem;
        margin: 0 auto var(--space-8);
        border-radius: var(--marketing-shot-radius);
        overflow: hidden;
        border: 1px solid var(--marketing-shot-border);
        box-shadow: var(--marketing-shot-shadow);
    }

    .marketing-hero-shot img {
        width: 100%;
        height: auto;
        display: block;
    }

    .marketing-hero-description {
        font-size: var(--text-lg);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        max-width: 43.75rem;
        margin: 0 auto var(--space-10);
    }

    .marketing-hero-cta {
        margin-top: var(--space-2);
    }

    @media (min-width: 768px) {
        .marketing-hero {
            padding-top: calc(var(--space-16) + var(--space-4));
            padding-bottom: var(--space-16);
        }
    }
`;

export const marketingFeatureGridStyles = css`
    .marketing-features {
        max-width: var(--marketing-content-max-width);
        margin: 0 auto;
        padding: var(--space-12) var(--marketing-section-padding-x);
    }

    .marketing-features-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: var(--space-6);
    }

    .marketing-feature-card {
        border-radius: var(--radius-xl);
        padding: var(--space-8);
    }

    .marketing-feature-card::before {
        content: '';
        display: block;
        width: 2.75rem;
        height: 0.25rem;
        border-radius: var(--radius-sm);
        margin-bottom: var(--space-5);
        background: var(--accent-gradient);
    }

    .marketing-feature-title {
        font-size: var(--text-xl);
        font-weight: var(--font-semibold);
        margin: 0 0 var(--space-3);
        color: var(--text-primary);
    }

    .marketing-feature-description {
        font-size: var(--text-base);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        margin: 0;
    }

    @media (min-width: 768px) {
        .marketing-features-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }

    @media (min-width: 1024px) {
        .marketing-features-grid {
            grid-template-columns: repeat(4, 1fr);
        }
    }
`;

export const marketingStepsStyles = css`
    .marketing-steps {
        padding: var(--marketing-section-padding-y) var(--marketing-section-padding-x);
        background: var(--glass-tint-subtle);
    }

    .marketing-steps-container {
        max-width: var(--marketing-content-max-width);
        margin: 0 auto;
    }

    .marketing-steps-title {
        font-size: var(--text-section-title);
        font-weight: var(--font-semibold);
        text-align: center;
        margin: 0 0 var(--space-12);
        color: var(--text-primary);
    }

    .marketing-steps-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: var(--space-8);
    }

    .marketing-step-item {
        display: flex;
        gap: var(--space-5);
        align-items: flex-start;
    }

    .marketing-step-number {
        flex-shrink: 0;
        width: 2.75rem;
        height: 2.75rem;
        border-radius: var(--radius-full);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: var(--text-lg);
        font-weight: var(--font-semibold);
        color: var(--text-primary);
        background: var(--marketing-product-accent-subtle);
        border: 1px solid var(--glass-border-medium);
    }

    .marketing-step-content h3 {
        font-size: var(--text-lg);
        font-weight: var(--font-semibold);
        margin: 0 0 var(--space-2);
        color: var(--text-primary);
    }

    .marketing-step-content p {
        font-size: var(--text-base);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        margin: 0;
    }

    @media (min-width: 768px) {
        .marketing-steps-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }

    @media (min-width: 1024px) {
        .marketing-steps-grid {
            grid-template-columns: repeat(4, 1fr);
        }
    }
`;

export const marketingUseCasesStyles = css`
    .marketing-use-cases {
        max-width: var(--marketing-content-max-width);
        margin: 0 auto;
        padding: var(--marketing-section-padding-y) var(--marketing-section-padding-x);
    }

    .marketing-use-cases-title {
        font-size: var(--text-section-title);
        font-weight: var(--font-semibold);
        text-align: center;
        margin: 0 0 var(--space-10);
        color: var(--text-primary);
    }

    .marketing-use-cases-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: var(--space-4);
    }

    .marketing-use-case-item {
        display: flex;
        align-items: center;
        gap: var(--space-4);
        padding: var(--space-5);
        border-radius: var(--radius-lg);
        border: 1px solid var(--glass-border-medium);
        background: var(--glass-bg-subtle);
    }

    .marketing-use-case-num {
        flex-shrink: 0;
        width: 2rem;
        height: 2rem;
        border-radius: var(--radius-full);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: var(--text-sm);
        font-weight: var(--font-semibold);
        color: var(--marketing-product-accent);
        background: var(--marketing-product-accent-subtle);
    }

    .marketing-use-case-text {
        font-size: var(--text-base);
        line-height: var(--leading-normal);
        color: var(--text-primary);
    }

    @media (min-width: 768px) {
        .marketing-use-cases-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }
`;

export const marketingGalleryStyles = css`
    .marketing-gallery {
        max-width: var(--marketing-content-max-width);
        margin: 0 auto;
        padding: 0 var(--marketing-section-padding-x) var(--space-12);
    }

    .marketing-gallery-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: var(--space-6);
    }

    @media (min-width: 768px) {
        .marketing-gallery-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }
`;

export const marketingBenefitsStyles = css`
    .marketing-benefits {
        background: var(--marketing-benefits-band-bg);
        border-top: 1px solid var(--marketing-benefits-band-border);
        border-bottom: 1px solid var(--marketing-benefits-band-border);
        padding: var(--marketing-section-padding-y) var(--marketing-section-padding-x);
    }

    .marketing-benefits-container {
        max-width: var(--marketing-content-max-width);
        margin: 0 auto;
    }

    .marketing-benefits-title {
        font-size: var(--text-section-title);
        font-weight: var(--font-semibold);
        text-align: center;
        margin: 0 0 var(--space-12);
        color: var(--text-primary);
    }

    .marketing-benefits-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: var(--space-8);
    }

    .marketing-benefit-item {
        display: flex;
        align-items: flex-start;
        gap: var(--space-5);
    }

    .marketing-benefit-marker {
        flex-shrink: 0;
        width: 0.25rem;
        min-height: 3.25rem;
        border-radius: var(--radius-sm);
        margin-top: var(--space-1);
        background: var(--accent-gradient);
    }

    .marketing-benefit-content h3 {
        font-size: var(--text-lg);
        font-weight: var(--font-semibold);
        margin: 0 0 var(--space-2);
        color: var(--text-primary);
    }

    .marketing-benefit-content p {
        font-size: var(--text-base);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        margin: 0;
    }

    @media (min-width: 768px) {
        .marketing-benefits-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }

    @media (min-width: 1024px) {
        .marketing-benefits-grid {
            grid-template-columns: repeat(3, 1fr);
        }
    }
`;

export const marketingFaqStyles = css`
    .marketing-faq {
        padding: var(--marketing-section-padding-y) var(--marketing-section-padding-x);
        max-width: var(--marketing-narrow-max-width);
        margin: 0 auto;
    }

    .marketing-faq-title {
        font-size: var(--text-section-title);
        font-weight: var(--font-semibold);
        text-align: center;
        margin: 0 0 var(--space-10);
        color: var(--text-primary);
    }

    .marketing-faq-list {
        display: flex;
        flex-direction: column;
        gap: var(--space-3);
    }

    details.marketing-faq-item {
        border: 1px solid var(--glass-border-medium);
        border-radius: var(--radius-lg);
        padding: 0 var(--space-5);
        background: var(--glass-bg-subtle);
    }

    details.marketing-faq-item summary {
        cursor: pointer;
        font-weight: var(--font-semibold);
        font-size: var(--text-base);
        padding: var(--space-4) 0;
        list-style: none;
        color: var(--text-primary);
    }

    details.marketing-faq-item summary::-webkit-details-marker {
        display: none;
    }

    .marketing-faq-answer {
        font-size: var(--text-base);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        padding: 0 0 var(--space-4);
        margin: 0;
    }
`;

export const marketingCtaStyles = css`
    .marketing-cta {
        max-width: var(--marketing-narrow-max-width);
        margin: 0 auto;
        padding: var(--marketing-section-padding-y) var(--marketing-section-padding-x);
        text-align: center;
    }

    .marketing-cta-title {
        font-size: var(--text-section-title);
        font-weight: var(--font-semibold);
        margin: 0 0 var(--space-4);
        color: var(--text-primary);
    }

    .marketing-cta-subtitle {
        font-size: var(--text-lg);
        color: var(--text-secondary);
        margin: 0 0 var(--space-8);
    }

    .marketing-back-link {
        display: inline-flex;
        align-items: center;
        gap: var(--space-2);
        padding: var(--space-3) var(--space-6);
        color: var(--text-secondary);
        text-decoration: none;
        font-size: var(--text-base);
        transition: var(--motion-transition-interactive);
        margin-top: var(--space-6);
    }

    .marketing-back-link:hover {
        color: var(--marketing-product-accent);
    }
`;

export const marketingDownloadStyles = css`
    .marketing-download {
        max-width: var(--marketing-narrow-max-width);
        margin: 0 auto;
        padding: 0 var(--marketing-section-padding-x) var(--marketing-section-padding-y);
        text-align: center;
    }

    .marketing-download-logo {
        width: 5rem;
        height: 5rem;
        margin: 0 auto var(--space-8);
        border-radius: var(--radius-xl);
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--accent-subtle);
        border: 1px solid var(--glass-border-medium);
        overflow: hidden;
    }

    .marketing-download-logo img {
        width: 3rem;
        height: 3rem;
        object-fit: contain;
    }

    .marketing-release-banner {
        margin: 0 auto var(--space-6);
        max-width: 45rem;
        padding: var(--space-3) var(--space-4);
        border-radius: var(--radius-md);
        font-size: var(--text-sm);
        text-align: center;
    }

    .marketing-release-banner[data-ready='true'] {
        background: var(--success-bg);
        border: 1px solid var(--success-border);
        color: var(--success);
    }

    .marketing-release-banner[data-ready='false'] {
        background: var(--error-bg);
        border: 1px solid var(--error-border);
        color: var(--error);
    }

    .marketing-download-actions {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: var(--space-3);
        margin-bottom: var(--space-6);
    }

    .marketing-download-link {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: var(--space-2);
        padding: var(--space-4) var(--space-8);
        border-radius: var(--btn-radius);
        font-size: var(--text-lg);
        font-weight: var(--font-medium);
        text-decoration: none;
        transition: var(--motion-transition-interactive);
        box-sizing: border-box;
    }

    a.marketing-download-link.marketing-download-link--primary,
    a.marketing-download-link.marketing-download-link--primary:hover,
    a.marketing-download-link.marketing-download-link--primary:visited,
    a.marketing-download-link.marketing-download-link--primary:active {
        color: var(--platform-btn-primary-text);
        -webkit-text-fill-color: currentColor;
        background: var(--platform-btn-primary-bg);
        box-shadow: var(--platform-btn-primary-shadow);
    }

    a.marketing-download-link.marketing-download-link--primary:hover {
        background: var(--platform-btn-primary-bg-hover);
        box-shadow: var(--platform-btn-primary-shadow-hover);
        transform: translateY(-1px);
    }

    a.marketing-download-link.marketing-download-link--secondary,
    a.marketing-download-link.marketing-download-link--secondary:hover,
    a.marketing-download-link.marketing-download-link--secondary:visited,
    a.marketing-download-link.marketing-download-link--secondary:active {
        color: var(--platform-btn-secondary-text);
        -webkit-text-fill-color: currentColor;
        background: var(--platform-btn-secondary-bg);
        border: 1px solid var(--glass-border-medium);
    }

    a.marketing-download-link.marketing-download-link--secondary:hover {
        background: var(--platform-btn-secondary-bg-hover);
    }

    .marketing-download-login {
        margin-top: var(--space-8);
        font-size: var(--text-base);
        color: var(--text-secondary);
    }

    .marketing-download-login a {
        color: var(--accent);
        text-decoration: none;
    }

    .marketing-download-login a:hover {
        text-decoration: underline;
    }

    .marketing-download-footer-note {
        margin-top: var(--space-6);
        font-size: var(--text-sm);
        color: var(--text-tertiary);
    }
`;

export const marketingAgentDownloadStyles = css`
    .marketing-download-hero-primary {
        max-width: 40rem;
        margin: 0 auto var(--space-4);
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: var(--space-4);
    }

    .marketing-download-hero-hint {
        margin: 0;
        font-size: var(--text-sm);
        color: var(--text-tertiary);
        line-height: var(--leading-relaxed);
    }

    .marketing-download-hero-cards {
        width: 100%;
        display: grid;
        grid-template-columns: 1fr;
        gap: var(--space-4);
    }

    @media (min-width: 640px) {
        .marketing-download-hero-cards {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    a.marketing-download-hero-button,
    a.marketing-download-hero-button:hover,
    a.marketing-download-hero-button:visited,
    a.marketing-download-hero-button:active {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: var(--space-3);
        min-width: min(100%, 20rem);
        padding: var(--space-5) var(--space-10);
        border-radius: var(--btn-radius);
        font-size: var(--text-xl);
        font-weight: var(--font-semibold);
        text-decoration: none;
        color: var(--platform-btn-primary-text);
        -webkit-text-fill-color: currentColor;
        background: var(--platform-btn-primary-bg);
        box-shadow: var(--platform-btn-primary-shadow);
        transition: var(--motion-transition-interactive);
    }

    a.marketing-download-hero-button:hover {
        background: var(--platform-btn-primary-bg-hover);
        box-shadow: var(--platform-btn-primary-shadow-hover);
        transform: translateY(-2px);
    }

    a.marketing-download-platform-card,
    a.marketing-download-platform-card:any-link {
        position: relative;
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: var(--space-3);
        padding: var(--space-6);
        border-radius: var(--radius-xl);
        text-decoration: none;
        color: var(--text-primary);
        transition: var(--motion-transition-interactive);
        box-sizing: border-box;
        min-height: 100%;
    }

    a.marketing-download-platform-card:hover {
        transform: translateY(-3px);
    }

    a.marketing-download-platform-card--hero {
        padding: var(--space-8);
        text-align: left;
    }

    a.marketing-download-platform-card--recommended {
        border-color: var(--accent);
        box-shadow: 0 0 0 1px var(--accent-subtle), var(--platform-btn-primary-shadow);
    }

    .marketing-download-platform-card-badge {
        position: absolute;
        top: var(--space-4);
        right: var(--space-4);
        padding: var(--space-1) var(--space-3);
        border-radius: var(--radius-full);
        font-size: var(--text-xs);
        font-weight: var(--font-semibold);
        color: var(--accent);
        background: var(--accent-subtle);
        border: 1px solid var(--glass-border-medium);
    }

    .marketing-download-platform-card-icon-wrap {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 4rem;
        height: 4rem;
        border-radius: var(--radius-lg);
        border: 1px solid var(--glass-border-subtle);
        background: var(--marketing-download-platform-icon-bg);
    }

    a.marketing-download-platform-card--hero .marketing-download-platform-card-icon-wrap {
        width: 4.5rem;
        height: 4.5rem;
    }

    .marketing-download-platform-card-icon-wrap--windows {
        --marketing-download-platform-icon-color: var(--marketing-download-icon-windows);
        --marketing-download-platform-icon-bg: var(--marketing-download-icon-windows-bg);
    }

    .marketing-download-platform-card-icon-wrap--apple {
        --marketing-download-platform-icon-color: var(--marketing-download-icon-apple);
        --marketing-download-platform-icon-bg: var(--marketing-download-icon-apple-bg);
    }

    .marketing-download-platform-card-icon-wrap--ubuntu {
        --marketing-download-platform-icon-color: var(--marketing-download-icon-ubuntu);
        --marketing-download-platform-icon-bg: var(--marketing-download-icon-ubuntu-bg);
    }

    .marketing-download-platform-card-icon-wrap--fedora {
        --marketing-download-platform-icon-color: var(--marketing-download-icon-fedora);
        --marketing-download-platform-icon-bg: var(--marketing-download-icon-fedora-bg);
    }

    .marketing-download-platform-card-icon-wrap--linux {
        --marketing-download-platform-icon-color: var(--marketing-download-icon-linux);
        --marketing-download-platform-icon-bg: var(--marketing-download-icon-linux-bg);
    }

    .marketing-download-platform-card-icon {
        display: block;
        width: 2rem;
        height: 2rem;
        background-color: var(--marketing-download-platform-icon-color);
        -webkit-mask-image: var(--marketing-download-platform-icon-mask);
        -webkit-mask-repeat: no-repeat;
        -webkit-mask-position: center;
        -webkit-mask-size: contain;
        mask-image: var(--marketing-download-platform-icon-mask);
        mask-repeat: no-repeat;
        mask-position: center;
        mask-size: contain;
    }

    a.marketing-download-platform-card--hero .marketing-download-platform-card-icon {
        width: 2.25rem;
        height: 2.25rem;
    }

    .marketing-download-hero-button-icon {
        display: block;
        width: 1.75rem;
        height: 1.75rem;
        background-color: var(--platform-btn-primary-text);
        -webkit-mask-image: var(--marketing-download-platform-icon-mask);
        -webkit-mask-repeat: no-repeat;
        -webkit-mask-position: center;
        -webkit-mask-size: contain;
        mask-image: var(--marketing-download-platform-icon-mask);
        mask-repeat: no-repeat;
        mask-position: center;
        mask-size: contain;
    }

    .marketing-download-platform-card-title {
        font-size: var(--text-lg);
        font-weight: var(--font-semibold);
        line-height: var(--leading-snug);
        color: var(--text-primary);
    }

    a.marketing-download-platform-card--hero .marketing-download-platform-card-title {
        font-size: var(--text-xl);
    }

    .marketing-download-platform-card-subtitle {
        font-size: var(--text-sm);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        flex: 1;
    }

    .marketing-download-platform-card-action {
        display: inline-flex;
        align-items: center;
        gap: var(--space-2);
        margin-top: var(--space-2);
        font-size: var(--text-sm);
        font-weight: var(--font-medium);
        color: var(--accent);
    }

    .marketing-download-scroll-trigger {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: var(--space-2);
        margin: var(--space-2) auto var(--space-10);
        padding: var(--space-3) var(--space-6);
        border: 1px solid var(--glass-border-medium);
        border-radius: var(--radius-full);
        background: var(--glass-bg-subtle);
        color: var(--text-secondary);
        font: inherit;
        font-size: var(--text-sm);
        font-weight: var(--font-medium);
        cursor: pointer;
        transition: var(--motion-transition-interactive);
    }

    .marketing-download-scroll-trigger:hover {
        color: var(--text-primary);
        border-color: var(--accent);
        background: var(--accent-subtle);
        transform: translateY(-1px);
    }

    .marketing-download-all-platforms {
        max-width: var(--marketing-content-max-width);
        margin: 0 auto;
        padding: var(--space-12) var(--marketing-section-padding-x);
        scroll-margin-top: calc(var(--space-16) + var(--space-4));
    }

    .marketing-download-all-platforms-title {
        margin: 0 0 var(--space-8);
        text-align: center;
        font-size: var(--text-section-title);
        font-weight: var(--font-semibold);
        color: var(--text-primary);
    }

    .marketing-download-all-platforms-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: var(--space-4);
    }

    @media (min-width: 640px) {
        .marketing-download-all-platforms-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }

    @media (min-width: 1024px) {
        .marketing-download-all-platforms-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
    }

    .marketing-download-postscript {
        max-width: var(--marketing-narrow-max-width);
        margin: 0 auto;
        padding: 0 var(--marketing-section-padding-x) var(--marketing-section-padding-y);
        text-align: center;
    }
`;

export const marketingContentStyles = css`
    .marketing-content {
        max-width: var(--marketing-narrow-max-width);
        margin: 0 auto;
        padding: var(--marketing-hero-padding-top) var(--marketing-section-padding-x)
            var(--marketing-section-padding-y);
        box-sizing: border-box;
    }

    .marketing-content-hero {
        text-align: center;
        margin-bottom: var(--space-10);
    }

    .marketing-content-title {
        font-size: var(--text-display-sm);
        font-weight: var(--font-semibold);
        line-height: var(--leading-tight);
        letter-spacing: var(--tracking-tight);
        margin: 0 0 var(--space-4);
        color: var(--text-primary);
    }

    .marketing-content-lede {
        font-size: var(--text-lg);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        margin: 0 auto;
        max-width: 36rem;
    }

    .marketing-content-stack {
        display: flex;
        flex-direction: column;
        gap: var(--space-6);
    }

    .marketing-content-panel {
        border-radius: var(--radius-xl);
        padding: var(--space-8);
    }

    .marketing-content-panel-compact {
        padding: var(--space-6) var(--space-8);
    }

    .marketing-content-section-label {
        font-size: var(--text-sm);
        font-weight: var(--font-semibold);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--text-tertiary);
        margin: 0 0 var(--space-4);
    }

    .marketing-contact-row {
        display: flex;
        align-items: flex-start;
        gap: var(--space-4);
    }

    .marketing-contact-icon {
        flex-shrink: 0;
        width: 2.5rem;
        height: 2.5rem;
        border-radius: var(--radius-md);
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--accent-subtle);
        border: 1px solid var(--glass-border-medium);
        color: var(--accent);
    }

    a.marketing-contact-link,
    a.marketing-contact-link:any-link {
        color: var(--accent);
        font-size: var(--text-lg);
        font-weight: var(--font-medium);
        word-break: break-all;
        text-decoration: none;
    }

    a.marketing-contact-link:hover {
        text-decoration: underline;
    }

    .marketing-form-stack {
        display: flex;
        flex-direction: column;
        gap: var(--space-5);
    }

    .marketing-form-actions {
        margin-top: var(--space-2);
    }

    .marketing-form-status {
        font-size: var(--text-sm);
        margin-top: var(--space-3);
        min-height: 1.25em;
    }

    .marketing-form-status.is-error {
        color: var(--error);
    }

    .marketing-form-status.is-ok {
        color: var(--success);
    }

    .marketing-form-note {
        font-size: var(--text-sm);
        color: var(--text-tertiary);
        margin-top: var(--space-4);
        line-height: var(--leading-relaxed);
    }

    .marketing-content-aside {
        margin-top: var(--space-10);
        padding-top: var(--space-6);
        border-top: 1px solid var(--glass-border-subtle);
        text-align: center;
    }

    a.marketing-content-aside-link,
    a.marketing-content-aside-link:any-link {
        color: var(--accent);
        display: inline-flex;
        align-items: center;
        gap: var(--space-2);
        font-size: var(--text-sm);
        text-decoration: none;
    }

    a.marketing-content-aside-link:hover {
        text-decoration: underline;
    }

    .marketing-prose h2 {
        font-size: var(--text-xl);
        font-weight: var(--font-semibold);
        margin: var(--space-8) 0 var(--space-3);
        color: var(--text-primary);
    }

    .marketing-prose h2:first-child {
        margin-top: 0;
    }

    .marketing-prose p {
        font-size: var(--text-base);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        margin: 0 0 var(--space-4);
    }

    .marketing-prose ul,
    .marketing-prose ol {
        padding-left: var(--space-5);
        margin: 0 0 var(--space-4);
    }

    .marketing-prose li {
        font-size: var(--text-base);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        margin-bottom: var(--space-2);
    }

    .marketing-prose .updated {
        color: var(--text-tertiary);
        font-size: var(--text-sm);
        margin-bottom: var(--space-8);
    }

    .marketing-content-card-list {
        list-style: none;
        padding: 0;
        margin: 0;
        display: flex;
        flex-direction: column;
        gap: var(--space-4);
    }

    .marketing-content-card {
        border-radius: var(--radius-xl);
        padding: var(--space-6) var(--space-8);
    }

    .marketing-content-card-title {
        font-size: var(--text-lg);
        font-weight: var(--font-semibold);
        margin: 0 0 var(--space-2);
        color: var(--text-primary);
    }

    .marketing-content-card-summary {
        font-size: var(--text-base);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        margin: 0 0 var(--space-4);
    }

    .marketing-text-link {
        background: transparent;
        border: none;
        color: var(--accent);
        font: inherit;
        font-size: var(--text-base);
        font-weight: var(--font-medium);
        cursor: pointer;
        padding: 0;
        text-decoration: underline;
    }

    .marketing-text-muted {
        color: var(--text-tertiary);
        font-size: var(--text-sm);
        line-height: var(--leading-relaxed);
    }

    .marketing-text-error {
        color: var(--error);
        font-size: var(--text-base);
    }

    .marketing-content-cta {
        margin-top: var(--space-10);
        padding-top: var(--space-8);
        border-top: 1px solid var(--glass-border-subtle);
    }
`;

export const marketingPublicContentPageStyles = [
    glassStyles,
    marketingPageHostStyles,
    marketingContentStyles,
];

export const marketingAgentDownloadPageStyles = [
    glassStyles,
    marketingPageHostStyles,
    marketingHeroStyles,
    marketingFeatureGridStyles,
    marketingDownloadStyles,
    marketingAgentDownloadStyles,
];

export const marketingProductPageStyles = [
    glassStyles,
    marketingPageHostStyles,
    marketingHeroStyles,
    marketingFeatureGridStyles,
    marketingStepsStyles,
    marketingUseCasesStyles,
    marketingGalleryStyles,
    marketingBenefitsStyles,
    marketingFaqStyles,
    marketingCtaStyles,
    marketingDownloadStyles,
];
