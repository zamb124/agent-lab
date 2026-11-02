/**
 * ShopMenuPage — рейка категорий: ввод имени в cat-add включает кнопку
 * и _addCategory дергает shop/category_create с тем же payload.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import {
    shopShopsResource,
    shopUpdateOp,
    shopBadgeIconsListOp,
    shopCategoriesListOp,
    shopProductsListOp,
    shopCategoryCreateOp,
    shopCategoryRemoveOp,
    shopCategoriesReorderOp,
    shopProductUpdateOp,
    shopProductRemoveOp,
    shopProductsReorderOp,
    shopProductsImportOp,
    shopAiParseMenuOp,
    shopAiDescribeBatchOp,
    shopAiEnhancePhotoOp,
    shopAiGeneratePhotoOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
import {
    shopCreateOp,
    shopPublishOp,
    shopAiAutofillOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import '../../../../apps/shop/ui/pages/shop-menu-page.js';
import '../../../../apps/shop/ui/pages/shop-home-page.js';

const FACTORIES = [
    shopShopsResource,
    shopUpdateOp,
    shopBadgeIconsListOp,
    shopCategoriesListOp,
    shopProductsListOp,
    shopCategoryCreateOp,
    shopCategoryRemoveOp,
    shopCategoriesReorderOp,
    shopProductUpdateOp,
    shopProductRemoveOp,
    shopProductsReorderOp,
    shopProductsImportOp,
    shopAiParseMenuOp,
    shopAiDescribeBatchOp,
    shopAiEnhancePhotoOp,
    shopAiGeneratePhotoOp,
    shopCreateOp,
    shopPublishOp,
    shopAiAutofillOp,
    platformFileCreateOp,
];

function typeIntoField(host: HTMLElement, selector: string, text: string): void {
    const field = host.shadowRoot!.querySelector(selector) as HTMLElement & { shadowRoot: ShadowRoot };
    expect(field, `field ${selector}`).to.exist;
    const inner = field.shadowRoot.querySelector('platform-field-string') as HTMLElement & { shadowRoot: ShadowRoot };
    expect(inner, `${selector} platform-field-string`).to.exist;
    const input = inner.shadowRoot.querySelector('input') as HTMLInputElement;
    expect(input, `${selector} input`).to.exist;
    input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
}

describe('shop-menu-page: добавление категории', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES });
    });

    it('ввод имени включает кнопку "+" (disabled=false)', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        await elementUpdated(el);
        const addBtn = el.shadowRoot!.querySelector('.cat-add platform-button') as HTMLElement & { disabled: boolean };
        expect(addBtn, 'cat-add platform-button').to.exist;
        expect(addBtn.disabled).to.equal(true);
        typeIntoField(el, '.cat-add platform-field', 'Суши');
        await elementUpdated(el);
        expect((el as unknown as { _newCategory: string })._newCategory).to.equal('Суши');
        expect(addBtn.disabled).to.equal(false);
    });
});

describe('shop-home-page: slug-поле', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES });
    });

    it('ручной ввод кириллицы транслитерируется в валидный slug', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-home-page></shop-home-page>
        `);
        await elementUpdated(el);
        const slugField = el.shadowRoot!.querySelector('platform-field[hint]') as HTMLElement;
        expect(slugField, 'slug platform-field с hint').to.exist;
        const inner = slugField.shadowRoot!.querySelector('platform-field-string') as HTMLElement;
        const input = inner.shadowRoot!.querySelector('input') as HTMLInputElement;
        input.value = 'выфвыфвфы';
        input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        await elementUpdated(el);
        expect((el as unknown as { _newSlug: string })._newSlug).to.equal('vyfvyfvfy');
    });
});
