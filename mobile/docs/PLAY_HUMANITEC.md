# Humanitec: что заполнить в Google Play Console

Черновики текстов согласованы с лендингом и [`PLAY_MANUAL.md`](PLAY_MANUAL.md). Подставьте **реальные URL** поддержки и политики; юридические формулировки проверьте у себя.

---

## App identity

| Поле | Значение |
|------|----------|
| **applicationId** (package name) | `ru.humanitec.app` (тот же, что iOS bundle id; не менять после первого релиза). |
| **App name** | `Humanitec` (≤30 символов). |
| **Default language** | Russian (ru-RU). Дополнительно — English (en-US). |
| **Category** | Productivity (основная) или Business. |
| **Tags** | `Productivity`, `Business`, `Communication`. |
| **App icon** (512×512) | `mobile/screens/play_icon_512.png` — генерируется `scripts/generate_humanitec_pwa_icons.py`. |
| **Feature graphic** (1024×500) | `mobile/screens/play_feature_graphic_1024x500.png` — там же. |

---

## Main store listing — тексты (Russian)

| Поле | Лимит | Черновик (RU) |
|------|-------|----------------|
| **App name** | 30 | `Humanitec` |
| **Short description** | 80 | `AI-агенты, чаты, видеозвонки, граф контактов и база знаний — в одном клиенте.` |
| **Full description** | 4000 | См. ниже. |

### Full description (RU, черновик)

```
Humanitec — платформа для автоматизации бизнеса и совместной работы команд.

В одном клиенте:
• AI Studio — конструктор AI-агентов и сценариев (flows)
• Sync — чаты, треды, голосовые, видеозвонки и совместная работа
• NetWorkle — CRM на базе графа контактов и связей
• Knowledge Base — умная база знаний с семантическим поиском
• Documents — совместное редактирование документов

Android-клиент Humanitec — нативная оболочка для платформы. Логин, выбор компании, управление ролями и биллингом — там же, что и в браузере; приложение добавляет нативные уведомления, оффлайн-заглушку и быстрый доступ через иконку в системе.

Подходит для команд от 3 человек: тех, кто строит AI-ассистентов на базе своих данных и общается в единой среде, не разнося чаты, агенты и базу знаний по разным сервисам.

Узнать больше: https://humanitec.ru
```

### Tags / Categorization

- Primary category: **Productivity**
- Tags (выбрать из списка Google): **Productivity tools**, **Communication**, **Project management**

---

## Main store listing — тексты (English, опционально)

| Поле | Лимит | Черновик (EN) |
|------|-------|----------------|
| **App name** | 30 | `Humanitec` |
| **Short description** | 80 | `AI agents, chat, video calls, CRM and knowledge base in one client.` |
| **Full description** | 4000 | См. ниже. |

```
Humanitec is a platform for business automation and team collaboration.

In a single app:
• AI Studio — visual builder for AI agents and workflows
• Sync — chat, threads, voice messages, and video calls
• NetWorkle — CRM with a contact graph
• Knowledge Base — smart documents with semantic search
• Documents — collaborative editing

The Humanitec Android client is a native shell over the platform: the same login, company switch, roles, and billing as in the browser, plus native push notifications, an offline screen, and a system app icon for quick access.

Built for teams of 3+ who build AI assistants on top of their own data and want chats, agents, and knowledge in one place.

Learn more: https://humanitec.ru
```

---

## Screenshots

- **Phone** — минимум 2, максимум 8. Размеры в `mobile/screens/generated/play_phone_*` (1080×1920 / 1920×1080).
- **7" Tablet** — `mobile/screens/generated/play_tablet7_*` (1200×1920 / 1920×1200).
- **10" Tablet** — `mobile/screens/generated/play_tablet10_*` (1600×2560 / 2560×1600).

Покажите: вход, дашборд, **Sync** (чат), агентов / базу знаний — чтобы было видно ценность приложения, не пустой WebView.

---

## Contact details

| Поле | Черновик |
|------|----------|
| **Website** | `https://humanitec.ru` |
| **Email** | `support@humanitec.ru` (или ваш контакт поддержки) |
| **Phone** | По желанию |
| **Privacy Policy** | URL вашей страницы политики (тот же, что в App Store Connect и в Setup → App content) |

---

## Data safety (Setup → App content → Data safety)

Опросник Google Play. Чек-лист **что мы собираем**:

- **Account info**: name, email, user IDs — для аутентификации и идентификации в команде
- **Personal info**: profile photo, bio
- **Messages**: сообщения чатов и аудио/видео в Sync
- **Files and docs**: вложения в чатах, документы Knowledge Base / Documents
- **App activity**: in-app actions, flows runs (для аналитики работы агентов)
- **App info and performance**: crash logs, diagnostics
- **Device or other IDs**: FCM registration token (для push)

Все категории — **Collected**, **Linked to user**, **Encrypted in transit** (HTTPS), **User can request deletion** (через `support@humanitec.ru` или `/settings`).

---

## Build → Release notes (Russian)

```
Первая публичная сборка Humanitec для Android: чаты Sync с голосом и видеозвонками, AI-агенты, CRM, база знаний.
Поддержка push-уведомлений (FCM) и App Links на humanitec.ru / humanetic.ru / agents-lab.ru.
```

---

## Сопоставление с продуктом (имена из платформы)

| В витрине / в тексте | Смысл |
|----------------------|--------|
| Humanitec | Название платформы |
| AI Studio | Конструктор AI-агентов (flows) |
| Sync | Чаты и видеозвонки |
| NetWorkle | CRM / граф контактов |
| Knowledge Base | Документы и семантический поиск |

При необходимости сокращайте под лимиты Google Play.
