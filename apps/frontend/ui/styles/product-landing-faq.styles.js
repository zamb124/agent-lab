/**
 * Общие стили секции FAQ на продуктовых посадочных страницах.
 */
import { css } from 'lit';

export const productLandingFaqStyles = css`
    .faq-section {
        padding: 80px 20px;
        max-width: 900px;
        margin: 0 auto;
    }

    .faq-title {
        font-family: 'Fira Sans Condensed', sans-serif;
        font-size: clamp(28px, 4vw, 40px);
        font-weight: 600;
        text-align: center;
        margin: 0 0 40px;
        color: var(--landing-secondary, #e8e8e8);
    }

    .faq-list {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    details.faq-item {
        border: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.12));
        border-radius: 16px;
        padding: 0 20px;
        background: var(--landing-panel-bg, rgba(255, 255, 255, 0.03));
    }

    details.faq-item summary {
        cursor: pointer;
        font-family: 'Fira Sans', sans-serif;
        font-weight: 600;
        font-size: 16px;
        padding: 18px 0;
        list-style: none;
        color: var(--landing-secondary, #e8e8e8);
    }

    details.faq-item summary::-webkit-details-marker {
        display: none;
    }

    .faq-answer {
        font-family: 'Fira Sans', sans-serif;
        font-size: 15px;
        line-height: 1.65;
        color: var(--landing-text-soft, rgba(232, 232, 232, 0.78));
        padding: 0 0 18px;
        margin: 0;
    }
`;
