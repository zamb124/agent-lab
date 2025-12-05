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
        console.log('🔷 CRM Module initialized');
        this.setupEventListeners();
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
    openEntity: (id) => window.crmModule?.openEntityDetail(id)
};

