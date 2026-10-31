import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import {
    getPlatformI18nVars,
    mergePlatformI18nVars,
} from '../../../../core/frontend/static/lib/utils/platform-i18n-vars.js';
import {
    setPlatformBrandBootstrap,
} from '../../../../core/frontend/static/lib/utils/platform-brand.js';
import { translate } from '../../../../core/frontend/static/lib/events/effects/i18n.effect.js';

const BRAND = {
    isProduction: true,
    baseDomain: 'linnex.io',
    portSuffix: '',
    protocol: 'https',
    platformName: 'Linnex',
    supportEmail: 'support@linnex.io',
    logoPath: '/static/core/assets/service_logos/frontend_logo.svg',
    apexOrigin: 'https://linnex.io/',
    supportedDomains: ['linnex.io', 'linnex.io'],
    modelsProductName: 'Linnex Models',
    voiceProductName: 'Linnex Voice',
    llmsDisplayLabel: 'Linnex LLMs',
    flowsProductLabel: 'Linnex Flows',
};

describe('platform-i18n-vars', () => {
    beforeEach(() => {
        setPlatformBrandBootstrap(BRAND);
    });

    afterEach(() => {
        if (typeof window !== 'undefined') {
            delete window.__PLATFORM_BRAND__;
        }
    });

    it('getPlatformI18nVars returns brand product labels', () => {
        expect(getPlatformI18nVars()).toEqual({
            platformName: 'Linnex',
            supportEmail: 'support@linnex.io',
            modelsProductName: 'Linnex Models',
            voiceProductName: 'Linnex Voice',
            llmsDisplayLabel: 'Linnex LLMs',
            flowsProductLabel: 'Linnex Flows',
        });
    });

    it('mergePlatformI18nVars merges caller vars over brand defaults', () => {
        expect(mergePlatformI18nVars({ year: 2026 })).toEqual({
            platformName: 'Linnex',
            supportEmail: 'support@linnex.io',
            modelsProductName: 'Linnex Models',
            voiceProductName: 'Linnex Voice',
            llmsDisplayLabel: 'Linnex LLMs',
            flowsProductLabel: 'Linnex Flows',
            year: 2026,
        });
    });

    it('translate interpolates platformName from merged vars', () => {
        const i18nState = {
            locale: 'en',
            defaultNamespace: 'frontend',
            translations: {
                en: {
                    frontend: {
                        console: {
                            welcome_subtitle: 'Manage {platformName} services from one place',
                        },
                    },
                },
            },
        };
        const text = translate(
            i18nState,
            'console.welcome_subtitle',
            mergePlatformI18nVars(undefined),
            'frontend',
        );
        expect(text).toBe('Manage Linnex services from one place');
    });
});
