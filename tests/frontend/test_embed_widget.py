"""
Frontend тесты для встраиваемого виджета чата.

Playwright тесты проверяют работу виджета в браузере.
"""

import pytest
from playwright.async_api import Page, expect


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_widget_loads(page: Page):
    """Тест что виджет загружается и отображается"""
    
    # Создаем тестовую HTML страницу с виджетом
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Widget Test</title>
    </head>
    <body>
        <h1>Test Page</h1>
        <script src="/static/core/embed/chat-widget.js"></script>
        <script>
            // Инициализируем виджет после загрузки
            window.addEventListener('DOMContentLoaded', () => {
                new HumanitecChat({
                    embedId: 'test_embed_123',
                    baseUrl: window.location.origin
                });
            });
        </script>
    </body>
    </html>
    """
    
    # Загружаем страницу
    await page.set_content(html_content)
    
    # Ждем появления виджета
    toggle_button = await page.wait_for_selector('#hc-toggle', timeout=5000)
    
    # Проверяем что кнопка видима
    await expect(toggle_button).to_be_visible()


@pytest.mark.asyncio
@pytest.mark.playwright  
async def test_widget_opens_and_closes(page: Page):
    """Тест открытия и закрытия виджета"""
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Widget Test</title>
    </head>
    <body>
        <script src="/static/core/embed/chat-widget.js"></script>
        <script>
            window.addEventListener('DOMContentLoaded', () => {
                new HumanitecChat({
                    embedId: 'test_embed_123',
                    baseUrl: window.location.origin
                });
            });
        </script>
    </body>
    </html>
    """
    
    await page.set_content(html_content)
    
    # Ждем кнопку toggle
    toggle_button = await page.wait_for_selector('#hc-toggle')
    
    # Проверяем что окно чата скрыто
    chat_window = await page.query_selector('#hc-window')
    assert chat_window is not None
    
    # Проверяем что у окна нет класса 'open'
    classes = await chat_window.get_attribute('class')
    assert 'open' not in classes
    
    # Открываем виджет
    await toggle_button.click()
    await page.wait_for_timeout(300)  # Ждем анимацию
    
    # Проверяем что окно открылось
    classes = await chat_window.get_attribute('class')
    assert 'open' in classes
    
    # Закрываем виджет
    close_button = await page.query_selector('#hc-close')
    await close_button.click()
    await page.wait_for_timeout(300)
    
    # Проверяем что окно закрылось
    classes = await chat_window.get_attribute('class')
    assert 'open' not in classes


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_widget_greeting_message(page: Page):
    """Тест отображения приветственного сообщения"""
    
    greeting = "Привет! Чем могу помочь?"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Widget Test</title>
    </head>
    <body>
        <script src="/static/core/embed/chat-widget.js"></script>
        <script>
            window.addEventListener('DOMContentLoaded', () => {{
                // Мокаем fetch для settings
                window.fetch = async (url) => {{
                    if (url.includes('/settings')) {{
                        return {{
                            ok: true,
                            json: async () => ({{
                                embed_id: 'test_embed_123',
                                agent_id: 'test_agent',
                                theme: 'dark',
                                position: 'bottom-right',
                                show_reasoning: false,
                                show_tool_calls: false,
                                primary_color: '#6366f1',
                                greeting_message: '{greeting}',
                                placeholder: 'Type here...',
                                branding: true
                            }})
                        }};
                    }}
                    return {{ ok: false }};
                }};
                
                new HumanitecChat({{
                    embedId: 'test_embed_123',
                    baseUrl: window.location.origin
                }});
            }});
        </script>
    </body>
    </html>
    """
    
    await page.set_content(html_content)
    
    # Ждем загрузки виджета
    await page.wait_for_selector('#hc-toggle')
    await page.wait_for_timeout(500)
    
    # Открываем виджет
    toggle_button = await page.query_selector('#hc-toggle')
    await toggle_button.click()
    await page.wait_for_timeout(300)
    
    # Проверяем наличие приветственного сообщения
    messages_container = await page.query_selector('#hc-messages')
    content = await messages_container.inner_text()
    
    assert greeting in content


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_widget_shadow_dom_isolation(page: Page):
    """Тест что виджет использует Shadow DOM для изоляции стилей"""
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Widget Test</title>
        <style>
            /* Стили страницы НЕ должны влиять на виджет */
            button {
                background: red !important;
                color: yellow !important;
            }
        </style>
    </head>
    <body>
        <script src="/static/core/embed/chat-widget.js"></script>
        <script>
            window.addEventListener('DOMContentLoaded', () => {
                new HumanitecChat({
                    embedId: 'test_embed_123',
                    baseUrl: window.location.origin
                });
            });
        </script>
    </body>
    </html>
    """
    
    await page.set_content(html_content)
    
    # Ждем виджет
    toggle_button = await page.wait_for_selector('#hc-toggle')
    
    # Проверяем что кнопка виджета имеет свои стили (не red от страницы)
    bg_color = await toggle_button.evaluate('(el) => window.getComputedStyle(el).backgroundColor')
    
    # Не должен быть красным (rgb(255, 0, 0))
    assert bg_color != 'rgb(255, 0, 0)'


@pytest.mark.asyncio
@pytest.mark.playwright
async def test_widget_input_placeholder(page: Page):
    """Тест placeholder в поле ввода"""
    
    placeholder_text = "Напишите ваш вопрос..."
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Widget Test</title>
    </head>
    <body>
        <script src="/static/core/embed/chat-widget.js"></script>
        <script>
            window.addEventListener('DOMContentLoaded', () => {{
                window.fetch = async (url) => {{
                    if (url.includes('/settings')) {{
                        return {{
                            ok: true,
                            json: async () => ({{
                                embed_id: 'test',
                                agent_id: 'test',
                                theme: 'dark',
                                position: 'bottom-right',
                                show_reasoning: false,
                                show_tool_calls: false,
                                primary_color: '#6366f1',
                                greeting_message: null,
                                placeholder: '{placeholder_text}',
                                branding: false
                            }})
                        }};
                    }}
                }};
                
                new HumanitecChat({{
                    embedId: 'test',
                    baseUrl: window.location.origin
                }});
            }});
        </script>
    </body>
    </html>
    """
    
    await page.set_content(html_content)
    await page.wait_for_selector('#hc-toggle')
    await page.wait_for_timeout(500)
    
    # Открываем виджет
    toggle_button = await page.query_selector('#hc-toggle')
    await toggle_button.click()
    await page.wait_for_timeout(300)
    
    # Проверяем placeholder
    input_field = await page.query_selector('#hc-input')
    placeholder = await input_field.get_attribute('placeholder')
    
    assert placeholder == placeholder_text


