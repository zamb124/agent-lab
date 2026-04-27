import { css } from 'lit';

/**
 * Блок под `<page-header>` при `platform-island padding="none"` на мобилке.
 * Настольная вёрстка: `display: contents` — дети ведут себя как раньше.
 */
export const frontendIslandPageBodyStyles = css`
    @media (max-width: 767px) {
        :host {
            display: flex;
            flex-direction: column;
            min-height: 0;
            flex: 1;
        }
    }

    .page-body {
        display: contents;
    }
    @media (max-width: 767px) {
        .page-body {
            display: block;
            box-sizing: border-box;
            flex: 1;
            min-height: 0;
            padding: var(--space-2);
            padding-top: 0;
            padding-left: max(var(--space-2), env(safe-area-inset-left, 0px));
            padding-right: max(var(--space-2), env(safe-area-inset-right, 0px));
            padding-bottom: var(--space-2);
        }
    }
`;
