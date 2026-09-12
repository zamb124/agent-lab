/**
 * Палитра Источников: официальные иконки по catalog.icon.
 */

import { fixture, fixtureCleanup, html, expect, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { installFetchMock } from '../helpers/fake-fetch.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import { nodeTypesOp, resourceTypesOp } from '../../../../apps/flows/ui/events/resources/metadata.resource.js';
import { triggerRemoveOp, triggersListOp } from '../../../../apps/flows/ui/events/resources/triggers.resource.js';
import '../../../../apps/flows/ui/components/editor/flows-node-types-sidebar.js';

describe('flows-node-types-sidebar datasource brand icons', () => {
    let fetchMock;

    beforeEach(() => {
        resetPlatformState();
        const bus = bootstrapTestBus({
            factories: [nodeTypesOp, resourceTypesOp, triggersListOp, triggerRemoveOp],
        });
        const locale = bus.getState().i18n.locale;
        const previous = bus.getState().i18n.translations[locale] || {};
        bus.dispatch(
            CoreEvents.I18N_LOCALE_LOADED,
            { locale, bundle: { ...previous, flows: flowsEn } },
            { source: 'system' },
        );
        fetchMock = installFetchMock();
        fetchMock.respondJson('GET', (url) => url.includes('/flows/api/v1/metadata/node-types'), [
            {
                category: 'sources',
                type: 'datasource',
                connector_id: 'postgres',
                name: 'PostgreSQL',
                icon: 'postgres',
                description: 'SQL query/schema',
                color: '#14b8a6',
                inputs: 1,
                outputs: 1,
            },
            {
                category: 'sources',
                type: 'datasource',
                connector_id: 'mysql',
                name: 'MySQL',
                icon: 'mysql',
                description: 'SQL query/schema',
                color: '#14b8a6',
                inputs: 1,
                outputs: 1,
            },
            {
                category: 'sources',
                type: 'datasource',
                connector_id: 'clickhouse',
                name: 'ClickHouse',
                icon: 'clickhouse',
                description: 'SQL query/schema',
                color: '#14b8a6',
                inputs: 1,
                outputs: 1,
            },
        ]);
        fetchMock.respondJson('GET', (url) => url.includes('/flows/api/v1/metadata/resource-types'), []);
    });

    afterEach(() => {
        fetchMock.uninstall();
        fixtureCleanup();
    });

    it('карточка PostgreSQL — platform-icon postgres colored', async () => {
        const el = await fixture(html`<flows-node-types-sidebar></flows-node-types-sidebar>`);
        await waitUntil(
            () => el.shadowRoot.querySelector('.node-item[aria-label="PostgreSQL"]') !== null,
            'postgres palette card',
        );
        const icon = el.shadowRoot.querySelector('.node-item[aria-label="PostgreSQL"] platform-icon');
        expect(icon, 'postgres icon').to.exist;
        expect(icon.getAttribute('name')).to.equal('postgres');
        expect(icon.hasAttribute('colored')).to.equal(true);
        const mysqlIcon = el.shadowRoot.querySelector('.node-item[aria-label="MySQL"] platform-icon');
        expect(mysqlIcon.getAttribute('name')).to.equal('mysql');
        expect(mysqlIcon.hasAttribute('colored')).to.equal(true);
        const clickhouseIcon = el.shadowRoot.querySelector('.node-item[aria-label="ClickHouse"] platform-icon');
        expect(clickhouseIcon.getAttribute('name')).to.equal('clickhouse');
        expect(clickhouseIcon.hasAttribute('colored')).to.equal(true);
    });
});
