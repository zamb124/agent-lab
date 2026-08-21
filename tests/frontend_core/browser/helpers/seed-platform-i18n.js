/**
 * Shared i18n seed for platform-markdown-editor browser tests.
 * Bootstrap async-loads /api/i18n; wait for it, then pin en + platform nest.
 */

import { waitUntil } from '../helpers/render.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { translate } from '@platform/lib/events/effects/i18n.effect.js';
import platformEn from '../../../../core/i18n/translations/en/platform.json' with { type: 'json' };

/**
 * Wait for bootstrap i18n to settle, then install/pin platform bundle (en).
 * Call after bootstrapTestBus().
 */
export async function seedPlatformMarkdownEditorI18n() {
    const bus = getPlatformBus();
    await waitUntil(
        () => {
            const i18n = bus.getState().i18n;
            if (i18n.loading) {
                return false;
            }
            const bundle = i18n.translations[i18n.locale];
            if (!bundle || typeof bundle !== 'object') {
                return false;
            }
            return Boolean(bundle.markdown_editor || (bundle.platform && bundle.platform.markdown_editor));
        },
        'platform i18n ready',
        { timeout: 15_000 },
    );

    for (const locale of ['en', 'ru']) {
        const prev = bus.getState().i18n.translations[locale] || {};
        bus.dispatch(
            CoreEvents.I18N_LOCALE_LOADED,
            {
                locale,
                bundle: {
                    ...prev,
                    ...platformEn,
                    platform: platformEn,
                },
            },
            { source: 'system' },
        );
    }
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'platform' },
        { source: 'system' },
    );

    const resolved = translate(bus.getState().i18n, 'markdown_editor.empty_preview', null, 'platform');
    if (resolved !== platformEn.markdown_editor.empty_preview) {
        throw new Error(
            `seedPlatformMarkdownEditorI18n failed: got "${resolved}", locale=${bus.getState().i18n.locale}`,
        );
    }
}

export { platformEn };
