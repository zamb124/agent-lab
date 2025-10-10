#!/bin/bash
set -e

echo "🔧 Генерация config.yaml для SGR из conf.json..."

# Проверяем наличие conf.json
if [ ! -f "/app/conf.json" ]; then
    echo "❌ Ошибка: /app/conf.json не найден"
    exit 1
fi

# Создаем config.yaml из conf.json
python3 << 'PYTHON_SCRIPT'
import json

# Читаем conf.json
with open('/app/conf.json', 'r') as f:
    config = json.load(f)

sgr_config = config.get('sgr', {})

if not sgr_config:
    print("❌ Ошибка: секция 'sgr' не найдена в conf.json")
    exit(1)

openai_key = sgr_config.get('openai_api_key', '')
tavily_key = sgr_config.get('tavily_api_key', '')

if not openai_key:
    print("❌ Ошибка: sgr.openai_api_key не найден в conf.json")
    exit(1)

if not tavily_key:
    print("❌ Ошибка: sgr.tavily_api_key не найден в conf.json")
    exit(1)

# Создаем config.yaml для SGR
config_yaml = f"""# Auto-generated from conf.json
openai:
  api_key: "{openai_key}"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o-mini"
  max_tokens: 8000
  temperature: 0.4
  proxy: ""

tavily:
  api_key: "{tavily_key}"
  api_base_url: "https://api.tavily.com"

search:
  max_results: 10

scraping:
  enabled: false
  max_pages: 5
  content_limit: 1500

execution:
  max_steps: 6
  reports_dir: "reports"
  logs_dir: "logs"

prompts:
  prompts_dir: "prompts"
  tool_function_prompt_file: "tool_function_prompt.txt"
  system_prompt_file: "system_prompt.txt"
"""

with open('/app/config.yaml', 'w') as f:
    f.write(config_yaml)

print(f"✅ config.yaml создан")
print(f"   OpenAI key: {openai_key[:20]}...")
print(f"   Tavily key: {tavily_key[:20]}...")
PYTHON_SCRIPT

echo "🚀 Запуск SGR Deep Research..."
exec python -m sgr_deep_research --host 0.0.0.0 --port 8010

