/**
 * IMAP modified UTF-7 → Unicode (RFC 3501 §5.1.3).
 * Wire folder names stay encoded; decode only for display labels.
 */

const PRINTABLE_ASCII_RE = /^[\x20-\x7e]*$/;

/**
 * @param {string} encoded
 * @returns {string}
 */
export function decodeImapModifiedUtf7(encoded: string) {
    if (typeof encoded !== 'string') {
        throw new Error('decodeImapModifiedUtf7: encoded must be a string');
    }
    if (encoded.length === 0) {
        return '';
    }
    if (PRINTABLE_ASCII_RE.test(encoded) && !encoded.includes('&')) {
        return encoded;
    }

    let out = '';
    let index = 0;
    while (index < encoded.length) {
        const amp = encoded.indexOf('&', index);
        if (amp < 0) {
            out += encoded.slice(index);
            break;
        }
        out += encoded.slice(index, amp);
        if (amp + 1 < encoded.length && encoded[amp + 1] === '-') {
            out += '&';
            index = amp + 2;
            continue;
        }
        const end = encoded.indexOf('-', amp + 1);
        if (end < 0) {
            throw new Error(`decodeImapModifiedUtf7: unclosed shift sequence in ${encoded}`);
        }
        const b64Body = encoded.slice(amp + 1, end).replace(/,/g, '/');
        const padLength = (4 - (b64Body.length % 4)) % 4;
        const b64 = `${b64Body}${'='.repeat(padLength)}`;
        let binary;
        try {
            binary = atob(b64);
        } catch (err) {
            throw new Error(`decodeImapModifiedUtf7: invalid base64 in ${encoded}: ${err}`);
        }
        if (binary.length % 2 !== 0) {
            throw new Error(`decodeImapModifiedUtf7: odd UTF-16BE length in ${encoded}`);
        }
        const codeUnits = [];
        for (let i = 0; i < binary.length; i += 2) {
            codeUnits.push((binary.charCodeAt(i) << 8) | binary.charCodeAt(i + 1));
        }
        out += String.fromCharCode(...codeUnits);
        index = end + 1;
    }
    return out;
}
