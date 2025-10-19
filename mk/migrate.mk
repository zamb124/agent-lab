.PHONY: remigrate

remigrate:
	@if [ -z "$(COMPANY)" ]; then \
		echo "❌ Укажите COMPANY=<company_id>"; \
		echo "Пример: make remigrate COMPANY=system"; \
		exit 1; \
	fi
	@echo "🔄 Перемиграция компании $(COMPANY)..."
	uv run python remigrate_company.py $(COMPANY)

