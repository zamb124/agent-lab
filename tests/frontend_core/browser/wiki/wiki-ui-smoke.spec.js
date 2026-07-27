/**
 * Wiki UI — регистрация компонентов и базовые контракты фабрик.
 */

import { expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/index.js';

import { WikiApp } from '../../../../apps/wiki/ui/app/wiki-app.js';
import '../../../../apps/wiki/ui/components/wiki-sidebar.js';
import '../../../../apps/wiki/ui/pages/wiki-home-page.js';
import '../../../../apps/wiki/ui/pages/wiki-page-view.js';
import '../../../../apps/wiki/ui/pages/wiki-search-page.js';
import '../../../../apps/wiki/ui/pages/wiki-history-page.js';
import '../../../../apps/wiki/ui/pages/wiki-public-preview-page.js';
import '../../../../apps/wiki/ui/components/sheets/wiki-outline-sheet.js';
import '../../../../apps/wiki/ui/components/sheets/wiki-tree-sheet.js';
import '../../../../apps/wiki/ui/modals/wiki-move-page-modal.js';
import '../../../../apps/wiki/ui/modals/wiki-page-access-modal.js';
import { buildLineDiff } from '../../../../apps/wiki/ui/pages/wiki-history-page.js';

describe('wiki ui', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('регистрирует все элементы сервиса', () => {
        const tags = [
            'wiki-app',
            'wiki-sidebar',
            'wiki-home-page',
            'wiki-page-view',
            'wiki-search-page',
            'wiki-history-page',
            'wiki-public-preview-page',
            'wiki-move-page-modal',
            'wiki-page-access-modal',
            'wiki-outline-sheet',
            'wiki-tree-sheet',
        ];
        for (const tag of tags) {
            expect(customElements.get(tag), tag).to.exist;
        }
    });

    it('объявляет i18n namespace и ассистента сервиса', () => {
        expect(WikiApp.defaultI18nNamespace).to.equal('wiki');
        expect(WikiApp.platformAssistant.serviceId).to.equal('wiki');
        expect(WikiApp.platformAssistant.branchId).to.equal('wiki');
    });

    it('нижняя навигация ссылается на существующие маршруты', () => {
        const routeKeys = new Set(['wiki_home', 'wiki_page', 'wiki_page_history', 'wiki_search', 'wiki_public_preview']);
        for (const item of WikiApp.bottomNavItems) {
            if (typeof item.routeKey === 'string') {
                expect(routeKeys.has(item.routeKey), item.routeKey).to.be.true;
            }
            expect(typeof item.labelKey).to.equal('string');
        }
    });

    it('все фабрики сервиса собираются без конфликтов имён', () => {
        const collected = collectFactories(WikiApp.factories);
        expect(Object.keys(collected.slices).length).to.be.greaterThan(0);
    });

    it('каждая фабрика имеет уникальное имя', () => {
        const names = WikiApp.factories.map((factory) => factory.name);
        expect(new Set(names).size).to.equal(names.length);
    });
});

describe('buildLineDiff', () => {
    it('одинаковый текст не даёт изменений', () => {
        const rows = buildLineDiff('первая\nвторая', 'первая\nвторая');
        expect(rows.every((row) => row.kind === 'same')).to.be.true;
    });

    it('отмечает добавленные строки', () => {
        const rows = buildLineDiff('первая', 'первая\nвторая');
        const added = rows.filter((row) => row.kind === 'added');
        expect(added.map((row) => row.text)).to.deep.equal(['вторая']);
    });

    it('отмечает удалённые строки', () => {
        const rows = buildLineDiff('первая\nвторая', 'первая');
        const removed = rows.filter((row) => row.kind === 'removed');
        expect(removed.map((row) => row.text)).to.deep.equal(['вторая']);
    });

    it('замена строки видна как удаление и добавление', () => {
        const rows = buildLineDiff('было', 'стало');
        expect(rows.map((row) => row.kind)).to.deep.equal(['removed', 'added']);
    });
});
