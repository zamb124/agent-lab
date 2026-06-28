/**
 * Каталог платформ HumanitecAgent для страницы /agent.
 */

export const AGENT_DOWNLOAD_BASE = '/frontend/api/agent/download';

/** @typedef {'windows' | 'macos-arm64' | 'macos-x64' | 'linux-deb' | 'linux-rpm' | 'linux-appimage'} AgentPlatformId */

/** @typedef {'macos' | 'windows' | 'linux' | 'unknown'} AgentHostOs */

/** @typedef {'arm64' | 'x64' | 'unknown'} AgentMacArchitecture */

/**
 * @typedef {Object} AgentPlatformSpec
 * @property {AgentPlatformId} platformId
 * @property {'windows' | 'apple' | 'ubuntu' | 'fedora' | 'linux'} iconTone
 * @property {string} iconSrc
 * @property {string} titleKey
 * @property {string} subtitleKey
 */

const AGENT_PLATFORM_ICON_BASE = '/static/core/assets/marketing/agent-platforms';

/** @type {readonly AgentPlatformSpec[]} */
export const AGENT_PLATFORM_CATALOG = Object.freeze([
    {
        platformId: 'windows',
        iconTone: 'windows',
        iconSrc: `${AGENT_PLATFORM_ICON_BASE}/windows.svg`,
        titleKey: 'platform_card_windows_title',
        subtitleKey: 'platform_card_windows_subtitle',
    },
    {
        platformId: 'macos-arm64',
        iconTone: 'apple',
        iconSrc: `${AGENT_PLATFORM_ICON_BASE}/apple.svg`,
        titleKey: 'platform_card_macos_arm64_title',
        subtitleKey: 'platform_card_macos_arm64_subtitle',
    },
    {
        platformId: 'macos-x64',
        iconTone: 'apple',
        iconSrc: `${AGENT_PLATFORM_ICON_BASE}/apple.svg`,
        titleKey: 'platform_card_macos_x64_title',
        subtitleKey: 'platform_card_macos_x64_subtitle',
    },
    {
        platformId: 'linux-deb',
        iconTone: 'ubuntu',
        iconSrc: `${AGENT_PLATFORM_ICON_BASE}/ubuntu.svg`,
        titleKey: 'platform_card_linux_deb_title',
        subtitleKey: 'platform_card_linux_deb_subtitle',
    },
    {
        platformId: 'linux-rpm',
        iconTone: 'fedora',
        iconSrc: `${AGENT_PLATFORM_ICON_BASE}/fedora.svg`,
        titleKey: 'platform_card_linux_rpm_title',
        subtitleKey: 'platform_card_linux_rpm_subtitle',
    },
    {
        platformId: 'linux-appimage',
        iconTone: 'linux',
        iconSrc: `${AGENT_PLATFORM_ICON_BASE}/linux.svg`,
        titleKey: 'platform_card_linux_appimage_title',
        subtitleKey: 'platform_card_linux_appimage_subtitle',
    },
]);

/** @param {AgentPlatformId} platformId @returns {AgentPlatformSpec} */
export function getAgentPlatformSpec(platformId) {
    for (const platformSpec of AGENT_PLATFORM_CATALOG) {
        if (platformSpec.platformId === platformId) {
            return platformSpec;
        }
    }
    throw new Error(`Unknown agent platform: ${platformId}`);
}

/** @returns {AgentHostOs} */
export function detectAgentHostOs() {
    if (typeof navigator === 'undefined') {
        return 'unknown';
    }
    const userAgent = navigator.userAgent;
    if (userAgent.includes('Mac')) {
        return 'macos';
    }
    if (userAgent.includes('Win')) {
        return 'windows';
    }
    if (userAgent.includes('Linux')) {
        return 'linux';
    }
    return 'unknown';
}

/** @returns {Promise<AgentMacArchitecture>} */
export async function detectAgentMacArchitecture() {
    if (typeof navigator === 'undefined' || !navigator.userAgent.includes('Mac')) {
        return 'unknown';
    }
    if (!navigator.userAgentData || typeof navigator.userAgentData.getHighEntropyValues !== 'function') {
        return 'unknown';
    }
    const values = await navigator.userAgentData.getHighEntropyValues(['architecture']);
    if (values.architecture === 'arm') {
        return 'arm64';
    }
    if (values.architecture === 'x86') {
        return 'x64';
    }
    return 'unknown';
}
