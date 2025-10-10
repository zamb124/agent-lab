"""
Генерирует .env.sgr из conf.json для SGR сервиса.
"""

import json

with open('conf.json', 'r') as f:
    config = json.load(f)

sgr_config = config.get('sgr', {})

if not sgr_config:
    raise ValueError("Секция 'sgr' не найдена в conf.json")

openai_key = sgr_config.get('openai_api_key', '')
tavily_key = sgr_config.get('tavily_api_key', '')

if not openai_key:
    raise ValueError("sgr.openai_api_key не найден в conf.json")

if not tavily_key:
    raise ValueError("sgr.tavily_api_key не найден в conf.json")

# Генерируем .env.sgr
env_content = f"""# Auto-generated from conf.json
OPENAI_API_KEY={openai_key}
TAVILY_API_KEY={tavily_key}
"""

with open('.env.sgr', 'w') as f:
    f.write(env_content)

print("✅ .env.sgr создан из conf.json")
print(f"   OpenAI key: {openai_key[:20]}...")
print(f"   Tavily key: {tavily_key[:20]}...")

