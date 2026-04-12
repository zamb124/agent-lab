import { expect } from '@open-wc/testing';
import { hrefForDeepLinkNavigation } from '@platform/lib/utils/platform-deeplink-paths.js';

describe('hrefForDeepLinkNavigation', () => {
    it('тот же origin — pathname + search + hash', () => {
        const opened = new URL('https://humanitec.ru/join?x=1#frag');
        const href = hrefForDeepLinkNavigation(opened, 'https://humanitec.ru');
        expect(href).to.equal('/join?x=1#frag');
    });

    it('другой origin — полный href', () => {
        const opened = new URL('https://tenant.humanitec.ru/crm/');
        const href = hrefForDeepLinkNavigation(opened, 'https://humanitec.ru');
        expect(href).to.equal('https://tenant.humanitec.ru/crm/');
    });
});
