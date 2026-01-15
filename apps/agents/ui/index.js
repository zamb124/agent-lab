/**
 * Agents Builder - Entry Point
 */

console.log('🚀 Agents Builder загружается...');

// Импортируем главное приложение - оно автоматически инициализирует все сервисы
import './app/AgentsApp.js';

// Импортируем компоненты из core/frontend
import '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/glass-form-modal.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/glass-textarea.js';
import '@platform/lib/components/glass-toast.js';
import '@platform/lib/components/glass-spinner.js';

// Компоненты выполнения
import './components/execution-runner/index.js';
import './components/execution-panel/index.js';
import './components/breakpoint-manager/index.js';
import './components/variables-panel/index.js';
import './components/variable-editor-modal/index.js';

// Редакторы
import './components/editors/json-field-editor.js';
import './components/editors/tag-input.js';
import './components/editors/llm-config-editor.js';
import './components/editors/llm-mocks-editor.js';
import './components/editors/state-mapping-editor.js';
import './components/editors/python-code-editor.js';
import './components/editors/test-panel.js';

// Редакторы нод
import './components/nodes/index.js';

// Модальные окна (загружаем ДО функциональных компонентов, которые их используют)
import './modals/platform-modal-host.js';
import './modals/confirm-modal.js';
import './modals/sessions-modal.js';
import './modals/tracing-modal.js';
import './modals/span-details-modal.js';
import './modals/raw-json-modal.js';
import './modals/state-modal.js';
import './modals/agent-edit-modal.js';
import './modals/agent-create-modal.js';
import './modals/edge-condition-modal.js';
import './modals/mcp-servers-modal.js';
import './modals/variables-modal.js';

// Функциональные компоненты
import './features/chat/chat-message.js';
import './features/chat/chat-messages.js';
import './features/chat/chat-input.js';
import './features/chat/platform-chat.js';
import './components/sidebar/agents-sidebar.js';

// Редактор агентов
import './features/agent-editor/agent-editor-page.js';
import './features/agent-editor/editor-header.js';
import './features/agent-editor/node-types-sidebar.js';
import './features/agent-editor/agent-canvas/index.js';
import './features/agent-editor/bottom-toolbar.js';
import './features/agent-editor/property-panel.js';
import './features/agent-editor/skills-tabs/index.js';

console.log('✅ Agents Builder инициализирован');
