/**
 * Language picker toolbar row — segmented control wrapper для code workbench/docs/library.
 */
import { css } from 'lit';

export const codeLanguageToolbarStyles = css`
    .code-language-toolbar {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        flex-wrap: wrap;
        min-height: var(--flows-chrome-control-size);
    }

    .code-language-toolbar platform-segmented-control {
        flex: 0 1 auto;
        min-width: 0;
    }
`;
