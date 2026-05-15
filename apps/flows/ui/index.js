/**
 * Bootstrap Flows UI: импорт <flows-app> + страниц + компонентов.
 *
 * Доменные операции — фабрики в `events/resources/*.resource.js`. Транспорт —
 * единый platform WS `/flows/api/ws/notifications` для команд чата/operator
 * и REST для CRUD.
 */

import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/glass-form-modal.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/glass-toast.js';
import '@platform/lib/components/platform-modal-stack.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/company-modal.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/layout/platform-island.js';
import '@platform/lib/components/platform-shell-page.js';

import './app/flows-app.js';

// Страницы
import './pages/flows-list-page.js';
import './pages/flows-home-page.js';
import './pages/chat-page.js';
import './pages/flow-editor-page.js';
import './pages/operator-page.js';

// Компоненты
import './components/flows-sidebar.js';
import './components/flows-catalog-list.js';
import './components/flow-card.js';
import './components/branch-item.js';
import './components/chat/chat-input.js';
import './components/chat/chat-message.js';
import './components/chat/chat-messages.js';
import './components/chat/flows-chat-run-trace.js';

// Универсальные редакторы
import './components/editors/flows-code-editor.js';
import './components/editors/flows-code-workbench.js';
import './components/editors/flows-json-field-editor.js';
import './components/editors/flows-llm-config-editor.js';
import './components/editors/flows-llm-mocks-editor.js';
import './components/editors/flows-state-mapping-editor.js';
import './components/editors/flows-variable-input.js';
import './components/editors/flows-searchable-combobox.js';

// Редакторы нод
import './components/nodes/flows-base-node-editor.js';
import './components/nodes/flows-llm-node-editor.js';
import './components/nodes/flows-code-node-editor.js';
import './components/nodes/flows-channel-node-editor.js';
import './components/nodes/flows-flow-node-editor.js';
import './components/nodes/flows-mcp-node-editor.js';
import './components/nodes/flows-hitl-node-editor.js';
import './components/nodes/flows-resource-node-editor.js';
import './components/nodes/flows-external-api-editor.js';
import './components/nodes/flows-remote-flow-editor.js';

// Редакторы ресурсов
import './components/resources/flows-base-resource-editor.js';
import './components/resources/flows-llm-resource-editor.js';
import './components/resources/flows-code-resource-editor.js';
import './components/resources/flows-files-resource-editor.js';

// Editor shell
import './components/editor/flows-editor-header.js';
import './components/editor/flows-bottom-toolbar.js';
import './components/editor/flows-node-types-sidebar.js';
import './components/editor/flows-flow-property-panel.js';
import './components/editor/flows-property-panel.js';
import './components/editor/flows-resource-property-panel.js';
import './components/editor/flows-branches-tabs.js';
import './components/editor/flows-execution-panel.js';
import './components/flow-canvas/flows-flow-canvas.js';

// Editor-related modals
import './modals/flows-edge-condition-modal.js';
import './modals/flows-incoming-policy-modal.js';
import './modals/flows-library-picker-modal.js';
import './modals/flows-tool-create-modal.js';
import './modals/flows-embedded-tool-config-modal.js';
import './modals/flows-code-node-drop-modal.js';
import './modals/flows-code-modal.js';
import './modals/flows-code-docs-modal.js';
import './modals/flows-tracing-modal.js';
import './modals/flows-span-details-modal.js';
import './modals/flows-logs-modal.js';
import './modals/flows-raw-json-modal.js';
import './modals/flows-state-modal.js';
import './modals/flows-mocks-modal.js';

// CRUD-модалки
import './modals/flows-flow-create-modal.js';
import './modals/flows-flow-edit-modal.js';
import './modals/flows-branch-create-modal.js';
import './modals/flows-sessions-modal.js';
import './modals/flows-mcp-servers-modal.js';
import './modals/flows-variable-editor-modal.js';
import './modals/flows-variables-modal.js';
import './modals/flows-trigger-editor-modal.js';
import './modals/flows-triggers-modal.js';
import './modals/flows-integrations-modal.js';
