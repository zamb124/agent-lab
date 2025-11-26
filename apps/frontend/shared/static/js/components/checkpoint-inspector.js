/**
 * CheckpointInspector - компонент для визуализации чекпоинтов LangGraph
 */

class CheckpointInspector {
    constructor(app, chatManager = null) {
        this.app = app;
        this.chatManager = chatManager;
    }

    async showInspector(currentSession) {
        console.log('🔍 showInspector вызван:', { currentSession });
        
        if (!currentSession) {
            console.warn('⚠️ Нет активной сессии для инспекции');
            this.app.showNotification('Нет активной сессии для инспекции', 'warning');
            return;
        }

        const threadId = await this.getFullSessionId(currentSession);
        if (!threadId) {
            this.app.showNotification('Не удалось сформировать thread_id для инспекции', 'warning');
            return;
        }

        try {
            const response = await fetch(`/frontend/api/checkpoints/timeline/${encodeURIComponent(threadId)}?include_values=true`);
            if (!response.ok) {
                if (response.status === 404) {
                    this.app.showNotification('Нет данных о выполнении для этой сессии', 'info');
                    return;
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const timelineData = await response.json();
            const modalData = this.renderInspectorModal(timelineData, threadId);
            const content = modalData.content;
            
            if (window.modalManager) {
                const modalId = window.modalManager.show(content, {
                    title: `Инспекция сессии: ${threadId.substring(0, 50)}...`,
                    size: 'full',
                    closeButton: true
                });
            } else {
                console.error('ModalManager не найден');
            }

        } catch (error) {
            console.error('❌ Ошибка загрузки данных инспекции:', error);
            this.app.showNotification('Ошибка загрузки данных инспекции: ' + error.message, 'danger');
        }
    }

    renderInspectorModal(timelineData, threadId) {
        console.log('🎯 renderInspectorModal вызван:', { timelineData, threadId });
        
        const tree = timelineData.tree || [];
        console.log('🌳 Tree data:', tree);
        
        const summary = timelineData.summary || {};
        console.log('📊 Summary:', summary);

        const sanitizedThreadId = threadId.replace(/[^a-zA-Z0-9]/g, '-');

        const toolStatsHtml = summary.tool_stats && Object.keys(summary.tool_stats).length > 0
            ? `<div style="display: flex; gap: 0.5rem; flex-wrap: wrap; font-size: 0.8em;">
                    ${Object.entries(summary.tool_stats).map(([name, count]) =>
                        `<span style=\"background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 999px; padding: 0.15rem 0.5rem;\">${name}: ${count}</span>`
                    ).join('')}
               </div>`
            : '';

        const transitionStatsHtml = summary.transition_stats && Object.keys(summary.transition_stats).length > 0
            ? `<div style="display: flex; gap: 0.5rem; flex-wrap: wrap; font-size: 0.8em;">
                    ${Object.entries(summary.transition_stats).map(([name, count]) =>
                        `<span style=\"background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 999px; padding: 0.15rem 0.5rem;\">${name}: ${count}</span>`
                    ).join('')}
               </div>`
            : '';

        const hasSummaryDetails = toolStatsHtml || transitionStatsHtml;
        const summaryDetailsId = `checkpoint-summary-details-${sanitizedThreadId}`;
        const summaryDetailsBlock = hasSummaryDetails
            ? `<div id="${summaryDetailsId}" style="display: none; padding: 0.5rem 0.75rem 0.5rem 0.75rem; border-bottom: 1px solid var(--border-color); background: var(--bg-secondary, #f5f5f5);">
                    ${transitionStatsHtml ? `<div style=\"margin-bottom: 0.35rem;\"><span style=\"font-size: 0.75rem; color: var(--text-secondary);\">Переходы:</span> ${transitionStatsHtml}</div>` : ''}
                    ${toolStatsHtml ? `<div><span style=\"font-size: 0.75rem; color: var(--text-secondary);\">Инструменты:</span> ${toolStatsHtml}</div>` : ''}
               </div>`
            : '';

        let html = `
            <div class="checkpoint-inspector-container" style="height: 100vh; display: flex; flex-direction: column;">
                <div class="checkpoint-summary" style="padding: 0.5rem 0.75rem; background: var(--bg-secondary, #f5f5f5); border-bottom: 1px solid var(--border-color); flex-shrink: 0; display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;">
                    <strong style="font-size: 0.9rem;">Шагов: ${summary.total_steps || 0}</strong>
                    <span style="font-size: 0.8rem; color: var(--text-secondary);"><code style="font-size: 0.75rem;">${threadId.substring(0, 40)}${threadId.length > 40 ? '…' : ''}</code></span>
                    <button type="button" data-expanded="false" style="margin-left: auto; font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 999px; border: 1px solid var(--border-color); background: var(--bg-primary); cursor: pointer;" onclick="(function(btn){ const block = document.getElementById('${summaryDetailsId}'); if (!block) return; const expanded = btn.dataset.expanded === 'true'; const nextExpanded = !expanded; btn.dataset.expanded = nextExpanded ? 'true' : 'false'; block.style.display = nextExpanded ? 'block' : 'none'; btn.textContent = nextExpanded ? 'Скрыть детали' : 'Детали'; })(this)">Детали</button>
                    <button type="button" style="font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 999px; border: 1px solid var(--border-color); background: var(--bg-primary); cursor: pointer;" onclick="navigator.clipboard?.writeText(${JSON.stringify(threadId)})">Копировать ID</button>
                </div>
                ${summaryDetailsBlock}

                <div class="checkpoint-tree" style="flex: 1; overflow-y: auto; padding: 0.75rem 1rem 1.5rem;">
        `;
        if (tree.length === 0) {
            console.warn('⚠️ Дерево чекпоинтеров пустое');
            html += `
                <div style="padding: 3rem; text-align: center; color: var(--text-secondary, #666); background: var(--bg-primary, white); border-radius: 8px; border: 1px solid var(--border-color, #ddd);">
                    <div style="font-size: 3rem; margin-bottom: 1rem;">📭</div>
                    <h4 style="margin: 0 0 1rem 0; color: var(--text-primary, #333);">Нет данных для инспекции</h4>
                    <p style="margin: 0; line-height: 1.5;">
                        Для этой сессии не найдено чекпоинтеров выполнения.<br>
                        Возможно, сессия еще не начата или агент не использует чекпоинтеры.
                    </p>
                </div>
            `;
        } else {
            const sortedTree = this.flattenAndSortTree(tree);
            
            html += `<div class="timeline-tree">`;
            
            sortedTree.forEach((node, index) => {
                const step = node.step || 0;
                const timestamp = node.timestamp || '';
                const nodeName = node.node_name || node.source || 'unknown';
                const metadata = node.metadata || {};
                const toolCalls = node.tool_calls || [];
                const storeVars = node.store_variables || {};
                const nextNodes = node.next_nodes || [];
                const values = node.values || {};
                const messages = Array.isArray(values.messages) ? values.messages : [];
                const otherChannels = { ...values };
                if (otherChannels.messages) {
                    delete otherChannels.messages;
                }
                
                const agentInfo = this.extractAgentInfo(node, metadata);
                const nodeLabel = metadata.node || metadata.state_name || nodeName;
                const taskId = node.task_id || metadata.task_id || metadata.taskId;

                
                const borderColors = ['#007bff', '#28a745', '#ffc107', '#dc3545', '#17a2b8'];
                const borderColor = borderColors[index % borderColors.length];
                
                const timeStr = timestamp ? new Date(timestamp).toLocaleString('ru-RU') : 'Неизвестно';
                
                html += `
                    <div class="timeline-item" style="position: relative; margin-bottom: 1.5rem;">
                        <!-- Timeline линия -->
                        <div class="timeline-line" style="
                            position: absolute;
                            left: 20px;
                            top: 40px;
                            bottom: -1.5rem;
                            width: 2px;
                            background: var(--border-color, #ddd);
                        "></div>
                        
                        <!-- Timeline точка -->
                        <div class="timeline-dot" style="
                            position: absolute;
                            left: 16px;
                            top: 36px;
                            width: 10px;
                            height: 10px;
                            border-radius: 50%;
                            background: ${borderColor};
                            border: 2px solid white;
                            box-shadow: 0 0 0 2px ${borderColor}33;
                        "></div>
                        
                        <!-- Карточка шага -->
                        <div class="step-card" style="
                            margin-left: 50px;
                            padding: 1rem;
                            background: var(--bg-primary, white);
                            border: 1px solid var(--border-color, #ddd);
                            border-radius: 8px;
                            border-left: 4px solid ${borderColor};
                            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                        ">
                            
                            <!-- Заголовок -->
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                                <div>
                                    <h6 style="margin: 0; color: var(--text-primary, #333);">
                                        Шаг ${step} <span style="color: ${borderColor}; font-weight: bold;">[${this.escapeHtml(nodeLabel)}]</span>
                                    </h6>
                                    <small style="color: var(--text-secondary, #666);">
                                        ${this.escapeHtml(node.source || 'unknown')}
                                    </small>
                                    ${agentInfo ? `
                                        <br><small style="color: var(--text-secondary, #666); font-weight: bold;">
                                            🤖 Агент / Нода: ${this.escapeHtml(agentInfo)}
                                        </small>
                                    ` : ''}
                                    ${taskId ? `
                                        <br><small style="color: var(--text-secondary, #666);">Task ID: ${this.escapeHtml(taskId)}</small>
                                    ` : ''}
                                </div>
                                <div style="text-align: right;">
                                    <div style="font-size: 0.85em; color: var(--text-secondary, #666);">
                                        ${timeStr}
                                    </div>
                                    ${nextNodes.length > 0 ? `
                                        <div style="font-size: 0.8em; color: var(--text-primary, #333); margin-top: 0.25rem;">
                                            Следующие: ${nextNodes.slice(0, 3).join(', ')}${nextNodes.length > 3 ? '...' : ''}
                                        </div>
                                    ` : ''}
                                </div>
                            </div>

                            <!-- Входные данные (сообщения) -->
                            ${messages.length > 0 ? `
                                <div style="margin-bottom: 1rem; padding: 0.75rem; background: var(--bg-secondary, #f0f8ff); border-radius: 4px;">
                                    <strong style="color: var(--text-primary, #333); font-size: 0.9em;">💬 Сообщения:</strong>
                                    <div style="margin-top: 0.5rem; max-height: 260px; overflow-y: auto;">
                                        ${messages.map((msg) => {
                                            const role = msg.role || msg.type || 'unknown';
                                            const roleEmoji = role === 'user' ? '👤' : role === 'assistant' ? '🤖' : '⚡';
                                            const content = this.formatMessageContent(msg);
                                            return `
                                                <div style="margin-bottom: 0.75rem; padding: 0.5rem; background: white; border-radius: 4px; border-left: 3px solid ${role === 'user' ? '#007bff' : '#28a745'};">
                                                    <strong style="font-size: 0.8em;">${roleEmoji} ${this.escapeHtml(role)}:</strong>
                                                    <pre style="margin: 0.35rem 0 0; white-space: pre-wrap; font-size: 0.8em; color: var(--text-secondary, #333); background: #f7f9fc; padding: 0.5rem; border-radius: 4px;">${content}</pre>
                                                </div>
                                            `;
                                        }).join('')}
                                    </div>
                                </div>
                            ` : ''}

                            <!-- Вызовы инструментов -->
                            ${toolCalls.length > 0 ? `
                                <div style="margin-bottom: 1rem; padding: 0.75rem; background: var(--bg-secondary, #f9f9f9); border-radius: 4px;">
                                    <strong style="color: var(--text-primary, #333); font-size: 0.9em;">🔧 Вызовы инструментов:</strong>
                                    <ul style="margin: 0.5rem 0 0 0; padding-left: 1.5rem; font-size: 0.9em;">
                                        ${toolCalls.map(tc => `
                                            <li>
                                                <strong>${tc.name || 'unknown'}</strong>
                                                ${tc.arguments && Object.keys(tc.arguments).length > 0 ? 
                                                    `(${Object.entries(tc.arguments).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})` : 
                                                    '()'}
                                            </li>
                                        `).join('')}
                                    </ul>
                                </div>
                            ` : ''}

                            <!-- Переменные состояния -->
                            ${storeVars && Object.keys(storeVars).length > 0 ? `
                                <div style="margin-bottom: 1rem; padding: 0.75rem; background: var(--bg-secondary, #e7f3ff); border-radius: 4px;">
                                    <strong style="color: var(--text-primary, #333); font-size: 0.9em;">📦 Переменные состояния:</strong>
                                    <div style="margin-top: 0.5rem;">
                                        ${(() => {
                                            const varEntries = Object.entries(storeVars);
                                            const showLimit = 3;
                                            const hasMore = varEntries.length > showLimit;
                                            
                                            let varsHtml = varEntries.slice(0, showLimit).map(([key, value]) => {
                                                const valueStr = value === null ? 'null' : 
                                                                 value === undefined ? 'undefined' : 
                                                                 String(value);
                                                return `<div><strong>${key}:</strong> <code>${valueStr.length > 50 ? valueStr.substring(0, 50) + '...' : valueStr}</code></div>`;
                                            }).join('');
                                            
                                            if (hasMore) {
                                                const moreVarsHtml = varEntries.slice(showLimit).map(([key, value]) => {
                                                    const valueStr = value === null ? 'null' : 
                                                                     value === undefined ? 'undefined' : 
                                                                     String(value);
                                                    return `<div><strong>${key}:</strong> <code>${valueStr}</code></div>`;
                                                }).join('');
                                                
                                                varsHtml += `<div style="margin-top: 0.5rem;">
                                                    <button onclick="this.parentElement.innerHTML = '${moreVarsHtml.replace(/'/g, "\\'")}'; this.remove();" style="background: none; border: 1px solid var(--border-color, #ddd); padding: 0.25rem 0.5rem; border-radius: 4px; cursor: pointer; font-size: 0.8em;">
                                                        Показать еще ${varEntries.length - showLimit} переменных
                                                    </button>
                                                </div>`;
                                            }
                                            
                                            return varsHtml;
                                        })()}
                                    </div>
                                </div>
                            ` : ''}

                            <!-- Метаданные -->
                            ${metadata && Object.keys(metadata).length > 0 ? `
                                <div style="margin-bottom: 1rem; padding: 0.75rem; background: var(--bg-secondary, #f4f0ff); border-radius: 4px;">
                                    <strong style="color: var(--text-primary, #333); font-size: 0.9em;">🧾 Метаданные шага</strong>
                                    <details style="margin-top: 0.5rem;">
                                        <summary style="cursor: pointer; font-size: 0.85em; color: var(--text-secondary);">Показать JSON</summary>
                                        <pre style="margin: 0.5rem 0 0; white-space: pre-wrap; font-size: 0.8em; background: #fff; padding: 0.5rem; border-radius: 4px; border: 1px solid var(--border-color);">${this.formatJSON(metadata)}</pre>
                                    </details>
                                </div>
                            ` : ''}

                            <!-- Другие каналы -->
                            ${otherChannels && Object.keys(otherChannels).length > 0 ? `
                                <div style="margin-bottom: 0; padding: 0.75rem; background: var(--bg-secondary, #eefaf4); border-radius: 4px;">
                                    <strong style="color: var(--text-primary, #333); font-size: 0.9em;">🔄 Каналы состояний</strong>
                                    <details style="margin-top: 0.5rem;">
                                        <summary style="cursor: pointer; font-size: 0.85em; color: var(--text-secondary);">Показать JSON</summary>
                                        <pre style="margin: 0.5rem 0 0; white-space: pre-wrap; font-size: 0.8em; background: #fff; padding: 0.5rem; border-radius: 4px; border: 1px solid var(--border-color);">${this.formatJSON(otherChannels)}</pre>
                                    </details>
                                </div>
                            ` : ''}

                        </div>
                    </div>
                `;
            });
            
            html += `</div>`;
        }

        html += `
                </div>
            </div>
        `;

        return {
            content: html,
            networkData: null,
            timelineItems: null,
            threadId: threadId
        };
    }

    extractAgentInfo(node, metadata = {}) {
        const taskId = node.task_id || metadata.task_id;
        const agentFields = [
            metadata.agent,
            metadata.actor,
            metadata.flow,
            metadata.node,
            metadata.tool,
            taskId
        ].filter(Boolean);

        if (agentFields.length > 0) {
            return agentFields.join(' · ');
        }

        return null;
    }

    escapeHtml(value) {
        if (value === null || value === undefined) {
            return '';
        }
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    formatJSON(obj) {
        try {
            return this.escapeHtml(JSON.stringify(obj, null, 2));
        } catch (e) {
            return this.escapeHtml(String(obj));
        }
    }

    formatMessageContent(message) {
        if (!message) {
            return '';
        }

        const { content } = message;

        if (typeof content === 'string') {
            return this.escapeHtml(content);
        }

        if (Array.isArray(content)) {
            const parts = content.map((part) => {
                if (typeof part === 'string') {
                    return part;
                }
                if (part && typeof part === 'object') {
                    if (typeof part.text === 'string') {
                        return part.text;
                    }
                    if (typeof part.content === 'string') {
                        return part.content;
                    }
                    return JSON.stringify(part, null, 2);
                }
                return String(part);
            });
            return this.escapeHtml(parts.join('\n'));
        }

        if (content && typeof content === 'object') {
            return this.escapeHtml(JSON.stringify(content, null, 2));
        }

        return this.escapeHtml(String(content));
    }

    flattenAndSortTree(tree) {
        const result = [];
        
        const processNode = (node) => {
            result.push(node);
            if (node.children) {
                // Сортируем детей по времени
                const sortedChildren = [...node.children].sort((a, b) => {
                    const timeA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
                    const timeB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
                    return timeA - timeB;
                });
                sortedChildren.forEach(processNode);
            }
        };
        
        // Обрабатываем корневые узлы
        tree.forEach(processNode);
        
        // Сортируем весь результат по времени
        return result.sort((a, b) => {
            const timeA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
            const timeB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
            return timeA - timeB;
        });
    }

    async getFullSessionId(sessionId) {
        if (!sessionId) return null;
        
        if (sessionId.includes(':')) {
            return sessionId;
        }
        
        let userId = 'unknown';
        try {
            const userResponse = await fetch('/frontend/api/admin/me');
            if (userResponse.ok) {
                const userData = await userResponse.json();
                userId = userData.user_id;
                console.log('✅ Получен user_id для thread_id:', userId);
            } else {
                console.warn('⚠️ Не удалось получить user_id, используем unknown');
            }
        } catch (e) {
            console.warn('⚠️ Ошибка получения user_id:', e);
        }
        
        let flowId = 'unknown';
        if (this.chatManager && this.chatManager.currentAgent) {
            flowId = this.chatManager.currentAgent;
        }
        
        if (sessionId && sessionId.includes(':')) {
            const parts = sessionId.split(':');
            if (parts.length >= 3) {
                const fullSessionId = sessionId;
                console.log('🔍 Используем полный session_id для инспекции:', fullSessionId);
                return fullSessionId;
            }
        }
        
        const fullSessionId = `web:${userId}:${flowId}:${sessionId}`;
        console.log('🔍 Сформирован полный session_id для инспекции:', fullSessionId);
        return fullSessionId;
    }

    initializeVisComponents(modalData) {
        // Метод оставлен для совместимости, но Vis.js больше не используется
        console.log('Vis.js не используется - отображаем текстовое timeline-дерево');
    }
}

export default CheckpointInspector;
