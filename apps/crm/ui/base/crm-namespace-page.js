/**
 * Страница CRM с реактивным срезом пространства для API (`null` = все пространства).
 */

import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { selectCrmApiNamespace } from '../utils/crm-namespace-select.js';

export class CRMNamespacePage extends PlatformPage {
    constructor() {
        super();
        this._crmNamespaceSel = this.select(selectCrmApiNamespace);
    }
}
