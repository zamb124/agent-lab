/**
 * Тот же контракт, что core.guest_runtime.git_url.commit_sha_from_git_url:
 * SHA из сегмента commit/commits + 40 hex на любом хосте. Живую ветку не резолвим.
 */

const COMMIT_SHA_RE = /\/commits?\/([0-9a-fA-F]{40})(?=[/?#]|$)/;

/**
 * @param {string} gitUrl
 * @returns {string}
 */
export function commitShaFromGitUrl(gitUrl) {
    if (typeof gitUrl !== 'string') {
        throw new Error('commitShaFromGitUrl: gitUrl string required');
    }
    const stripped = gitUrl.trim();
    if (stripped.length === 0) {
        return '';
    }
    const match = COMMIT_SHA_RE.exec(stripped);
    if (match === null) {
        return '';
    }
    return match[1].toLowerCase();
}
