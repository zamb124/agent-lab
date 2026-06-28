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

## 4. CI поведение

Workflow [`.github/workflows/humanitec-agent-build.yml`](../../../../.github/workflows/humanitec-agent-build.yml):

1. Step **Import macOS signing certificate** — создаёт `$RUNNER_TEMP/signing.keychain-db`, импортирует `.p12`.
2. `build.sh` — pipeline подписи в три шага:
   - **Pre-sign** `src/bin/goosed` (`codesign` + arch gate `file x86_64` / `arm64`) до `electron-forge make`.
   - **Package + sign `.app`** через forge (`osxSign` в Goose `forge.config.ts`; `goosed` пропускается через `optionsForFile`).
   - **Notarize + staple** `.app` через `notarytool submit` + `notarytool wait` с retry (transient network на GitHub runners) + `stapler` в `build.sh` (не inline `osxNotarize` в forge).
3. `build.sh` — DMG с `.app` + symlink **Applications**.
4. Verify — при подписи: `codesign --verify` на `.app` и `Resources/bin/goosed` + `spctl -a`.
5. При падении macOS job — artifact `forge-*.log` из `vendor/goose/ui/desktop/`.

## 5. Пересборка release

```bash
gh workflow run humanitec-agent-build.yml \
  -f artifact_mode=release \
  -f force_rebuild=true \
  -f publish_draft=false
```

## 6. Проверка на Mac после скачивания

```bash
codesign -dv --verbose=4 /Applications/HumanitecAgent.app
spctl -a -vv /Applications/HumanitecAgent.app
xattr -l /Applications/HumanitecAgent.app   # без com.apple.quarantine после notarize
```

Ожидаемый Authority: **Developer ID Application: …**

## 7. Prod download

Скачивание с `https://humanitec.ru/agent` — через GitHub Releases API.  
Private repo: секрет `AGENT__RELEASES__GITHUB_TOKEN` (Deploy → `platform-secrets` → frontend pod).
