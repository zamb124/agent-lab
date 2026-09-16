import { describe, expect, it } from 'vitest';
import { commitShaFromGitUrl } from '../../../../apps/flows/ui/_helpers/code-agent-git.js';

describe('commitShaFromGitUrl', () => {
    it('extracts 40-hex SHA from GitHub and GitLab commit URLs', () => {
        expect(
            commitShaFromGitUrl(
                'https://github.com/zub123123123/cheetah-agent/commit/70eb6c3c6909d1f975d9c7e6c723bae5db897478',
            ),
        ).toBe('70eb6c3c6909d1f975d9c7e6c723bae5db897478');
        expect(
            commitShaFromGitUrl(
                'https://gitlab.example.com/group/project/-/commit/70eb6c3c6909d1f975d9c7e6c723bae5db897478',
            ),
        ).toBe('70eb6c3c6909d1f975d9c7e6c723bae5db897478');
    });

    it('returns empty for tree URLs and incomplete SHA', () => {
        expect(
            commitShaFromGitUrl('https://gitlab.example.com/group/project/-/tree/main'),
        ).toBe('');
        expect(
            commitShaFromGitUrl(
                'https://github.com/zub123123123/cheetah-agent/commit/abc123',
            ),
        ).toBe('');
    });
});
