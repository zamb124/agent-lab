/**
 * RagNamespaceCreateModal — создание namespace сервиса RAG.
 *
 * Отправка идёт в `namespaces.resource.events.CREATE_REQUESTED` через
 * `useForm('rag/namespace_create_form')`; фабрика делает POST `/rag/api/v1/namespaces`
 * и эмитит CREATED/CREATE_FAILED. База `PlatformNamespaceCreateModal` выбирает
 * созданный namespace в platform-namespace selection и закрывает модалку.
 */

import { PlatformNamespaceCreateModal } from '@platform/lib/components/platform-namespace-create-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

const FORM_NAME = 'rag/namespace_create_form';
const NAMESPACES_NAME = 'rag/namespaces';

export class RagNamespaceCreateModal extends PlatformNamespaceCreateModal {
    static modalKind = 'rag.namespace_create';

    constructor() {
        super();
        this._namespaces = this.useResource(NAMESPACES_NAME);
        this._form = this.useForm(FORM_NAME);
    }
}

customElements.define('rag-namespace-create-modal', RagNamespaceCreateModal);
registerModalKind(RagNamespaceCreateModal.modalKind, 'rag-namespace-create-modal');
