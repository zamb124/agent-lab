/**
 * Общие стили липкой мобильной полосы хедера (токены --platform-mobile-sticky-header-*).
 * page-header: .header-wrap + .header; sync-chat-header: :host.
 */
import { css } from 'lit';

export const mobileStickyHeaderPageHeaderShellStyles = css`
    @media (max-width: 767px) {
        .header-wrap {
            position: sticky;
            top: 0;
            z-index: var(--platform-mobile-sticky-header-z-index);
            margin: 0 0 var(--space-2);
            padding: var(--platform-mobile-sticky-header-padding-top)
                var(--platform-mobile-sticky-header-padding-right)
                var(--platform-mobile-sticky-header-padding-bottom)
                var(--platform-mobile-sticky-header-padding-left);
            background: var(--glass-solid-strong);
            backdrop-filter: blur(var(--glass-blur-medium));
            -webkit-backdrop-filter: blur(var(--glass-blur-medium));
            border-bottom: 1px solid var(--glass-border-subtle);
            box-sizing: border-box;
        }

        .header {
            align-items: center;
            flex-wrap: nowrap;
            min-height: var(--platform-mobile-sticky-header-row-min-height);
            gap: var(--space-1);
        }

        .header-left {
            align-items: center;
            min-width: 0;
        }
    }
`;

/**
 * mobile: :host (sync-chat-header) — те же отступы и липкость, что у page-header .header-wrap.
 */
export const mobileStickyHeaderSyncChatHostStyles = css`
    @media (max-width: 767px) {
        :host {
            min-height: calc(
                var(--platform-mobile-sticky-header-padding-top)
                + var(--platform-mobile-sticky-header-row-min-height)
                + var(--platform-mobile-sticky-header-padding-bottom)
            );
            padding: var(--platform-mobile-sticky-header-padding-top)
                var(--platform-mobile-sticky-header-padding-right)
                var(--platform-mobile-sticky-header-padding-bottom)
                var(--platform-mobile-sticky-header-padding-left);
            position: sticky;
            top: 0;
            z-index: var(--platform-mobile-sticky-header-z-index);
            align-items: center;
            gap: var(--space-1);
            background: var(--glass-solid-strong);
            backdrop-filter: blur(var(--glass-blur-medium));
            -webkit-backdrop-filter: blur(var(--glass-blur-medium));
            border-bottom: 1px solid var(--glass-border-subtle);
            box-sizing: border-box;
        }

        :host .text {
            justify-content: center;
            min-height: 0;
        }

        :host .title {
            font-size: var(--text-base);
        }

        :host .subtitle {
            font-size: var(--text-xs);
            line-height: 1.2;
        }
    }
`;
