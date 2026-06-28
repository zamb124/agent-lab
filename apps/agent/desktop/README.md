# HumanitecAgent Desktop (Goose custom distro)

Брендированная сборка [Goose](https://github.com/block/goose) для Windows, macOS и Linux.

## Структура

- `distro/humanitec.json` — контракт брендинга и bundled extensions
- `build_contract.py` — имена артефактов и префиксы GitHub Release assets
- `vendor/goose/` — git submodule Goose (pin: `4f7bf8c1e281863932b42b65577b4d7be04214b0`)
- `scripts/build.sh` — сборка одной платформы (`placeholder` или `release`)
- `scripts/apply_branding.sh` — патч Goose desktop + `humanitec.defaults.json`
- `branding/icons/` — иконки HumanitecAgent
- `dist/` — выходные установщики

## Release workflow (prod)

Сборка HumanitecAgent — **только вручную** через GitHub Actions → **humanitec-agent-build** → `workflow_dispatch`.

| Инвариант | Значение |
|---|---|
| Триггер | `workflow_dispatch` (Deploy не запускает сборку) |
| Release tag | `humanitec-agent-{short_sha}` или явный `release_tag` |
| `releases/latest` | `make_latest: true` на каждой публикации |
| Release с таким tag уже есть | skip matrix; `force_rebuild=true` для пересборки |

Параметры `workflow_dispatch`: `release_tag` (опционально), `artifact_mode`, `publish_draft`, `force_rebuild`.

### Локально (dev/smoke)

```bash
make agent-release AGENT_RELEASE_TAG=humanitec-agent-v0.2.0 AGENT_VERSION_SHA=$(git rev-parse HEAD)
make agent-release-placeholder AGENT_RELEASE_TAG=humanitec-agent-v0.2.0-dev
make agent-ensure AGENT_ARTIFACT_MODE=placeholder
```

## Локальный профиль (dev = test stack на lvh.me)

Без `conf.local.json` desktop и browser pairing идут на prod (`https://humanitec.ru`).

Для локальной разработки скопируйте `conf.local.json.example` → `conf.local.json`:

```json
{
  "server": {
    "platform_public_base_url": "http://system.lvh.me:8002"
  }
}
```

| Режим | `platform_public_base_url` | Frontend | Flows |
|-------|---------------------------|----------|-------|
| Dev (`make app`) | `http://system.lvh.me:8002` | `:8002` | `:8001` |
| Test (`make test-up`) | `http://system.lvh.me:9004` | `:9004` | `:9001` |

Pairing: `http://system.lvh.me:8002/settings` → HumanitecAgent (компания `system`).  
Register возвращает URL bundle; компания берётся из pairing, не из Host desktop.

Desktop dev override: `HUMANITEC_FRONTEND_BASE_URL=http://system.lvh.me:8002`.

## Toolchain

- Node.js **22** LTS (CI; Node 24 ломает extract-zip/electron postinstall)
- pnpm **>= 10.30**
- Rust stable (goosed)
- macOS x64: `bundle:intel` + `ELECTRON_ARCH=x64`

## Code signing (CI secrets)

Передаются в matrix job [`humanitec-agent-build.yml`](../../../.github/workflows/humanitec-agent-build.yml).  
Подробный чеклист: [`docs/MACOS_SIGNING.md`](docs/MACOS_SIGNING.md).

| Secret | Назначение |
|--------|------------|
| `APPLE_ID` | Apple ID для notarization |
| `APPLE_ID_PASSWORD` | App-specific password (не пароль Apple ID, не `.p8`) |
| `APPLE_TEAM_ID` | Team ID (`MLL2V8KTV4` — тот же, что mobile/iOS) |
| `MACOS_CERTIFICATE_P12_BASE64` | Developer ID Application `.p12` (base64) |
| `MACOS_CERTIFICATE_PASSWORD` | Пароль экспорта `.p12` |
| `WINDOWS_CERTIFICATE_FILE` | Authenticode cert |
| `WINDOWS_CERTIFICATE_PASSWORD` | cert password |

**Не путать с mobile:** `AUTH_APPLE_PRIVATE_KEY` (.p8) — Sign in with Apple OAuth, не codesign desktop.

Goose [`forge.config.ts`](vendor/goose/ui/desktop/forge.config.ts) активирует `osxSign`/`osxNotarize` только когда CI импортировал `.p12` и выставил `APPLE_TEAM_ID` в env job (см. step Import macOS signing certificate). Без секретов macOS собирается **unsigned**.

`KEYCHAIN_PATH` создаётся на раннере в `$RUNNER_TEMP/signing.keychain-db`, не хранится в GitHub Secrets.

## Download API

`GET /frontend/api/agent/download/{platform}` → redirect на asset из `releases/latest`.

Конфиг:

```json
{
  "agent": {
    "releases": {
      "github_owner": "zamb124",
      "github_repo": "agent-lab"
    }
  }
}
```

Проверка:

```bash
curl -I https://<host>/frontend/api/agent/download/macos-arm64
curl https://<host>/frontend/api/agent/releases/status
```

## Имена артефактов

Единый источник — `build_contract.py`:

| platform | prefix / pattern |
|----------|------------------|
| windows | `HumanitecAgent-Setup-` |
| macos-arm64 | `HumanitecAgent-macos-arm64-` |
| macos-x64 | `HumanitecAgent-macos-x64-` |
| linux-deb | `humanitec-agent_` |
| linux-rpm | `humanitec-agent-` |
| linux-appimage | `HumanitecAgent-` (суффикс `.AppImage`) |

## Submodule pin

```bash
git submodule update --init apps/agent/desktop/vendor/goose
cd apps/agent/desktop/vendor/goose && git checkout 4f7bf8c1e281863932b42b65577b4d7be04214b0
```

Parent repo фиксирует commit submodule; floating `HEAD` без pin запрещён для release.

## Manual checklist (Goose runtime)

Сценарии D1–D15 и D-GOLD автоматизированы: `make test-agent-desktop-e2e`.  
Перед semver release дополнительно пройти вручную на real artifact:

| ID | Проверка | Как |
|----|----------|-----|
| G1 | CUSTOM_DISTROS spike | `vendor/goose` собирается после `apply_branding.sh` |
| G2 | `humanitec.defaults.json` | extensions `platform_mcp` активны после install |
| G3 | Deep links | `humanitec://auth/callback`, `humanitec://pairing` открывают приложение |
| G4 | Platform MCP | desktop → flows URL + device JWT → `tools/list` |
| G5 | fail-fast branding | `scripts/apply_branding.sh` без submodule падает с понятной ошибкой |
| G6 | Icons | иконки HumanitecAgent в `.dmg`/`.exe`/`.deb` |

CI: `test_apply_branding_script_*`, `test_distro_fields_in_release_artifact`, opt-in `@pytest.mark.agent_build_release`.
