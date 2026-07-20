# platform-markdown-editor

Platform markdown editor (`<platform-markdown-editor>`).

Canon: `value` = markdown; `change` → `{ value, htmlValue, textValue }`.

Layers: document (CodeMirror), compose/wysiwyg (mail), variables, mentions, file-drop.

## Strict test coverage

| Layer | File |
|---|---|
| sanitize / htmlToMarkdown / htmlToPlainText | `tests/frontend_core/browser/utils/markdown-html.spec.js` |
| document API, modes, mentions, fail-closed | `tests/frontend_core/browser/components/platform-markdown-editor.spec.js` |
| compose / attachments / primary | `tests/frontend_core/browser/components/platform-markdown-editor-compose.spec.js` |
| enable-variables preview | `tests/frontend_core/browser/components/platform-markdown-editor-variables.spec.js` |
| UI Kit L1 | `contract.spec.js` (re-exports all of the above) |

```bash
npm run test:core-browser -- --files tests/frontend_core/browser/utils/markdown-html.spec.js
npm run test:core-browser -- --files 'tests/frontend_core/browser/components/platform-markdown-editor*.spec.js'
npm run test:ui-kit -- tests/ui/design-system/components/platform-markdown-editor/contract.spec.js
```
