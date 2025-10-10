#!/bin/bash
set -e

echo "🔧 Генерация config.yaml для SGR..."

# Проверяем переменные окружения
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Ошибка: OPENAI_API_KEY не установлен"
    exit 1
fi

if [ -z "$TAVILY_API_KEY" ]; then
    echo "❌ Ошибка: TAVILY_API_KEY не установлен"
    exit 1
fi

# Создаем config.yaml
python3 << 'PYTHON_SCRIPT'
import os

openai_key = os.environ.get('OPENAI_API_KEY')
tavily_key = os.environ.get('TAVILY_API_KEY')

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

