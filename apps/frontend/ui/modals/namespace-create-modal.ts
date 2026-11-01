/**
 * FrontendNamespaceCreateModal — создание namespace из консоли.
 *
 * Отправка идёт в `namespaces.resource.events.CREATE_REQUESTED` через
 * `useForm('frontend/namespace_create_form')`; фабрика зовёт команду
 * `frontend/namespaces/create_requested` (REST `/frontend/api/namespaces`)
 * и эмитит CREATED/CREATE_FAILED. База `PlatformNamespaceCreateModal`
 * выбирает созданный namespace в platform-namespace selection и закрывает
 * модалку.
 */

import { PlatformNamespaceCreateModal } from '@platform/lib/components/platform-namespace-create-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

const FORM_NAME = 'frontend/namespace_create_form';
const NAMESPACES_NAME = 'frontend/namespaces';

export class FrontendNamespaceCreateModal extends PlatformNamespaceCreateModal {
    static modalKind = 'frontend.namespace_create';

    constructor() {
        super();
        this._namespaces = this.useResource(NAMESPACES_NAME);
        this._form = this.useForm(FORM_NAME);
    }
}

customElements.define('frontend-namespace-create-modal', FrontendNamespaceCreateModal);
registerModalKind(FrontendNamespaceCreateModal.modalKind, 'frontend-namespace-create-modal');
