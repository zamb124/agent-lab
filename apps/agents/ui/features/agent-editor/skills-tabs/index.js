/**
 * SkillsTabsBar - управление skills с merge логикой
 * Реализует полную логику AgentFactory._apply_skill с backend
 */
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { skillsTabsBarStyles } from './styles.js';
import { renderSkillsTabsBar } from './templates.js';
import '../../../modals/skill-create-modal.js';

export class SkillsTabsBar extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        skillsTabsBarStyles,
    ];

    static properties = {
        agentConfig: { type: Object },
        currentSkillId: { type: String },
    };

    constructor() {
        super();
        this.agentConfig = null;
        this.currentSkillId = null;
        this.activeSkill = 'base';
        this.skills = [];
        this._baseData = { nodes: {}, edges: [], entry: null, variables: {} };
        this._skillsData = new Map();
        this._initialized = false;
    }

    willUpdate(changedProperties) {
        const agentConfigChanged = changedProperties.has('agentConfig') && this.agentConfig;
        const currentSkillIdChanged = changedProperties.has('currentSkillId');
        
        if (agentConfigChanged) {
            this._initSkills(this.agentConfig);
            this._initialized = true;
            
            // Если currentSkillId тоже изменился в этом же цикле - уже обработано в _initSkills
            // Больше ничего не делаем
            return;
        }
        
        // Если изменился только currentSkillId (без agentConfig) - переключаемся
        if (currentSkillIdChanged && this._initialized && this.currentSkillId) {
            this._switchSkill(this.currentSkillId, { force: true });
        }
    }

    render() {
        return renderSkillsTabsBar(this);
    }

    _initSkills(agent) {
        this._baseData = {
            nodes: agent.nodes || {},
            edges: agent.edges || [],
            entry: agent.entry || null,
            variables: this._extractVariableValues(agent.variables || {}),
        };

        this._skillsData.clear();

        if (agent.skills) {
            for (const [skillId, skill] of Object.entries(agent.skills)) {
                console.log(`[SkillsTabsBar] Init skill "${skillId}":`, {
                    nodes_mode: skill.nodes_mode,
                    edges_mode: skill.edges_mode,
                    nodes_count: skill.nodes ? Object.keys(skill.nodes).length : 'null',
                    edges_count: skill.edges ? skill.edges.length : 'null'
                });
                
                this._skillsData.set(skillId, {
                    id: skillId,
                    name: skill.name || skillId,
                    description: skill.description || '',
                    entry: skill.entry || null,
                    nodes: skill.nodes || null,
                    edges: skill.edges || null,
                    variables: this._extractVariableValues(skill.variables || {}),
                    nodes_mode: skill.nodes_mode || 'replace',
                    edges_mode: skill.edges_mode || 'replace',
                    variables_mode: skill.variables_mode || 'merge',
                });
            }
        }

        this.skills = Array.from(this._skillsData.values());
        
        // При инициализации переключаемся на currentSkillId или 'base'
        const targetSkill = this.currentSkillId || 'base';
        console.log('[SkillsTabsBar] _initSkills, target skill:', targetSkill);
        this._switchSkill(targetSkill, { force: true });
    }

    _extractVariableValues(variables) {
        const result = {};
        for (const [key, value] of Object.entries(variables)) {
            if (value && typeof value === 'object' && 'value' in value) {
                result[key] = value.value;
            } else {
                result[key] = value;
            }
        }
        return result;
    }

    _getMergedData(skillId) {
        const skill = this._skillsData.get(skillId);
        if (!skill) {
            return {
                ...this._baseData,
                inherited: { nodeIds: new Set(), edgeKeys: new Set(), variableKeys: new Set() },
            };
        }

        console.log(`[SkillsTabsBar] Merge skill "${skillId}":`, {
            nodes_mode: skill.nodes_mode,
            edges_mode: skill.edges_mode,
            nodes_in_skill: skill.nodes ? Object.keys(skill.nodes) : null,
            edges_in_skill: skill.edges ? skill.edges.length : null,
            nodes_in_base: Object.keys(this._baseData.nodes).length,
            edges_in_base: this._baseData.edges.length
        });

        const base = this._baseData;
        const inherited = {
            nodeIds: new Set(),
            edgeKeys: new Set(),
            variableKeys: new Set(),
        };

        // Точка входа (всегда replace если указана)
        const entry = skill.entry || base.entry;

        // === NODES ===
        let nodes = {};
        if (skill.nodes === null) {
            // Skill не переопределяет ноды - берем все из base
            nodes = JSON.parse(JSON.stringify(base.nodes));
            Object.keys(nodes).forEach(id => inherited.nodeIds.add(id));
        } else if (skill.nodes_mode === 'replace') {
            // REPLACE: ТОЛЬКО ноды skill, base игнорируется
            nodes = JSON.parse(JSON.stringify(skill.nodes));
        } else {
            // MERGE: base + переопределения skill
            nodes = JSON.parse(JSON.stringify(base.nodes));
            Object.keys(nodes).forEach(id => inherited.nodeIds.add(id));

            for (const [nodeId, nodeConfig] of Object.entries(skill.nodes)) {
                if (nodeId in nodes) {
                    // Deep merge для существующей ноды
                    nodes[nodeId] = this._deepMerge(nodes[nodeId], nodeConfig);
                    inherited.nodeIds.delete(nodeId);
                } else {
                    // Новая нода
                    nodes[nodeId] = JSON.parse(JSON.stringify(nodeConfig));
                }
            }
        }

        // === EDGES ===
        let edges = [];
        if (skill.edges === null) {
            edges = JSON.parse(JSON.stringify(base.edges));
            edges.forEach(e => inherited.edgeKeys.add(this._edgeKey(e)));
        } else if (skill.edges_mode === 'replace') {
            edges = JSON.parse(JSON.stringify(skill.edges));
            
            // ВАЖНО: автоматически наследуем ноды, на которые ссылаются edges
            const referencedNodeIds = new Set();
            edges.forEach(edge => {
                if (edge.from) referencedNodeIds.add(edge.from);
                if (edge.to) referencedNodeIds.add(edge.to);
            });
            
            // Добавляем entry тоже
            if (entry) referencedNodeIds.add(entry);
            
            // Наследуем ноды из base, если их нет в skill
            referencedNodeIds.forEach(nodeId => {
                if (!nodes[nodeId] && base.nodes[nodeId]) {
                    nodes[nodeId] = JSON.parse(JSON.stringify(base.nodes[nodeId]));
                    inherited.nodeIds.add(nodeId);
                    console.log(`[SkillsTabsBar] Auto-inheriting node "${nodeId}" from base (referenced by edges)`);
                }
            });
        } else {
            // MERGE: рёбра с той же парой (from, to) заменяются
            const skillEdgePairs = new Set(skill.edges.map(e => `${e.from}→${e.to}`));
            
            const baseEdgesFiltered = base.edges.filter(e => 
                !skillEdgePairs.has(`${e.from}→${e.to}`)
            );
            
            console.log(`[SkillsTabsBar] EDGES MERGE for "${skillId}":`, {
                base_edges_count: base.edges.length,
                base_edges: base.edges.map(e => `${e.from}→${e.to}`),
                skill_edge_pairs: Array.from(skillEdgePairs),
                base_edges_filtered: baseEdgesFiltered.map(e => `${e.from}→${e.to}`),
                skill_edges: skill.edges.map(e => `${e.from}→${e.to}`),
            });
            
            edges = baseEdgesFiltered.map(e => {
                const copy = JSON.parse(JSON.stringify(e));
                inherited.edgeKeys.add(this._edgeKey(copy));
                return copy;
            });
            
            edges.push(...JSON.parse(JSON.stringify(skill.edges)));
        }

        // === VARIABLES ===
        let variables = {};
        if (skill.variables_mode === 'replace') {
            // REPLACE: ТОЛЬКО переменные skill
            variables = JSON.parse(JSON.stringify(skill.variables || {}));
        } else {
            // MERGE: base + переопределения skill
            variables = JSON.parse(JSON.stringify(base.variables || {}));
            Object.keys(variables).forEach(key => inherited.variableKeys.add(key));

            for (const [key, value] of Object.entries(skill.variables || {})) {
                if (key in variables) {
                    inherited.variableKeys.delete(key);
                }
                variables[key] = JSON.parse(JSON.stringify(value));
            }
        }

        return { nodes, edges, entry, variables, inherited };
    }

    _deepMerge(base, override) {
        const result = JSON.parse(JSON.stringify(base));
        for (const [key, value] of Object.entries(override)) {
            if (value && typeof value === 'object' && !Array.isArray(value) &&
                result[key] && typeof result[key] === 'object' && !Array.isArray(result[key])) {
                result[key] = this._deepMerge(result[key], value);
            } else {
                result[key] = JSON.parse(JSON.stringify(value));
            }
        }
        return result;
    }

    _edgeKey(edge) {
        return `${edge.from}:${edge.to}:${edge.condition || ''}`;
    }

    _computeDiff(canvasData) {
        const base = this._baseData;
        let diffNodes = null;
        let diffEdges = null;
        let diffEntry = null;

        if (canvasData.entry !== base.entry) {
            diffEntry = canvasData.entry;
        }

        const changedNodes = {};
        for (const [nodeId, nodeConfig] of Object.entries(canvasData.nodes)) {
            const baseNode = base.nodes[nodeId];
            if (!baseNode || !this._isEqual(nodeConfig, baseNode)) {
                changedNodes[nodeId] = nodeConfig;
            }
        }

        if (Object.keys(changedNodes).length > 0) {
            diffNodes = changedNodes;
        }

        const baseEdgeKeys = new Set(base.edges.map(e => this._edgeKey(e)));
        const canvasEdgeKeys = new Set(canvasData.edges.map(e => this._edgeKey(e)));

        const hasEdgeChanges =
            canvasData.edges.length !== base.edges.length ||
            ![...canvasEdgeKeys].every(k => baseEdgeKeys.has(k));

        if (hasEdgeChanges) {
            diffEdges = canvasData.edges;
        }

        return {
            nodes: diffNodes,
            edges: diffEdges,
            entry: diffEntry,
        };
    }

    _isEqual(a, b) {
        return JSON.stringify(a) === JSON.stringify(b);
    }

    _switchSkill(skillId, options = {}) {
        const { force = false } = options;
        
        // Если skill не изменился и не force режим - пропускаем
        if (skillId === this.activeSkill && !force) {
            console.log(`[SkillsTabsBar] Skipping switch - already on skill "${skillId}"`);
            return;
        }

        // Сохраняем данные текущего skill перед переключением (только если не force)
        if (!force) {
        this.emit('save-current-skill-data', { skillId: this.activeSkill });
        }

        this.activeSkill = skillId;
        let data;
        let inherited = { nodeIds: new Set(), edgeKeys: new Set(), variableKeys: new Set() };

        if (skillId === 'base') {
            data = this._baseData;
        } else {
            const merged = this._getMergedData(skillId);
            data = {
                nodes: merged.nodes,
                edges: merged.edges,
                entry: merged.entry,
                variables: merged.variables,
            };
            inherited = merged.inherited;
        }

        console.log(`[SkillsTabsBar] Switching to skill "${skillId}" (force=${force}):`, {
            nodes_count: Object.keys(data.nodes || {}).length,
            edges_count: (data.edges || []).length,
            edges: data.edges,
            variables_keys: Object.keys(data.variables || {}),
            inherited_nodes: Array.from(inherited.nodeIds),
            inherited_edges: Array.from(inherited.edgeKeys),
            inherited_vars: Array.from(inherited.variableKeys),
        });

        this.emit('skill-switched', { skillId, data, inherited });
        this.requestUpdate('skills');
    }

    _showNewSkillDialog() {
        let modal = document.querySelector('skill-create-modal');
        if (!modal) {
            modal = document.createElement('skill-create-modal');
            document.body.appendChild(modal);
        }

        modal.addEventListener('skill-create', (e) => {
            const { skillId, name, initType, copyFromSkillId } = e.detail;
            
            if (this._skillsData.has(skillId)) {
                this.notify.error(`Skill "${skillId}" уже существует`);
                return;
            }

            this._createSkill(skillId, name, '', initType, copyFromSkillId);
        }, { once: true });

        modal.showModal(this.activeSkill);
    }

    _createSkill(skillId, name, description, initType, copyFromSkillId = null) {
        let sourceData = this._baseData;
        
        if (initType === 'copy' && copyFromSkillId && copyFromSkillId !== 'base') {
            const sourceSkill = this._skillsData.get(copyFromSkillId);
            if (sourceSkill) {
                const mergedData = this._computeMergedData(sourceSkill);
                sourceData = {
                    nodes: mergedData.nodes,
                    edges: mergedData.edges,
                    entry: mergedData.entry,
                    variables: mergedData.variables,
                };
            }
        }
        
        const newSkill = {
            id: skillId,
            name,
            description,
            entry: initType === 'copy' ? sourceData.entry : null,
            nodes: initType === 'copy' ? JSON.parse(JSON.stringify(sourceData.nodes)) : null,
            edges: initType === 'copy' ? JSON.parse(JSON.stringify(sourceData.edges)) : null,
            variables: {},
            nodes_mode: 'replace',
            edges_mode: 'replace',
            variables_mode: 'merge',
        };

        this._skillsData.set(skillId, newSkill);
        this.skills = Array.from(this._skillsData.values());
        this.notify.success(`Skill "${name}" создан`);
        this._switchSkill(skillId);
    }

    _deleteSkill(skillId) {
        if (!confirm(`Удалить skill "${this._skillsData.get(skillId)?.name}"?`)) return;

        this._skillsData.delete(skillId);
        this.skills = Array.from(this._skillsData.values());
        this.notify.success('Skill удален');

        if (this.activeSkill === skillId) {
            this._switchSkill('base');
        } else {
            this.requestUpdate('skills');
        }
    }

    updateSkillData(skillId, canvasData) {
        if (skillId === 'base') {
            this._baseData = {
                nodes: canvasData.nodes,
                edges: canvasData.edges,
                entry: canvasData.entry,
                variables: this._baseData.variables,
            };
        } else {
            const skill = this._skillsData.get(skillId);
            if (skill) {
                const diff = this._computeDiff(canvasData);
                skill.nodes = diff.nodes;
                skill.edges = diff.edges;
                skill.entry = diff.entry;
            }
        }
    }

    updateSkillVariables(skillId, variables) {
        if (skillId === 'base') {
            this._baseData.variables = variables;
        } else {
            const skill = this._skillsData.get(skillId);
            if (skill) {
                skill.variables = variables;
            }
        }
    }

    getSkillsForSubmit() {
        const skills = {};
        for (const [skillId, skill] of this._skillsData.entries()) {
            skills[skillId] = {
                name: skill.name,
                description: skill.description,
                entry: skill.entry,
                nodes: skill.nodes,
                edges: skill.edges,
                variables: skill.variables,
                nodes_mode: skill.nodes_mode,
                edges_mode: skill.edges_mode,
                variables_mode: skill.variables_mode,
            };
        }
        return skills;
    }

    getActiveSkillData() {
        if (this.activeSkill === 'base') {
            return this._baseData;
        }
        return this._getMergedData(this.activeSkill);
    }
}

customElements.define('skills-tabs-bar', SkillsTabsBar);
