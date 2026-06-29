# macOS code signing и notarization HumanitecAgent

HumanitecAgent для macOS распространяется **вне App Store** (`.dmg` с GitHub Releases).  
Нужен **Developer ID Application** + notarization. Это **не** те же артефакты, что для mobile/iOS.

## Что уже есть в платформе (mobile)

| Артефакт | Где | Назначение | Для desktop? |
|---|---|---|---|
| Team ID `MLL2V8KTV4` | `conf.json`, Xcode | Apple Developer команда | Да → `APPLE_TEAM_ID` |
| `AUTH_APPLE_PRIVATE_KEY` (.p8) | GitHub Secret | Sign in with Apple OAuth, APNs | **Нет** |
| Apple Distribution cert | Xcode / App Store | iOS App Store | **Нет** |

Подробнее про Apple portal для iOS: [`mobile/docs/APPLE_MANUAL.md`](../../../../mobile/docs/APPLE_MANUAL.md).

## 1. Developer ID Application

1. [Certificates](https://developer.apple.com/account/resources/certificates/list) → **+** → **Developer ID Application**.
2. На Mac: **Keychain Access** → Certificate Assistant → Request Certificate (CSR).
3. Загрузить CSR, скачать `.cer`, установить в keychain **login**.
4. В Keychain: сертификат **Developer ID Application** + private key → **Export** → `.p12` с паролем.

## 2. App-specific password

1. [appleid.apple.com](https://appleid.apple.com) → Sign-In and Security → **App-Specific Passwords**.
2. Label: `humanitec-agent-ci-notarize`.
3. Сохранить пароль — это `APPLE_ID_PASSWORD` (не пароль Apple ID, не `.p8`).

## 3. GitHub Secrets

Репозиторий `zamb124/agent-lab` → Settings → Secrets → Actions:

```bash
gh secret set APPLE_ID --body 'your-apple-id@example.com'
gh secret set APPLE_ID_PASSWORD --body 'xxxx-xxxx-xxxx-xxxx'
gh secret set APPLE_TEAM_ID --body 'MLL2V8KTV4'
gh secret set MACOS_CERTIFICATE_PASSWORD --body 'p12-export-password'
gh secret set MACOS_CERTIFICATE_P12_BASE64 < <(base64 -i DeveloperID.p12)
```

Все пять секретов должны быть заданы вместе. Если `MACOS_CERTIFICATE_P12_BASE64` пуст — CI собирает **unsigned** `.dmg` (job не падает).

## 4. Async notarization pipeline (CI)

Release **не ждёт Apple**. Два workflow:

| Workflow | Назначение |
|---|---|
| [`humanitec-agent-build.yml`](../../../../.github/workflows/humanitec-agent-build.yml) | Sign + DMG + `notarytool submit` (без poll) + publish всех 6 платформ |
| [`humanitec-agent-macos-notarize.yml`](../../../../.github/workflows/humanitec-agent-macos-notarize.yml) | Каждые 30 мин (до 48 ч): poll Apple → stapler → replace `.dmg` в том же release |

### Phase 1 — build (`AGENT_MACOS_NOTARIZE=submit-only`)

1. Pre-sign `goosed`, forge `osxSign`.
2. `notarytool submit` — один submit на platform на release (без blocking wait).
3. Signed `.dmg` публикуется сразу (Gatekeeper может требовать ПКМ→Открыть до notarize).
4. Internal assets в release (не попадают в download API):
   - `HumanitecAgent-macos-*-{sha}.app-bundle.zip` — тот же `.app`, что отправлен в Apple (для stapler).
   - `humanitec-agent-macos-notarize-{short_sha}.json` — manifest pending/completed.

При новом release pending manifest предыдущих releases помечается `superseded` (Apple cancel API **не существует**).

### Phase 2 — follow-up (до 48 ч)

Workflow `humanitec-agent-macos-notarize`:

1. Скачивает manifest asset с release по имени `humanitec-agent-macos-notarize-*.json` (не по `targetCommitish` ветки).
2. `notarytool info` по submission id из manifest.
3. `Accepted` → download app-bundle → stapler → rebuild DMG → `gh release upload --clobber` → update `checksums.txt` → delete app-bundle zip.
4. `Rejected` → workflow error, signed DMG остаётся.
5. Deadline 48 ч (`NOTARY_FOLLOWUP_MAX_AGE_SECONDS=172800`) → `expired`, signed DMG остаётся.

Локальный poll:

```bash
make agent-notarize-followup AGENT_RELEASE_TAG=humanitec-agent-c38f05e
# или все pending:
make agent-notarize-followup
```

### Локальная sync-сборка (dev)

Полный цикл submit + poll + staple в одном `make` (не для CI):

```bash
export APPLE_ID='your@email.com'
export APPLE_ID_PASSWORD='xxxx-xxxx-xxxx-xxxx'
export APPLE_TEAM_ID='MLL2V8KTV4'

make agent-build-macos-local AGENT_VERSION_SHA=$(git rev-parse HEAD)
```

Скрипт [`build-macos-local.sh`](../scripts/build-macos-local.sh) — `AGENT_MACOS_NOTARIZE=1`, polling через `notarytool info`.

## 5. Проверка статуса Apple

Веб-UI очереди notarization **нет**. Только CLI:

```bash
xcrun notarytool history \
  --apple-id "$APPLE_ID" \
  --password "$APPLE_ID_PASSWORD" \
  --team-id "$APPLE_TEAM_ID"
```

## 6. Verify flags

| Env | Когда |
|---|---|
| `AGENT_VERIFY_CODESIGN=1` | CI после sign — `codesign --verify` |
| `AGENT_VERIFY_MACOS_NOTARIZED=1` | После staple — `spctl -a -vv` |

## 7. Prod download

Скачивание с `https://humanitec.ru/agent` — через GitHub Releases API.  
Private repo: секрет `AGENT__RELEASES__GITHUB_TOKEN`.

API `AgentReleaseStatusResponse.macos_notarization_pending=true` — manifest ещё в release, DMG может быть signed-only.

```bash
codesign -dv --verbose=4 /Applications/HumanitecAgent.app
spctl -a -vv /Applications/HumanitecAgent.app
xattr -l /Applications/HumanitecAgent.app
```

Ожидаемый Authority: **Developer ID Application: …**

## 8. Пересборка release

```bash
gh workflow run humanitec-agent-build.yml \
  -f artifact_mode=release \
  -f force_rebuild=true \
  -f publish_draft=false
```
