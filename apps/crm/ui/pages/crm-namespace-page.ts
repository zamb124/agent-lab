/**
 * Страница CRM с реактивным срезом пространства для API (`null` = все пространства).
 */

import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { selectCrmApiNamespace } from '../_helpers/crm-namespace-select.js';
import type {
} from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

export class CRMNamespacePage extends PlatformPage {
    protected _crmNamespaceSel: SelectController<string | null>;

    constructor() {
        super();
        this._crmNamespaceSel = this.select(selectCrmApiNamespace);
    }
}
