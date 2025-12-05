/**
 * CRM Module - Networkle
 * Основной JavaScript модуль для CRM функциональности
 */

class CRMModule {
    constructor() {
        this.apiBase = '/crm/api/v1';
        this.graph = null;
        this.init();
    }
    
    init() {
        console.log('CRM Module initialized');
        this.setupMarked();
        this.setupEventListeners();
        
        // Initial render for existing content
        this.renderMarkdownContent(document);
    }
    
    setupMarked() {
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,
                gfm: true,
                headerIds: false,
                mangle: false
            });
        }
    }
    
    setupEventListeners() {
        // HTMX события
        document.body.addEventListener('htmx:afterSwap', (e) => {
            this.onContentSwap(e);
        });
        
        // Закрытие модалки по Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModal();
            }
        });
        
        // Закрытие модалки по клику на overlay
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('crm-modal-overlay')) {
                this.closeModal();
            }
        });
    }
    
    onContentSwap(event) {
        const target = event.detail.target;
        
        // Инициализация графа если загружена страница графа
        if (target.querySelector('.crm-graph-container')) {
            this.initGraph();
        }
        
        // Инициализация редактора заметок
        if (target.querySelector('.crm-note-textarea')) {
            this.initNoteEditor();
        }
        
        // Рендеринг markdown контента
        this.renderMarkdownContent(target);
    }
    
    renderMarkdownContent(container) {
        if (typeof marked === 'undefined') return;
        
        const markdownElements = container.querySelectorAll('[data-markdown]');
        markdownElements.forEach(el => {
            const rawContent = el.getAttribute('data-markdown');
            if (rawContent) {
                el.innerHTML = marked.parse(rawContent);
            }
        });
    }
    
    // === API Methods ===
    
    async apiRequest(endpoint, options = {}) {
        const url = `${this.apiBase}${endpoint}`;
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
        };
        
        try {
            const response = await fetch(url, { ...defaultOptions, ...options });
            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('CRM API error:', error);
            this.showNotification('Ошибка при выполнении запроса', 'error');
            throw error;
        }
    }
    
    // === Notes ===
    
    initNoteEditor() {
        const textarea = document.querySelector('.crm-note-textarea');
        if (!textarea) return;
        
        // Auto-resize
        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = textarea.scrollHeight + 'px';
        });
        
        // Markdown preview tabs
        this.initMarkdownTabs();
        
        // @mention autocomplete
        this.initMentionAutocomplete(textarea);
    }
    
    // === @Mention Autocomplete ===
    
    initMentionAutocomplete(textarea) {
        this.mentionState = {
            active: false,
            startPos: 0,
            query: '',
            selectedIndex: 0,
            results: []
        };
        
        // Создаём dropdown контейнер
        let dropdown = document.getElementById('mention-dropdown');
        if (!dropdown) {
            dropdown = document.createElement('div');
            dropdown.id = 'mention-dropdown';
            dropdown.className = 'crm-mention-dropdown';
            dropdown.style.display = 'none';
            textarea.parentNode.style.position = 'relative';
            textarea.parentNode.appendChild(dropdown);
        }
        this.mentionDropdown = dropdown;
        
        // Обработчик ввода
        textarea.addEventListener('input', (e) => this.handleMentionInput(e));
        textarea.addEventListener('keydown', (e) => this.handleMentionKeydown(e));
        textarea.addEventListener('blur', () => {
            setTimeout(() => this.hideMentionDropdown(), 200);
        });
        
        // Клик по элементу dropdown
        dropdown.addEventListener('click', (e) => {
            const item = e.target.closest('.crm-mention-item');
            if (item) {
                const index = parseInt(item.dataset.index);
                this.selectMention(index);
            }
        });
    }
    
    handleMentionInput(e) {
        const textarea = e.target;
        const value = textarea.value;
        const cursorPos = textarea.selectionStart;
        
        // Ищем @ перед курсором
        const textBeforeCursor = value.substring(0, cursorPos);
        const atMatch = textBeforeCursor.match(/@([^\s@]*)$/);
        
        if (atMatch) {
            this.mentionState.active = true;
            this.mentionState.startPos = cursorPos - atMatch[0].length;
            this.mentionState.query = atMatch[1];
            this.searchMentions(atMatch[1]);
        } else {
            this.hideMentionDropdown();
        }
    }
    
    handleMentionKeydown(e) {
        if (!this.mentionState.active || !this.mentionState.results.length) return;
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.mentionState.selectedIndex = 
                    (this.mentionState.selectedIndex + 1) % this.mentionState.results.length;
                this.renderMentionDropdown();
                break;
            case 'ArrowUp':
                e.preventDefault();
                this.mentionState.selectedIndex = 
                    (this.mentionState.selectedIndex - 1 + this.mentionState.results.length) % this.mentionState.results.length;
                this.renderMentionDropdown();
                break;
            case 'Enter':
            case 'Tab':
                if (this.mentionState.active && this.mentionState.results.length) {
                    e.preventDefault();
                    this.selectMention(this.mentionState.selectedIndex);
                }
                break;
            case 'Escape':
                this.hideMentionDropdown();
                break;
        }
    }
    
    async searchMentions(query) {
        if (query.length < 1) {
            this.mentionState.results = [];
            this.hideMentionDropdown();
            return;
        }
        
        try {
            const results = await this.apiRequest(`/entities/autocomplete?q=${encodeURIComponent(query)}&limit=8`);
            this.mentionState.results = results;
            this.mentionState.selectedIndex = 0;
            
            if (results.length > 0) {
                this.renderMentionDropdown();
            } else {
                this.hideMentionDropdown();
            }
        } catch (error) {
            console.error('Mention search error:', error);
            this.hideMentionDropdown();
        }
    }
    
    renderMentionDropdown() {
        const { results, selectedIndex } = this.mentionState;
        
        if (!results.length) {
            this.hideMentionDropdown();
            return;
        }
        
        const typeIcons = {
            person: 'ti-user',
            company: 'ti-building',
            project: 'ti-folder'
        };
        
        const typeColors = {
            person: 'var(--crm-blue)',
            company: 'var(--crm-purple)',
            project: 'var(--crm-green)'
        };
        
        this.mentionDropdown.innerHTML = results.map((entity, index) => `
            <div class="crm-mention-item ${index === selectedIndex ? 'selected' : ''}" 
                 data-index="${index}"
                 data-id="${entity.entity_id || entity.id}">
                <div class="crm-mention-icon" style="color: ${typeColors[entity.type] || 'var(--crm-teal)'}">
                    <i class="ti ${typeIcons[entity.type] || 'ti-tag'}"></i>
                </div>
                <div class="crm-mention-info">
                    <div class="crm-mention-name">${this.escapeHtml(entity.name)}</div>
                    <div class="crm-mention-type">${entity.type}</div>
                </div>
            </div>
        `).join('');
        
        this.mentionDropdown.style.display = 'block';
    }
    
    selectMention(index) {
        const entity = this.mentionState.results[index];
        if (!entity) return;
        
        const textarea = document.querySelector('.crm-note-textarea');
        if (!textarea) return;
        
        const value = textarea.value;
        const beforeMention = value.substring(0, this.mentionState.startPos);
        const afterMention = value.substring(textarea.selectionStart);
        
        // Вставляем ссылку на сущность: [@Name](entity:id)
        const mentionText = `[@${entity.name}](entity:${entity.entity_id || entity.id})`;
        
        textarea.value = beforeMention + mentionText + afterMention;
        
        // Перемещаем курсор после вставки
        const newPos = beforeMention.length + mentionText.length;
        textarea.setSelectionRange(newPos, newPos);
        textarea.focus();
        
        this.hideMentionDropdown();
        this.showNotification(`Добавлена ссылка на ${entity.name}`, 'success');
    }
    
    hideMentionDropdown() {
        this.mentionState.active = false;
        this.mentionState.results = [];
        if (this.mentionDropdown) {
            this.mentionDropdown.style.display = 'none';
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    initMarkdownTabs() {
        const tabs = document.querySelectorAll('.crm-markdown-tab');
        const editor = document.getElementById('note-content-editor');
        const preview = document.getElementById('note-content-preview');
        
        if (!tabs.length || !editor || !preview) return;
        
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const mode = tab.getAttribute('data-tab');
                
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                
                if (mode === 'edit') {
                    editor.style.display = 'block';
                    preview.style.display = 'none';
                } else {
                    editor.style.display = 'none';
                    preview.style.display = 'block';
                    
                    if (typeof marked !== 'undefined') {
                        preview.innerHTML = marked.parse(editor.value || '');
                    } else {
                        preview.textContent = editor.value || '';
                    }
                }
            });
        });
    }
    
    // === Voice Input ===
    
    initVoiceInput() {
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
            console.warn('Speech Recognition not supported');
            return;
        }
        
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = 'ru-RU';
        
        this.recognition.onresult = (event) => {
            const textarea = document.querySelector('.crm-note-textarea');
            if (!textarea) return;
            
            let interimTranscript = '';
            let finalTranscript = '';
            
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript;
                } else {
                    interimTranscript += transcript;
                }
            }
            
            if (finalTranscript) {
                const currentPos = textarea.selectionStart;
                const textBefore = textarea.value.substring(0, currentPos);
                const textAfter = textarea.value.substring(currentPos);
                textarea.value = textBefore + finalTranscript + ' ' + textAfter;
                textarea.setSelectionRange(currentPos + finalTranscript.length + 1, currentPos + finalTranscript.length + 1);
            }
        };
        
        this.recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            this.stopVoiceInput();
        };
        
        this.recognition.onend = () => {
            this.isRecording = false;
            this.updateVoiceButton(false);
        };
    }
    
    toggleVoiceInput() {
        if (!this.recognition) {
            this.initVoiceInput();
        }
        
        if (!this.recognition) {
            this.showNotification('Голосовой ввод не поддерживается', 'error');
            return;
        }
        
        if (this.isRecording) {
            this.stopVoiceInput();
        } else {
            this.startVoiceInput();
        }
    }
    
    startVoiceInput() {
        this.recognition.start();
        this.isRecording = true;
        this.updateVoiceButton(true);
    }
    
    stopVoiceInput() {
        this.recognition.stop();
        this.isRecording = false;
        this.updateVoiceButton(false);
    }
    
    updateVoiceButton(isActive) {
        const btn = document.querySelector('[data-voice-input]');
        if (btn) {
            btn.classList.toggle('recording', isActive);
            btn.querySelector('i').className = isActive ? 'ti ti-microphone-off' : 'ti ti-microphone';
        }
    }
    
    async analyzeNote(noteId) {
        try {
            const result = await this.apiRequest(`/notes/${noteId}/analyze`, {
                method: 'POST'
            });
            
            // Показываем модалку с результатами AI анализа
            this.showAISuggestions(result);
            return result;
        } catch (error) {
            console.error('Error analyzing note:', error);
        }
    }
    
    showAISuggestions(analysis) {
        // Триггерим HTMX запрос для показа модалки с результатами
        htmx.ajax('GET', `/crm/partials/ai-suggestions?data=${encodeURIComponent(JSON.stringify(analysis))}`, {
            target: '#modal-container',
            swap: 'innerHTML'
        });
    }
    
    // === Knowledge Graph ===
    
    async initGraph() {
        const container = document.querySelector('.crm-graph-canvas');
        if (!container) return;
        
        // Проверяем наличие vis.js
        if (typeof vis === 'undefined') {
            console.warn('vis.js not loaded, loading...');
            await this.loadVisJs();
        }
        
        try {
            const graphData = await this.apiRequest('/graph');
            this.renderGraph(container, graphData);
        } catch (error) {
            console.error('Error loading graph:', error);
        }
    }
    
    async loadVisJs() {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = '/static/crm/js/vis-network.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    renderGraph(container, data) {
        const nodes = new vis.DataSet(data.nodes.map(node => ({
            id: node.id,
            label: node.name,
            color: this.getEntityColor(node.type),
            shape: 'dot',
            size: 20,
            font: { color: '#2D3A4F', size: 12 }
        })));
        
        const edges = new vis.DataSet(data.relationships.map(rel => ({
            from: rel.source_entity_id,
            to: rel.target_entity_id,
            label: rel.relationship_type,
            arrows: 'to',
            color: { color: '#8A9AAD', opacity: 0.6 },
            font: { size: 10, color: '#8A9AAD' }
        })));
        
        const options = {
            nodes: {
                borderWidth: 2,
                shadow: true
            },
            edges: {
                width: 1,
                smooth: {
                    type: 'continuous'
                }
            },
            physics: {
                stabilization: { iterations: 100 },
                barnesHut: {
                    gravitationalConstant: -3000,
                    springLength: 150
                }
            },
            interaction: {
                hover: true,
                tooltipDelay: 200
            }
        };
        
        this.graph = new vis.Network(container, { nodes, edges }, options);
        
        // Клик на ноду - открываем детали
        this.graph.on('click', (params) => {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                this.openEntityDetail(nodeId);
            }
        });
    }
    
    getEntityColor(type) {
        const colors = {
            person: '#5B8EC2',    // Синий
            company: '#6B5B95',   // Фиолетовый
            project: '#7BC96F'    // Зеленый
        };
        return colors[type] || '#5BA8A8'; // Бирюзовый по умолчанию
    }
    
    zoomGraph(direction) {
        if (!this.graph) return;
        const scale = this.graph.getScale();
        const newScale = direction === 'in' ? scale * 1.2 : scale / 1.2;
        this.graph.moveTo({ scale: newScale });
    }
    
    fitGraph() {
        if (!this.graph) return;
        this.graph.fit({ animation: true });
    }
    
    // === Entities ===
    
    openEntityDetail(entityId) {
        htmx.ajax('GET', `/crm/partials/entity-modal/${entityId}`, {
            target: '#modal-container',
            swap: 'innerHTML'
        });
    }
    
    // === Modal ===
    
    closeModal() {
        const modal = document.querySelector('.crm-modal-overlay');
        if (modal) {
            modal.remove();
        }
    }
    
    // === Notifications ===
    
    showNotification(message, type = 'info') {
        // Используем глобальную систему уведомлений если есть
        if (window.app && window.app.notification) {
            window.app.notification.show(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }
    
    // === AI Assistant ===
    
    askAI() {
        // Открываем чат с CRM агентом
        if (window.app && window.app.chat) {
            // CRM использует специальный flow для AI помощника
            window.app.chat.open({
                agent_id: 'crm_assistant',
                session_id: null,
                title: 'CRM AI Помощник'
            });
        } else {
            // Fallback: показываем чат виджет
            const chatWidget = document.getElementById('chat-widget');
            if (chatWidget) {
                chatWidget.classList.remove('hidden');
                chatWidget.classList.add('open');
            } else {
                this.showNotification('AI помощник временно недоступен', 'warning');
            }
        }
    }
}

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', () => {
    window.crmModule = new CRMModule();
});

// Глобальные функции для использования в HTML
window.CRM = {
    analyzeNote: (noteId) => window.crmModule?.analyzeNote(noteId),
    zoomGraph: (dir) => window.crmModule?.zoomGraph(dir),
    fitGraph: () => window.crmModule?.fitGraph(),
    closeModal: () => window.crmModule?.closeModal(),
    openEntity: (id) => window.crmModule?.openEntityDetail(id),
    toggleVoice: () => window.crmModule?.toggleVoiceInput(),
    askAI: () => window.crmModule?.askAI(),
    showNotification: (msg, type) => window.crmModule?.showNotification(msg, type),
    
    // Sidebar settings
    saveSidebarSettings: async () => {
        const items = [];
        const settingsContainer = document.getElementById('sidebar-settings');
        if (!settingsContainer) return;
        
        settingsContainer.querySelectorAll('.crm-sidebar-setting-item').forEach((item, index) => {
            const checkbox = item.querySelector('.sidebar-visibility-toggle');
            items.push({
                id: checkbox.dataset.itemId,
                visible: checkbox.checked,
                order: index
            });
        });
        
        try {
            const response = await fetch('/crm/api/v1/profile/sidebar', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ items })
            });
            
            if (response.ok) {
                window.crmModule?.showNotification('Настройки меню сохранены', 'success');
                // Перезагружаем sidebar
                window.location.reload();
            } else {
                throw new Error('Ошибка сохранения');
            }
        } catch (e) {
            window.crmModule?.showNotification('Ошибка сохранения настроек', 'error');
        }
    },
    
    // Widget settings
    saveWidgetSettings: async () => {
        const enabledWidgets = [];
        document.querySelectorAll('.widget-visibility-toggle:checked').forEach(checkbox => {
            enabledWidgets.push(checkbox.dataset.widgetId);
        });
        
        try {
            const response = await fetch('/crm/api/v1/profile/widgets', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    enabled_widgets: enabledWidgets,
                    layout: {}
                })
            });
            
            if (response.ok) {
                window.crmModule?.showNotification('Настройки виджетов сохранены', 'success');
            } else {
                throw new Error('Ошибка сохранения');
            }
        } catch (e) {
            window.crmModule?.showNotification('Ошибка сохранения настроек', 'error');
        }
    }
};

