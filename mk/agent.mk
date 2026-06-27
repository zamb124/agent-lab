.PHONY: agent agent-ensure agent-submodule agent-build agent-build-all agent-verify-local agent-publish agent-ci-build agent-release agent-release-placeholder

AGENT_PLATFORMS := windows macos-arm64 macos-x64 linux-deb linux-rpm linux-appimage
AGENT_ARTIFACT_MODE ?= placeholder
AGENT_VERSION_SHA ?= $(shell git rev-parse HEAD 2>/dev/null || echo local)
AGENT_RELEASE_TAG ?= humanitec-agent-v0.2.0

agent-submodule:
	@git submodule update --init apps/agent/desktop/vendor/goose

agent-ensure: runtime-bootstrap
	@chmod +x apps/agent/desktop/scripts/build.sh apps/agent/desktop/scripts/apply_branding.sh
	@uv run python scripts/agent_build.py ensure-local \
		--artifact-mode $(AGENT_ARTIFACT_MODE) \
		--version-sha $(AGENT_VERSION_SHA)

agent-build: agent-submodule
	@chmod +x apps/agent/desktop/scripts/build.sh apps/agent/desktop/scripts/apply_branding.sh
	@if [ -z "$(AGENT_PLATFORM)" ]; then \
		echo "AGENT_PLATFORM is required (e.g. macos-arm64, linux-deb)"; \
		exit 1; \
	fi
	@uv run python scripts/agent_build.py build \
		--platform $(AGENT_PLATFORM) \
		--artifact-mode $(AGENT_ARTIFACT_MODE) \
		--version-sha $(AGENT_VERSION_SHA)

agent-build-all: agent-submodule
	@chmod +x apps/agent/desktop/scripts/build.sh
	@uv run python scripts/agent_build.py build-all \
		--artifact-mode $(AGENT_ARTIFACT_MODE) \
		--version-sha $(AGENT_VERSION_SHA)

# Локальная копия CI matrix: build + verify_agent_artifact для всех 6 платформ
agent-verify-local: runtime-bootstrap agent-submodule
	@chmod +x apps/agent/desktop/scripts/build.sh apps/agent/desktop/scripts/apply_branding.sh
	@test -f apps/agent/desktop/distro/humanitec.json
	@uv run python scripts/agent_build.py verify-ci-local \
		--artifact-mode $(AGENT_ARTIFACT_MODE) \
		--version-sha $(AGENT_VERSION_SHA)

agent-publish:
	@uv run python scripts/agent_build.py publish-release \
		--tag $(AGENT_RELEASE_TAG) \
		--version-sha $(AGENT_VERSION_SHA)

agent-ci-build: agent-submodule
	@chmod +x apps/agent/desktop/scripts/build.sh apps/agent/desktop/scripts/apply_branding.sh
	@if [ -z "$(AGENT_PLATFORM)" ]; then \
		echo "AGENT_PLATFORM is required for agent-ci-build"; \
		exit 1; \
	fi
	@uv run python scripts/agent_build.py build \
		--platform $(AGENT_PLATFORM) \
		--artifact-mode $(AGENT_ARTIFACT_MODE) \
		--version-sha $(AGENT_VERSION_SHA)

# Release: real Goose installers + GitHub Release (semver tag вручную или workflow_dispatch)
agent-release:
	@$(MAKE) agent-build-all AGENT_ARTIFACT_MODE=release AGENT_VERSION_SHA=$(AGENT_VERSION_SHA)
	@$(MAKE) agent-publish AGENT_VERSION_SHA=$(AGENT_VERSION_SHA) AGENT_RELEASE_TAG=$(AGENT_RELEASE_TAG)

# Локальный placeholder для dev/test
agent-release-placeholder:
	@$(MAKE) agent-build-all AGENT_ARTIFACT_MODE=placeholder AGENT_VERSION_SHA=$(AGENT_VERSION_SHA)
	@$(MAKE) agent-publish AGENT_VERSION_SHA=$(AGENT_VERSION_SHA) AGENT_RELEASE_TAG=$(AGENT_RELEASE_TAG)

agent: agent-release

.PHONY: test-agent test-agent-e2e test-agent-desktop-e2e test-agent-ui-e2e test-agent-mcp-flows-e2e test-agent-desktop-mcp-ui-e2e test-agent-goose-one test-agent-goose-extensions test-agent-desktop-full

test-agent-goose-one:
	@test -n "$(TEST)" || (echo "TEST is required, e.g. TEST=tests/agent/desktop_e2e/test_agent_desktop_goose_extensions.py::test_goose_dev_01_list_directory" >&2; exit 1)
	uv run pytest $(TEST) -n0 -v --timeout=900

test-agent-goose-extensions: test-up
	uv run python scripts/check_agent_e2e_coverage.py
	uv run python scripts/check_agent_goose_tool_contract.py
	AGENT_ARTIFACT_MODE=release uv run python scripts/agent_build.py ensure-local --artifact-mode release --version-sha "$$(git rev-parse HEAD)"
	RUN_UI_IN_TEST=1 UI_E2E_USE_LVH_ME=1 uv run pytest tests/agent/desktop_e2e/test_agent_desktop_goose_extensions.py tests/agent/desktop_e2e/test_agent_desktop_goose_cc_av_tut.py tests/agent/desktop_e2e/test_agent_desktop_goose_platform_ext.py tests/agent/desktop_e2e/test_agent_desktop_goosed_config.py -n0 --timeout=900

test-agent-desktop-full: test-up
	uv run python scripts/check_agent_e2e_coverage.py
	uv run python scripts/check_agent_goose_tool_contract.py
	AGENT_ARTIFACT_MODE=release uv run python scripts/agent_build.py ensure-local --artifact-mode release --version-sha "$$(git rev-parse HEAD)"
	RUN_UI_IN_TEST=1 UI_E2E_USE_LVH_ME=1 uv run pytest tests/agent/desktop_e2e tests/ui/e2e/test_frontend_settings_agent.py -n0 --timeout=900

test-agent: test-up
	uv run python scripts/check_agent_e2e_coverage.py
	uv run python scripts/check_agent_goose_tool_contract.py
	uv run python scripts/check_agent_test_no_monkeypatch.py
	AGENT_ARTIFACT_MODE=release uv run python scripts/agent_build.py ensure-local --artifact-mode release --version-sha "$$(git rev-parse HEAD)"
	RUN_UI_IN_TEST=1 UI_E2E_USE_LVH_ME=1 uv run pytest tests/agent tests/frontend/api/test_humanitec_agent_api.py tests/flows/api/test_agent_platform_mcp.py tests/ui/e2e/test_frontend_settings_agent.py -v -n0 --timeout=900

test-agent-e2e: test-up
	uv run pytest tests/agent/e2e -v -n0 --timeout=180

test-agent-desktop-e2e: test-up
	uv run python scripts/check_agent_e2e_coverage.py
	uv run python scripts/check_agent_goose_tool_contract.py
	AGENT_ARTIFACT_MODE=release uv run python scripts/agent_build.py ensure-local --artifact-mode release --version-sha "$$(git rev-parse HEAD)"
	RUN_UI_IN_TEST=1 UI_E2E_USE_LVH_ME=1 uv run pytest tests/agent/desktop_e2e tests/ui/e2e/test_frontend_settings_agent.py -v -n0 --timeout=900

test-agent-ui-e2e: test-up
	UI_E2E_USE_LVH_ME=1 RUN_UI_IN_TEST=1 uv run pytest tests/ui/e2e/test_frontend_settings_agent.py -n0 --timeout=300

test-agent-mcp-flows-e2e: test-up
	uv run pytest tests/agent/e2e/test_agent_platform_mcp_flows_e2e.py tests/agent/e2e/test_agent_platform_mcp_impossible_e2e.py -v -n0 --timeout=180

test-agent-desktop-mcp-ui-e2e: test-up
	uv run python scripts/check_agent_e2e_coverage.py
	uv run python scripts/check_agent_goose_tool_contract.py
	AGENT_ARTIFACT_MODE=release uv run python scripts/agent_build.py ensure-local --artifact-mode release --version-sha "$$(git rev-parse HEAD)"
	RUN_UI_IN_TEST=1 UI_E2E_USE_LVH_ME=1 uv run pytest tests/agent/desktop_e2e/test_agent_desktop_mcp_ui.py tests/agent/desktop_e2e/test_agent_desktop_mcp_flows.py -v -n0 --timeout=900
