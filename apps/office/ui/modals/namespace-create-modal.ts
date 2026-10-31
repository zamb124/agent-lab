/**
 * OfficeNamespaceCreateModal — создание workspace через BFF documents.
 *
 * BFF проксирует запрос в CRM (`POST /documents/api/v1/namespaces`).
 * Шаблоны загружаются через `useOp('office/namespace_templates')` — base-класс
 * `PlatformNamespaceCreateModal` рендерит секцию выбора шаблона и сидит
 * `template_id`. Отправка идёт в `namespacesResource.events.CREATE_REQUESTED`
 * через `useForm('office/namespace_create_form')`; после CREATED база выбирает
 * новый namespace в platform-namespace selection и закрывает модалку.
 */

import { PlatformNamespaceCreateModal } from '@platform/lib/components/platform-namespace-create-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

const FORM_NAME = 'office/namespace_create_form';
const NAMESPACES_NAME = 'office/namespaces';
const TEMPLATES_NAME = 'office/namespace_templates';

export class OfficeNamespaceCreateModal extends PlatformNamespaceCreateModal {
    static modalKind = 'office.namespace_create';

    constructor() {
        super();
        this._templates = this.useOp(TEMPLATES_NAME);
        this._namespaces = this.useResource(NAMESPACES_NAME);
        this._form = this.useForm(FORM_NAME);
    }
}

customElements.define('office-namespace-create-modal', OfficeNamespaceCreateModal);
registerModalKind(OfficeNamespaceCreateModal.modalKind, 'office-namespace-create-modal');
