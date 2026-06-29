#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DISTRO_JSON="${ROOT_DIR}/distro/humanitec.json"
BRANDING_DIR="${ROOT_DIR}/branding"
GOOSE_DESKTOP="${ROOT_DIR}/vendor/goose/ui/desktop"
REPO_ROOT="$(cd "${ROOT_DIR}/../../.." && pwd)"

if [[ ! -f "${DISTRO_JSON}" ]]; then
  echo "Distro config missing: ${DISTRO_JSON}" >&2
  exit 1
fi

if [[ ! -d "${GOOSE_DESKTOP}" ]]; then
  echo "Goose desktop tree missing: ${GOOSE_DESKTOP}" >&2
  exit 1
fi

uv run python - "${DISTRO_JSON}" "${BRANDING_DIR}" "${GOOSE_DESKTOP}" "${REPO_ROOT}" <<'PY'
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

repo_root = Path(sys.argv[4])
sys.path.insert(0, str(repo_root))
from apps.agent.desktop.build_contract import load_distro_config

distro_path = Path(sys.argv[1])
branding_dir = Path(sys.argv[2])
goose_desktop = Path(sys.argv[3])
distro = load_distro_config(distro_path)

def resolve_default_frontend_base_url() -> str:
    for env_name in ("HUMANITEC_FRONTEND_BASE_URL", "AGENT_DESKTOP_E2E_BASE_URL"):
        env_value = os.environ.get(env_name)
        if isinstance(env_value, str) and env_value.strip():
            return env_value.strip().rstrip("/")
    return distro.default_frontend_base_url.rstrip("/")

resolved_frontend_base_url = resolve_default_frontend_base_url()

package_path = goose_desktop / "package.json"
package_payload = json.loads(package_path.read_text(encoding="utf-8"))
package_slug = distro.bundle_name.lower()
package_payload["name"] = package_slug
package_payload["productName"] = distro.bundle_name
package_payload["description"] = f"{distro.display_name} App"
package_path.write_text(json.dumps(package_payload, indent=2) + "\n", encoding="utf-8")

for desktop_name in ("forge.deb.desktop", "forge.rpm.desktop"):
    source = branding_dir / desktop_name
    target = goose_desktop / desktop_name
    shutil.copyfile(source, target)

icons_dir = branding_dir / "icons"
goose_images = goose_desktop / "src" / "images"
goose_images.mkdir(parents=True, exist_ok=True)
required_icons = ("icon.png", "icon.ico", "icon.icns")
icons_complete = all((icons_dir / icon_name).is_file() for icon_name in required_icons)
if not icons_complete:
    icon_generator = repo_root / "scripts" / "generate_humanitec_desktop_icons.py"
    if not icon_generator.is_file():
        raise SystemExit(f"desktop icon generator missing: {icon_generator}")
    subprocess.run(
        [sys.executable, str(icon_generator), str(icons_dir)],
        check=True,
        cwd=str(repo_root),
    )
    icons_complete = all((icons_dir / icon_name).is_file() for icon_name in required_icons)
    if not icons_complete:
        raise SystemExit(f"desktop icons incomplete after generation: {icons_dir}")
for icon_name in required_icons:
    source_icon = icons_dir / icon_name
    if source_icon.is_file():
        shutil.copyfile(source_icon, goose_images / icon_name)

defaults_payload = {
    "id": distro.id,
    "display_name": distro.display_name,
    "bundle_name": distro.bundle_name,
    "protocol_scheme": distro.protocol_scheme,
    "auth_callback_path": distro.auth_callback_path,
    "pairing_path": distro.pairing_path,
    "primary_color": distro.primary_color,
    "platform_mcp_path": distro.platform_mcp_path,
    "default_frontend_base_url": resolved_frontend_base_url,
    "default_extensions": distro.default_extensions,
}
defaults_path = branding_dir / "humanitec.defaults.json"
defaults_path.write_text(json.dumps(defaults_payload, indent=2) + "\n", encoding="utf-8")
bundled_target = goose_desktop / "humanitec.defaults.json"
shutil.copyfile(defaults_path, bundled_target)

distro_loader_source = branding_dir / "humanitecDistro.ts"
distro_loader_target = goose_desktop / "src" / "humanitecDistro.ts"
if not distro_loader_source.is_file():
    raise SystemExit(f"humanitecDistro.ts missing: {distro_loader_source}")
shutil.copyfile(distro_loader_source, distro_loader_target)

for runtime_name in (
    "humanitecAgentStore.ts",
    "humanitecTunnelClient.ts",
    "humanitecAgentRuntime.ts",
    "humanitecExtensionOrder.ts",
    "humanitecTestSelectors.ts",
    "humanitecLlmSetup.ts",
    "HumanitecOnboardingGuard.tsx",
):
    runtime_source = branding_dir / runtime_name
    runtime_target = goose_desktop / "src" / runtime_name
    if not runtime_source.is_file():
        raise SystemExit(f"{runtime_name} missing: {runtime_source}")
    shutil.copyfile(runtime_source, runtime_target)

pairing_html_source = branding_dir / "humanitec-pairing.html"
pairing_html_target = goose_desktop / "src" / "humanitec-pairing.html"
if not pairing_html_source.is_file():
    raise SystemExit(f"humanitec-pairing.html missing: {pairing_html_source}")
shutil.copyfile(pairing_html_source, pairing_html_target)

built_in_extensions_path = goose_desktop / "src" / "built-in-extensions.json"
built_in_extensions = json.loads(built_in_extensions_path.read_text(encoding="utf-8"))
if not isinstance(built_in_extensions, list):
    raise SystemExit("built-in-extensions.json must be a list")
extension_ids = {item.get("id") for item in built_in_extensions if isinstance(item, dict)}
if "platform_mcp" in extension_ids:
    built_in_extensions = [
        item for item in built_in_extensions
        if not (isinstance(item, dict) and item.get("id") == "platform_mcp")
    ]
    built_in_extensions_path.write_text(
        json.dumps(built_in_extensions, indent=2) + "\n",
        encoding="utf-8",
    )

bundled_extensions_path = goose_desktop / "src" / "components" / "settings" / "extensions" / "bundled-extensions.json"
bundled_extensions = json.loads(bundled_extensions_path.read_text(encoding="utf-8"))
if not isinstance(bundled_extensions, list):
    raise SystemExit("bundled-extensions.json must be a list")
platform_mcp_entry = {
    "id": "platform_mcp",
    "name": "platform_mcp",
    "display_name": "Humanitec Platform MCP",
    "description": "Flows компании через Platform MCP endpoint Humanitec.",
    "enabled": True,
    "type": "streamable_http",
    "uri": "${HUMANITEC_PLATFORM_MCP_URL}",
    "headers": {
        "Authorization": "Bearer ${HUMANITEC_DEVICE_TOKEN}",
    },
    "timeout": 300,
    "bundled": True,
    "humanitec_primary": True,
    "priority": 0,
}
bundled_extensions = [
    item for item in bundled_extensions if not (isinstance(item, dict) and item.get("id") == "platform_mcp")
]
bundled_extensions.insert(0, platform_mcp_entry)
bundled_extensions_path.write_text(json.dumps(bundled_extensions, indent=2) + "\n", encoding="utf-8")

bundled_ts_path = goose_desktop / "src" / "components" / "settings" / "extensions" / "bundled-extensions.ts"
bundled_ts_text = bundled_ts_path.read_text(encoding="utf-8")
headers_type_anchor = "  env_keys?: Array<string>;\n  timeout?: number;"
headers_type_patch = (
    "  env_keys?: Array<string>;\n"
    "  headers?: { [key: string]: string };\n"
    "  timeout?: number;"
)
streamable_case_anchor = """        case 'streamable_http':
          extConfig = {
            type: bundledExt.type,
            name: bundledExt.name,
            description: bundledExt.description,
            timeout: bundledExt.timeout,
            uri: bundledExt.uri || '',
            bundled: true,
          };"""
streamable_case_patch = """        case 'streamable_http':
          extConfig = {
            type: bundledExt.type,
            name: bundledExt.name,
            description: bundledExt.description,
            timeout: bundledExt.timeout,
            uri: bundledExt.uri || '',
            headers: bundledExt.headers,
            bundled: true,
          };"""
bundled_ts_modified = False
if "headers?: { [key: string]: string };" not in bundled_ts_text:
    if headers_type_anchor not in bundled_ts_text:
        raise SystemExit("bundled-extensions.ts headers type anchor missing")
    bundled_ts_text = bundled_ts_text.replace(headers_type_anchor, headers_type_patch, 1)
    bundled_ts_modified = True

if "headers: bundledExt.headers" not in bundled_ts_text:
    if streamable_case_anchor not in bundled_ts_text:
        raise SystemExit("bundled-extensions.ts streamable_http case anchor missing")
    bundled_ts_text = bundled_ts_text.replace(streamable_case_anchor, streamable_case_patch, 1)
    bundled_ts_modified = True

if bundled_ts_modified:
    bundled_ts_path.write_text(bundled_ts_text, encoding="utf-8")

bundled_ts_text = bundled_ts_path.read_text(encoding="utf-8")
reorder_import = "import { reorderHumanitecBundledExtensions } from '../../../humanitecExtensionOrder';"
if reorder_import not in bundled_ts_text:
    import_anchor = "import bundledExtensionsData from './bundled-extensions.json';"
    if import_anchor not in bundled_ts_text:
        raise SystemExit("bundled-extensions.ts import anchor missing")
    bundled_ts_text = bundled_ts_text.replace(import_anchor, reorder_import + "\n" + import_anchor, 1)
    bundled_ts_modified = True

reorder_call_anchor = "    const bundledExtensions = bundledExtensionsData as BundledExtension[];"
reorder_call_patch = (
    "    const bundledExtensions = reorderHumanitecBundledExtensions(\n"
    "      bundledExtensionsData as BundledExtension[],\n"
    "    );"
)
if reorder_call_anchor in bundled_ts_text and "reorderHumanitecBundledExtensions(" not in bundled_ts_text:
    bundled_ts_text = bundled_ts_text.replace(reorder_call_anchor, reorder_call_patch, 1)
    bundled_ts_modified = True

type_anchor = "  allow_configure?: boolean;\n};"
type_patch = (
    "  allow_configure?: boolean;\n"
    "  display_name?: string;\n"
    "  humanitec_primary?: boolean;\n"
    "  priority?: number;\n"
    "};"
)
if "humanitec_primary?: boolean;" not in bundled_ts_text:
    if type_anchor not in bundled_ts_text:
        raise SystemExit("bundled-extensions.ts BundledExtension type anchor missing")
    bundled_ts_text = bundled_ts_text.replace(type_anchor, type_patch, 1)
    bundled_ts_modified = True

streamable_display_anchor = """            description: bundledExt.description,
            timeout: bundledExt.timeout,
            uri: bundledExt.uri || '',
            headers: bundledExt.headers,
            bundled: true,
          };"""
streamable_display_patch = """            description: bundledExt.description,
            display_name: bundledExt.display_name,
            timeout: bundledExt.timeout,
            uri: bundledExt.uri || '',
            headers: bundledExt.headers,
            bundled: true,
          };"""
if "display_name: bundledExt.display_name" not in bundled_ts_text:
    if streamable_display_anchor not in bundled_ts_text:
        raise SystemExit("bundled-extensions.ts streamable display_name anchor missing")
    bundled_ts_text = bundled_ts_text.replace(streamable_display_anchor, streamable_display_patch, 1)
    bundled_ts_modified = True

if bundled_ts_modified:
    bundled_ts_path.write_text(bundled_ts_text, encoding="utf-8")

preload_path = goose_desktop / "src" / "preload.ts"
preload_text = preload_path.read_text(encoding="utf-8")
preload_anchor = "contextBridge.exposeInMainWorld('appConfig', appConfigAPI);"
preload_patch = """contextBridge.exposeInMainWorld('humanitecAgent', {
  discover: (originOverride?: string) => ipcRenderer.invoke('humanitec-agent:discover', originOverride),
  pair: (pairingCode: string) => ipcRenderer.invoke('humanitec-agent:pair', pairingCode),
  status: () => ipcRenderer.invoke('humanitec-agent:status'),
  logout: () => ipcRenderer.invoke('humanitec-agent:logout'),
  openPairing: () => ipcRenderer.invoke('humanitec-agent:open-pairing'),
  openSettings: () => ipcRenderer.invoke('humanitec-agent:open-settings'),
  distro: () => ipcRenderer.invoke('humanitec-agent:distro'),
  resyncExtensions: () => ipcRenderer.invoke('humanitec-agent:extensions-resync'),
  onPlatformMcpEnvUpdated: (callback: (payload: { platform_mcp_url: string }) => void) => {
    ipcRenderer.on('humanitec-agent:platform-mcp-env-updated', (_event, payload) => callback(payload));
  },
  onExtensionsResync: (callback: () => void) => {
    ipcRenderer.on('humanitec-agent:extensions-resync', () => callback());
  },
});"""
if "exposeInMainWorld('humanitecAgent'" not in preload_text:
    if preload_anchor not in preload_text:
        raise SystemExit("preload.ts appConfig expose anchor missing")
    preload_text = preload_text.replace(
        preload_anchor,
        preload_anchor + "\n" + preload_patch,
        1,
    )
    preload_path.write_text(preload_text, encoding="utf-8")
elif "resyncExtensions" not in preload_text or "openSettings" not in preload_text:
    old_humanitec_block_start = preload_text.find("contextBridge.exposeInMainWorld('humanitecAgent', {")
    if old_humanitec_block_start == -1:
        raise SystemExit("preload.ts humanitecAgent block missing")
    old_humanitec_block_end = preload_text.find("});", old_humanitec_block_start)
    if old_humanitec_block_end == -1:
        raise SystemExit("preload.ts humanitecAgent block end missing")
    old_humanitec_block_end = preload_text.find("\n", old_humanitec_block_end) + 1
    preload_text = (
        preload_text[:old_humanitec_block_start]
        + preload_patch
        + "\n"
        + preload_text[old_humanitec_block_end:]
    )
    preload_path.write_text(preload_text, encoding="utf-8")

main_path = goose_desktop / "src" / "main.ts"
main_text = main_path.read_text(encoding="utf-8")
if "applyHumanitecDistroEnv" not in main_text:
    import_anchor = "import 'dotenv/config';"
    if import_anchor not in main_text:
        raise SystemExit("main.ts dotenv anchor missing")
    main_text = main_text.replace(
        import_anchor,
        import_anchor
        + "\nimport { applyHumanitecDistroEnv } from './humanitecDistro';\n"
        + "applyHumanitecDistroEnv();",
        1,
    )

if "humanitecAgentRuntime" not in main_text:
    distro_import_anchor = "import { applyHumanitecDistroEnv } from './humanitecDistro';"
    if distro_import_anchor not in main_text:
        raise SystemExit("main.ts humanitecDistro import missing")
    main_text = main_text.replace(
        distro_import_anchor,
        distro_import_anchor
        + "\nimport { handleHumanitecDeepLink, initHumanitecAgentRuntime } from './humanitecAgentRuntime';",
        1,
    )

if "await initHumanitecAgentRuntime();" not in main_text:
    app_main_anchor = "    await appMain();"
    if app_main_anchor in main_text:
        main_text = main_text.replace(
            app_main_anchor,
            "    await initHumanitecAgentRuntime();\n    await appMain();",
            1,
        )
    else:
        ready_anchor = "await app.whenReady();"
        if ready_anchor not in main_text:
            raise SystemExit("main.ts app.whenReady anchor missing")
        main_text = main_text.replace(
            ready_anchor,
            ready_anchor + "\n    await initHumanitecAgentRuntime();",
            1,
        )

open_url_init_anchor = "    initHumanitecAgentRuntime();"
open_url_init_replacement = "    await initHumanitecAgentRuntime();"
if open_url_init_anchor in main_text:
    main_text = main_text.replace(open_url_init_anchor, open_url_init_replacement)

open_url_ready_anchor = (
    "    await app.whenReady();\n"
    "    await initHumanitecAgentRuntime();\n"
    "\n"
    "    const recentDirs = loadRecentDirs();"
)
open_url_ready_anchor_no_blank = (
    "    await app.whenReady();\n"
    "    await initHumanitecAgentRuntime();\n"
    "    const recentDirs = loadRecentDirs();"
)
for anchor in (open_url_ready_anchor, open_url_ready_anchor_no_blank):
    if anchor in main_text and "await handleHumanitecDeepLink(url)" not in main_text:
        main_text = main_text.replace(
            anchor,
            "    await app.whenReady();\n"
            "    await initHumanitecAgentRuntime();\n"
            "\n"
            "    if (await handleHumanitecDeepLink(url)) {\n"
            "      return;\n"
            "    }\n"
            "\n"
            "    const recentDirs = loadRecentDirs();",
            1,
        )
        break

main_text = main_text.replace(
    "import { installHumanitecTestSelectors } from './humanitecTestSelectors';\n",
    "",
)
main_text = main_text.replace("\n    installHumanitecTestSelectors();", "")

if "handleHumanitecDeepLink(url)" not in main_text:
    protocol_anchor = "async function processProtocolUrl(url: string, parsedUrl: URL, window: BrowserWindow) {"
    if protocol_anchor not in main_text:
        raise SystemExit("main.ts processProtocolUrl anchor missing")
    main_text = main_text.replace(
        protocol_anchor,
        protocol_anchor
        + "\n  if (await handleHumanitecDeepLink(url)) {\n    return;\n  }\n",
        1,
    )

protocol_scheme = distro.protocol_scheme
for goose_token in ("goose://", "'goose'", '"goose"'):
    main_text = main_text.replace(goose_token, goose_token.replace("goose", protocol_scheme))

main_path.write_text(main_text, encoding="utf-8")

forge_path = goose_desktop / "forge.config.ts"
text = forge_path.read_text(encoding="utf-8")
package_id = distro.bundle_name.lower()
packager_name_marker = "name: process.env.GOOSE_BUNDLE_NAME"
packager_cfg_anchor = "let cfg = {\n  asar: true,"
packager_cfg_patch = (
    "let cfg = {\n"
    "  name: process.env.GOOSE_BUNDLE_NAME || 'Goose',\n"
    "  executableName: process.env.GOOSE_BUNDLE_NAME || 'Goose',\n"
    # @electron/packager стейджит .app во временном каталоге, затем move в out/.
    # По умолчанию это системный $TMPDIR; на GitHub macOS-раннере он на отдельном
    # маленьком томе, и упаковка/move 245MB goosed там молча обрывались. Через
    # ELECTRON_PACKAGER_TMPDIR build.sh указывает каталог на том же томе, что out/.
    "  tmpdir: process.env.ELECTRON_PACKAGER_TMPDIR || undefined,\n"
    "  asar: true,"
)
if packager_name_marker not in text:
    if packager_cfg_anchor in text:
        text = text.replace(packager_cfg_anchor, packager_cfg_patch, 1)
    else:
        raise SystemExit("forge.config.ts packager cfg anchor missing")
replacements = {
    "name: 'Goose'": f"name: '{package_id}'",
    "bin: 'Goose'": f"bin: '{distro.bundle_name}'",
    "name: 'GooseProtocol'": f"name: '{distro.bundle_name}Protocol'",
    "schemes: ['goose']": f"schemes: ['{distro.protocol_scheme}']",
    "id: 'io.github.block.Goose'": f"id: 'ai.humanitec.{package_id}'",
    "maintainer: 'AAIF (Agentic AI Foundation)'": f"maintainer: '{distro.maintainer}'",
    "homepage: 'https://goose-docs.ai/'": f"homepage: '{distro.homepage}'",
}
for source, target in replacements.items():
    if source in text:
        text = text.replace(source, target)
    elif target not in text:
        raise SystemExit(f"forge.config.ts branding anchor missing: {source}")

extra_resource_anchor = "extraResource: ['src/bin', 'src/images'],"
extra_resource_target = "extraResource: ['src/bin', 'src/images', 'humanitec.defaults.json'],"
if extra_resource_anchor in text:
    text = text.replace(extra_resource_anchor, extra_resource_target, 1)

extend_info_anchor = "extendInfo: {"
if extend_info_anchor in text and "NSHumanitecUsageDescription" not in text:
    text = text.replace(
        extend_info_anchor,
        extend_info_anchor
        + f"\n      NSHumanitecUsageDescription: '{distro.display_name} desktop agent',",
        1,
    )

zip_platforms_old = "platforms: ['darwin', 'win32', 'linux'],"
zip_platforms_new = "platforms: ['darwin'],"
if zip_platforms_old in text:
    text = text.replace(zip_platforms_old, zip_platforms_new, 1)
elif "@electron-forge/maker-zip" in text and "platforms: ['darwin']," not in text:
    raise SystemExit("forge.config.ts maker-zip platforms anchor missing")

deb_maker_anchor = "      name: '@electron-forge/maker-deb',\n      config:"
deb_maker_patch = "      name: '@electron-forge/maker-deb',\n      platforms: ['linux'],\n      config:"
if deb_maker_anchor in text and "name: '@electron-forge/maker-deb',\n      platforms:" not in text:
    text = text.replace(deb_maker_anchor, deb_maker_patch, 1)

rpm_maker_anchor = "      name: '@electron-forge/maker-rpm',\n      config:"
rpm_maker_patch = "      name: '@electron-forge/maker-rpm',\n      platforms: ['linux'],\n      config:"
if rpm_maker_anchor in text and "name: '@electron-forge/maker-rpm',\n      platforms:" not in text:
    text = text.replace(rpm_maker_anchor, rpm_maker_patch, 1)

flatpak_maker_anchor = "      name: '@electron-forge/maker-flatpak',\n      config:"
flatpak_maker_patch = "      name: '@electron-forge/maker-flatpak',\n      platforms: ['linux'],\n      config:"
if flatpak_maker_anchor in text and "name: '@electron-forge/maker-flatpak',\n      platforms:" not in text:
    text = text.replace(flatpak_maker_anchor, flatpak_maker_patch, 1)

makers_plugins_anchor = "  ],\n  plugins:"
if "@electron-forge/maker-wix" not in text:
    if makers_plugins_anchor not in text:
        raise SystemExit("forge.config.ts makers/plugins anchor missing")
    extra_makers = """
    {
      name: '@electron-forge/maker-wix',
      platforms: ['win32'],
      config: {
        language: 1033,
        manufacturer: 'Humanitec',
        icon: 'src/images/icon.ico',
      },
    },
    {
      name: '@reforged/maker-appimage',
      platforms: ['linux'],
      config: {
        options: {
          name: 'humanitecagent',
          bin: 'HumanitecAgent',
          categories: ['Development'],
          icon: 'src/images/icon.png',
        },
      },
    },
  ],
  plugins:"""
    text = text.replace(makers_plugins_anchor, extra_makers, 1)

# Notarization вынесена в build.sh (notarytool + stapler после forge).
# goosed (~245MB extraResource) pre-sign до forge; osxSign пропускает его через optionsForFile.
osx_sign_old = """if (process.env.APPLE_TEAM_ID) {
  cfg.osxSign = {
    keychain: process.env.KEYCHAIN_PATH || undefined,
    entitlements: 'entitlements.plist',
    'entitlements-inherit': 'entitlements.plist',
  };
  cfg.osxNotarize = {
    appleId: process.env.APPLE_ID,
    appleIdPassword: process.env.APPLE_ID_PASSWORD,
    teamId: process.env.APPLE_TEAM_ID,
  };
}"""
osx_sign_new = """if (process.env.APPLE_TEAM_ID) {
  cfg.osxSign = {
    keychain: process.env.KEYCHAIN_PATH || undefined,
    entitlements: 'entitlements.plist',
    'entitlements-inherit': 'entitlements.plist',
    continueOnError: false,
    optionsForFile: (filePath) => {
      const pathSep = require('path').sep;
      if (filePath.includes(`${pathSep}Resources${pathSep}bin${pathSep}goosed`)) {
        return { sign: false };
      }
      return {};
    },
  };
}"""
if "optionsForFile: (filePath)" not in text:
    if osx_sign_old in text:
        text = text.replace(osx_sign_old, osx_sign_new, 1)
    elif "cfg.osxNotarize" in text:
        raise SystemExit(
            "forge.config.ts osxSign/osxNotarize block does not match expected anchor"
        )
elif "cfg.osxNotarize" in text:
    osx_notarize_block = """
  cfg.osxNotarize = {
    appleId: process.env.APPLE_ID,
    appleIdPassword: process.env.APPLE_ID_PASSWORD,
    teamId: process.env.APPLE_TEAM_ID,
  };"""
    text = text.replace(osx_notarize_block, "", 1)

if "continueOnError: false" not in text and "optionsForFile: (filePath)" in text:
    text = text.replace(
        "'entitlements-inherit': 'entitlements.plist',",
        "'entitlements-inherit': 'entitlements.plist',\n    continueOnError: false,",
        1,
    )

forge_path.write_text(text, encoding="utf-8")

app_ts_path = goose_desktop / "src" / "App.tsx"
app_ts_text = app_ts_path.read_text(encoding="utf-8")
if "HumanitecOnboardingGuard" not in app_ts_text:
    app_import_anchor = "import OnboardingGuard from './components/onboarding/OnboardingGuard';"
    if app_import_anchor not in app_ts_text:
        raise SystemExit("App.tsx OnboardingGuard import anchor missing")
    app_ts_text = app_ts_text.replace(
        app_import_anchor,
        app_import_anchor + "\nimport HumanitecOnboardingGuard from './HumanitecOnboardingGuard';",
        1,
    )
    app_ts_text = app_ts_text.replace("<OnboardingGuard>", "<HumanitecOnboardingGuard>", 1)
    app_ts_text = app_ts_text.replace("</OnboardingGuard>", "</HumanitecOnboardingGuard>", 1)
    app_ts_path.write_text(app_ts_text, encoding="utf-8")

app_ts_text = app_ts_path.read_text(encoding="utf-8")
if "installHumanitecTestSelectors" not in app_ts_text:
    selectors_import_anchor = "import HumanitecOnboardingGuard from './HumanitecOnboardingGuard';"
    if selectors_import_anchor not in app_ts_text:
        selectors_import_anchor = "import { registerPlatformEventHandlers } from './utils/platform_events';"
        if selectors_import_anchor not in app_ts_text:
            raise SystemExit("App.tsx registerPlatformEventHandlers import anchor missing")
    app_ts_text = app_ts_text.replace(
        selectors_import_anchor,
        selectors_import_anchor
        + "\nimport { installHumanitecTestSelectors } from './humanitecTestSelectors';",
        1,
    )
    platform_handlers_effect = (
        "  useEffect(() => {\n"
        "    return registerPlatformEventHandlers();\n"
        "  }, []);"
    )
    if platform_handlers_effect not in app_ts_text:
        raise SystemExit("App.tsx registerPlatformEventHandlers useEffect anchor missing")
    app_ts_text = app_ts_text.replace(
        platform_handlers_effect,
        platform_handlers_effect
        + "\n\n  useEffect(() => {\n    installHumanitecTestSelectors();\n  }, []);",
        1,
    )
    app_ts_path.write_text(app_ts_text, encoding="utf-8")

onboarding_path = goose_desktop / "src" / "components" / "onboarding" / "OnboardingGuard.tsx"
onboarding_text = onboarding_path.read_text(encoding="utf-8")
onboarding_replacements = {
    "defaultMessage: 'Welcome to goose',": "defaultMessage: 'Welcome to HumanitecAgent',",
    "defaultMessage: 'Your local AI agent. Connect an AI model provider to get started.',":
    "defaultMessage: 'Configure an AI model provider. Platform MCP is available after pairing.',",
}
for source, target in onboarding_replacements.items():
    if source in onboarding_text:
        onboarding_text = onboarding_text.replace(source, target, 1)
onboarding_path.write_text(onboarding_text, encoding="utf-8")

ru_messages_path = goose_desktop / "src" / "i18n" / "messages" / "ru.json"
if ru_messages_path.is_file():
    ru_messages = json.loads(ru_messages_path.read_text(encoding="utf-8"))
    ru_humanitec_entries = {
        "humanitecOnboarding.title": {
            "defaultMessage": "Подключите HumanitecAgent к платформе",
        },
        "humanitecOnboarding.description": {
            "defaultMessage": (
                "Введите 6-значный код из Настройки → HumanitecAgent на платформе "
                "или откройте Настройки, чтобы получить код."
            ),
        },
        "humanitecOnboarding.pairingCodePlaceholder": {"defaultMessage": "000000"},
        "humanitecOnboarding.pairButton": {"defaultMessage": "Подключить устройство"},
        "humanitecOnboarding.openSettings": {"defaultMessage": "Открыть настройки платформы"},
        "humanitecOnboarding.pairingInProgress": {"defaultMessage": "Подключение…"},
        "humanitecOnboarding.invalidCode": {"defaultMessage": "Код должен содержать 6 цифр"},
        "humanitecOnboarding.llmSetupInProgress": {"defaultMessage": "Настраиваем Platform Brain…"},
        "humanitecOnboarding.llmSetupFailed": {"defaultMessage": "Не удалось настроить LLM платформы"},
        "onboardingGuard.welcomeTitle": {"defaultMessage": "Добро пожаловать в HumanitecAgent"},
        "onboardingGuard.welcomeDescription": {
            "defaultMessage": (
                "Настройте провайдера AI-модели. Platform MCP доступен после подключения к платформе."
            ),
        },
    }
    ru_messages.update(ru_humanitec_entries)
    ru_messages_path.write_text(
        json.dumps(ru_messages, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

print(
    f"Applied Humanitec branding: bundle={distro.bundle_name}, "
    f"protocol={distro.protocol_scheme}, extensions={','.join(distro.default_extensions)}"
)
PY

echo "Humanitec branding applied"
