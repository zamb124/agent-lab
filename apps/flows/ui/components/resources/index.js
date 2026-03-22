/**
 * Resource Editors - экспорт всех редакторов ресурсов
 */
export { BaseResourceEditor } from './base-resource-editor.js';
export { CodeResourceEditor } from './code-resource-editor.js';
export { RAGResourceEditor } from './rag-resource-editor.js';
export { FilesResourceEditor } from './files-resource-editor.js';
export { PromptResourceEditor } from './prompt-resource-editor.js';
export { LLMResourceEditor } from './llm-resource-editor.js';
export { SecretResourceEditor } from './secret-resource-editor.js';
export { HTTPResourceEditor } from './http-resource-editor.js';
export { CacheResourceEditor } from './cache-resource-editor.js';

// Импортируем для регистрации custom elements
import './base-resource-editor.js';
import './code-resource-editor.js';
import './rag-resource-editor.js';
import './files-resource-editor.js';
import './prompt-resource-editor.js';
import './llm-resource-editor.js';
import './secret-resource-editor.js';
import './http-resource-editor.js';
import './cache-resource-editor.js';
