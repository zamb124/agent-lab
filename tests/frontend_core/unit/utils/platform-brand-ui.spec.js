import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import {
    setPlatformBrandBootstrap,
} from '../../../../core/frontend/static/lib/utils/platform-brand.js';
import { getPlatformI18nVars } from '../../../../core/frontend/static/lib/utils/platform-i18n-vars.js';
import { translate } from '../../../../core/frontend/static/lib/events/effects/i18n.effect.js';
import { mergePlatformI18nVars } from '../../../../core/frontend/static/lib/utils/platform-i18n-vars.js';

const LINNEX_BRAND = {
    isProduction: true,
    baseDomain: 'linnex.io',
    portSuffix: '',
    protocol: 'https',
    platformName: 'Linnex',
    supportEmail: 'support@linnex.io',
    logoPath: '/static/core/assets/service_logos/frontend_logo.svg',
    apexOrigin: 'https://linnex.io/',
    supportedDomains: ['linnex.io', 'humanitec.ru'],
    agentProductName: 'LinnexAgent',
    modelsProductName: 'Linnex Models',
    voiceProductName: 'Linnex Voice',
    llmsDisplayLabel: 'Linnex LLMs',
    flowsProductLabel: 'Linnex Flows',
};

describe('platform brand UI vars (linnex.io)', () => {
    beforeEach(() => {
        setPlatformBrandBootstrap(LINNEX_BRAND);
    });

    afterEach(() => {
        if (typeof window !== 'undefined') {
            delete window.__PLATFORM_BRAND__;
        }
    });

    it('exposes linnex support email and wordmark source', () => {
        const vars = getPlatformI18nVars();
        expect(vars.platformName).toBe('Linnex');
        expect(vars.supportEmail).toBe('support@linnex.io');
        expect(vars.platformName.toUpperCase()).toBe('LINNEX');
        expect(vars.modelsProductName).toBe('Linnex Models');
    });

    it('litserve sidebar title resolves to Linnex Models', () => {
        const i18nState = {
            locale: 'en',
            defaultNamespace: 'litserve',
            translations: {
                en: {
                    litserve: {
                        sidebar: { title: '{modelsProductName}' },
                        models: {
                            subtitle: '{platformName} system models for embeddings and rerank',
                        },
                    },
                },
            },
        };
        const vars = mergePlatformI18nVars(undefined);
        expect(
            translate(i18nState, 'sidebar.title', vars, 'litserve'),
        ).toBe('Linnex Models');
        expect(
            translate(i18nState, 'models.subtitle', vars, 'litserve'),
        ).toBe('Linnex system models for embeddings and rerank');
    });

    it('does not leak Humanitec in platform service labels', () => {
        const i18nState = {
            locale: 'en',
            defaultNamespace: 'platform',
            translations: {
                en: {
                    platform: {
                        apps: {
                            litserve: { name: '{modelsProductName}' },
                        },
                    },
                },
            },
        };
        const label = translate(
            i18nState,
            'apps.litserve.name',
            mergePlatformI18nVars(undefined),
            'platform',
        );
        expect(label).toBe('Linnex Models');
        expect(label.includes('Humanitec')).toBe(false);
    });
});
