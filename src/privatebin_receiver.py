"""Restricted PrivateBin v2 decoder, never the CLI/network implementation.

Protocol source: PrivateBin 2.0.6 js/privatebin.js; PBinCLI 0.3.7 format.py.
No v1 fallback, passwords, attachments, discussions or unbounded decompression.
"""
import base64
import json
import re
from urllib.parse import urlsplit
import zlib

from pbincli.format import Paste
import base58

from private_secrets import SecretUnavailable
import secret_safety
import safe_download


class BoundedPaste(Paste):
    def _Paste__decompress(self, data):
        if self._compression == 'none':
            if len(data) > 32768:
                raise SecretUnavailable('PrivateBin plaintext size exceeded')
            return data
        inflater = zlib.decompressobj(-zlib.MAX_WBITS)
        output = inflater.decompress(data, 32769)
        if len(output) > 32768 or not inflater.eof or inflater.unused_data:
            raise SecretUnavailable('PrivateBin decompression rejected')
        return output


def link(url, instances):
    """Exact configured HTTPS instance path; full URL stays secret."""
    secret_safety.register(url)
    try:
        parsed = urlsplit(url)
        base = parsed._replace(query='', fragment='').geturl()
        if (base not in instances or parsed.scheme != 'https' or parsed.username or parsed.password
                or parsed.port not in (None, 443) or not re.fullmatch(r'[0-9a-f]{16}', parsed.query)
                or not re.fullmatch(r'-?[1-9A-HJ-NP-Za-km-z]{1,45}', parsed.fragment)):
            raise ValueError()
        key = base58.b58decode(parsed.fragment.removeprefix('-'))
        if len(key) > 32:
            raise ValueError()
        # Match official JS zero-padding after base58 decoding.
        key = key.rjust(32, b'\0')
        return base + '?pasteid=' + parsed.query, base58.b58encode(key).decode()
    except (ValueError, TypeError):
        raise SecretUnavailable('Unsupported private link; use provisioned reference or continue without credentials') from None


def decode(payload, key):
    try:
        if not isinstance(payload, dict) or payload.get('v') != 2 or payload.get('status', 0) != 0:
            raise ValueError()
        adata = payload['adata']
        if not isinstance(adata, list) or len(adata) != 4 or adata[1:] != ['plaintext', 0, 1]:
            raise ValueError()
        spec = adata[0]
        if (not isinstance(spec, list) or len(spec) != 8
                or type(spec[2]) is not int or not 10000 <= spec[2] <= 100000
                or spec[3:7] != [256, 128, 'aes', 'gcm'] or spec[7] not in ('none', 'zlib')
                or len(base64.b64decode(spec[0], validate=True)) != 16
                or len(base64.b64decode(spec[1], validate=True)) != 8
                or not 16 < len(base64.b64decode(payload['ct'], validate=True)) <= 65536):
            raise ValueError()
        paste = BoundedPaste(debug=False)
        paste.setHash(key)
        paste.loadJSON(payload)
        paste.decrypt()
        if paste.getAttachment()[0]:
            raise ValueError()
        value = paste.getText().decode('utf-8')
        if not value or '\x00' in value:
            raise ValueError()
        secret_safety.register(value)
        return value
    except Exception:
        raise SecretUnavailable('PrivateBin content unsupported, unavailable or authentication failed; provision again') from None


def receive(url, instances, private, *, task_id, check, env_key, ttl=3600):
    target, key = link(url, instances)
    try:
        ciphertext = safe_download.download(target, allowed_hosts=[urlsplit(target).hostname],
            max_bytes=100000, timeout=20, max_redirects=0,
            headers={'X-Requested-With': 'JSONHttpRequest', 'Accept': 'application/json'})
        value = decode(json.loads(ciphertext), key)
        return private.provision(value, task_id=task_id, check=check, env_key=env_key, ttl=ttl)
    except Exception:
        raise SecretUnavailable('Private link could not be received safely; provision again or continue without credentials') from None
