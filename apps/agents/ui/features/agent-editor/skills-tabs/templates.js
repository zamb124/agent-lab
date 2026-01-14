import { html } from 'lit';

export function renderSkillsTabsBar(component) {
    return html`
        <div class="skills-tabs-bar">
            <div class="skills-tabs">
                <button
                    class="skill-tab ${component.activeSkill === 'base' ? 'active' : ''}"
                    @click=${() => component._switchSkill('base')}
                >
                    Base Flow
                </button>
                
                ${component.skills.map(skill => html`
                    <button
                        class="skill-tab ${component.activeSkill === skill.id ? 'active' : ''}"
                        @click=${(e) => {
                            if (!e.target.classList.contains('skill-close-btn')) {
                                component._switchSkill(skill.id);
                            }
                        }}
                    >
                        ${skill.name}
                        <button
                            class="skill-close-btn"
                            title="Удалить скилл"
                            @click=${(e) => {
                                e.stopPropagation();
                                component._deleteSkill(skill.id);
                            }}
                        >
                            &times;
                        </button>
                    </button>
                `)}
            </div>
            
            <button class="add-skill-btn" @click=${component._showNewSkillDialog}>
                <platform-icon name="plus" size="14"></platform-icon>
                Skill
            </button>
        </div>
    `;
}
