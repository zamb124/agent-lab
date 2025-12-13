"""
Figma Design Agent - создает интерфейсы в Figma на основе требований пользователя.
"""

from app.agents.react_agent import ReActAgent
from app.tools.misc.standard import ask_user
from app.agents.figma_designer.prompts import FIGMA_DESIGN_PROMPT


class FigmaDesignAgent(ReActAgent):
    """Агент для создания дизайнов в Figma на основе требований пользователя"""

    name = "figma_design_agent"
    title = "Figma Дизайнер"
    description = "Создает интерфейсы в Figma на основе требований, используя компонентную систему Туту.ру"
    is_public = True

    llm_config = {
        "model": "google/gemini-2.5-pro",
        "temperature": 0.3,
        "context_window": 32000,
    }


    prompt = FIGMA_DESIGN_PROMPT

    tools = [
        ask_user,
        # MCP тулы из cursor-talk-to-figma-mcp (добавляются после синхронизации)
        "mcp:figma_designer:register_figma_session",
        "mcp:figma_designer:get_document_info",
        "mcp:figma_designer:get_selection",
        "mcp:figma_designer:read_my_design",
        "mcp:figma_designer:get_node_info",
        "mcp:figma_designer:get_nodes_info",
        "mcp:figma_designer:create_rectangle",
        "mcp:figma_designer:create_frame",
        "mcp:figma_designer:create_text",
        "mcp:figma_designer:set_fill_color",
        "mcp:figma_designer:set_stroke_color",
        "mcp:figma_designer:move_node",
        "mcp:figma_designer:resize_node",
        "mcp:figma_designer:delete_node",
        "mcp:figma_designer:delete_multiple_nodes",
        "mcp:figma_designer:export_node_as_image",
        "mcp:figma_designer:set_text_content",
        "mcp:figma_designer:get_styles",
        "mcp:figma_designer:get_local_components",
        "mcp:figma_designer:create_component_instance",
        "mcp:figma_designer:get_annotations",
        "mcp:figma_designer:set_annotation",
        "mcp:figma_designer:set_multiple_annotations",
        "mcp:figma_designer:get_instance_overrides",
        "mcp:figma_designer:set_instance_overrides",
        "mcp:figma_designer:set_corner_radius",
        "mcp:figma_designer:clone_node",
        "mcp:figma_designer:scan_text_nodes",
        "mcp:figma_designer:set_multiple_text_contents",
        "mcp:figma_designer:scan_nodes_by_types",
        "mcp:figma_designer:set_layout_mode",
        "mcp:figma_designer:set_padding",
        "mcp:figma_designer:set_axis_align",
        "mcp:figma_designer:set_layout_sizing",
        "mcp:figma_designer:set_item_spacing",
        "mcp:figma_designer:get_reactions",
        "mcp:figma_designer:set_default_connector",
        "mcp:figma_designer:create_connections",
        "mcp:figma_designer:set_focus",
        "mcp:figma_designer:set_selections",
        # Сессионные тулы для хранения состояния
        "app.tools.session.session_tools.session_set",
        "app.tools.session.session_tools.session_get",
    ]

