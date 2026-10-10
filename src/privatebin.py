"""PrivateBin v2 links: parse, fetch once, decrypt locally.

A PrivateBin link looks like ``https://host/path/?<pasteid>#<base58 key>``. The server only
ever holds ciphertext; the key travels in the URL fragment, which browsers never send. The
bot fetches the paste JSON (``GET <base>?pasteid=<id>`` with ``X-Requested-With:
JSONHttpRequest``) and decrypts it here:

    key   = base58(fragment), left-padded with zero bytes to 32
    aes   = PBKDF2-HMAC-SHA256(key, salt, iterations, 32 bytes)
    plain = AES-256-GCM(aes, iv, ct[:-16], tag=ct[-16:], aad=json(adata, no spaces))
    text  = json(inflate_raw(plain) if compression == "zlib" else plain)["paste"]

Only what the bot needs is accepted: protocol v2, plain text (no attachments, no
discussion), burn-after-reading, bounded sizes. Anything else is ``LinkUnusable``.

Protocol reference: PrivateBin js/privatebin.js (CryptTool) and its JSON API docs.
"""
import base64
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import zlib

MAX_CIPHERTEXT = 100_000      # bytes of paste JSON fetched
MAX_PLAINTEXT = 32_768        # bytes after decompression
FETCH_TIMEOUT = 20
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_PASTE_ID = re.compile(r"[0-9a-f]{16}")
_FRAGMENT = re.compile(r"-?[1-9A-HJ-NP-Za-km-z]{20,50}")
# A PrivateBin-shaped link anywhere in a message (the host is checked separately).
LINK_RE = re.compile(r"https?://[^\s<>|?#]+\?[0-9a-f]{16}#-?[1-9A-HJ-NP-Za-km-z]{20,50}")


class LinkUnusable(Exception):
    """The link or paste cannot be used: wrong host, malformed, expired, already read,
    unsupported options or a failed decryption. The message is safe to show the user."""


def b58decode(text: str) -> bytes:
    number = 0
    for char in text:
        index = _B58.find(char)
        if index < 0:
            raise ValueError("not base58")
        number = number * 58 + index
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\0" * (len(text) - len(text.lstrip("1"))) + body


def base_of(url: str) -> str:
    """Scheme, host and path of an instance URL, normalised for comparison."""
    parsed = urllib.parse.urlsplit(url.strip())
    path = parsed.path if parsed.path.endswith("/") else parsed.path + "/"
    return f"{parsed.scheme.lower()}://{(parsed.hostname or '').lower()}{'' if parsed.port in (None, 443, 80) else ':' + str(parsed.port)}{path}"


def parse_link(url: str, accepted: dict[str, str]) -> tuple[str, bytes]:
    """Map a user-supplied link to (fetch_url, key).

    ``accepted`` maps a public instance base (as ``base_of`` returns it) to the base the
    bot should fetch from; for the bot's own temporary instance that is the local
    container address, so the paste never round-trips through the public tunnel.
    """
    parsed = urllib.parse.urlsplit(url.strip())
    base = base_of(url)
    if (base not in accepted or parsed.scheme not in ("https", "http") or parsed.username
            or parsed.password or not _PASTE_ID.fullmatch(parsed.query or "")
            or not _FRAGMENT.fullmatch(parsed.fragment or "")):
        raise LinkUnusable("That link is not from the secure page I set up (or an allowed "
                           "PrivateBin instance), or it is incomplete.")
    if parsed.scheme == "http" and not accepted[base].startswith("http://127.0.0.1"):
        raise LinkUnusable("Only HTTPS PrivateBin links are accepted.")
    key = b58decode(parsed.fragment.removeprefix("-"))
    if len(key) > 32:
        raise LinkUnusable("The link's key is malformed.")
    return f"{accepted[base]}?pasteid={parsed.query}", key.rjust(32, b"\0")


def fetch(fetch_url: str, *, opener=None) -> dict:
    """GET the paste JSON once. No redirects, bounded size and time."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise LinkUnusable("The PrivateBin server redirected the request; refused.")

    opener = opener or urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(fetch_url, headers={
        "X-Requested-With": "JSONHttpRequest", "Accept": "application/json", "User-Agent": "codebot"})
    try:
        with opener.open(request, timeout=FETCH_TIMEOUT) as response:
            body = response.read(MAX_CIPHERTEXT + 1)
    except LinkUnusable:
        raise
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise LinkUnusable(f"Could not reach the PrivateBin page ({type(error).__name__}).") from None
    if len(body) > MAX_CIPHERTEXT:
        raise LinkUnusable("The paste is larger than a credential should be.")
    try:
        payload = json.loads(body)
    except ValueError:
        raise LinkUnusable("The PrivateBin page did not return a paste.") from None
    if not isinstance(payload, dict) or payload.get("status", 0) != 0:
        raise LinkUnusable("That paste no longer exists: it was already read or it expired.")
    return payload


def decode(payload: dict, key: bytes) -> str:
    """Decrypt a v2 paste. Raises LinkUnusable on anything unexpected."""
    try:
        if payload.get("v") != 2:
            raise ValueError("version")
        adata = payload["adata"]
        if not isinstance(adata, list) or len(adata) != 4:
            raise ValueError("adata")
        spec, formatter, discussion, burn = adata
        if formatter != "plaintext" and formatter not in ("syntaxhighlighting", "markdown"):
            raise ValueError("formatter")
        if discussion != 0 or burn != 1:
            raise LinkUnusable("Create the paste with 'Burn after reading' on and discussions off.")
        if (not isinstance(spec, list) or len(spec) != 8 or type(spec[2]) is not int
                or not 10_000 <= spec[2] <= 1_000_000 or spec[3:7] != [256, 128, "aes", "gcm"]
                or spec[7] not in ("none", "zlib")):
            raise ValueError("cipher spec")
        iv = base64.b64decode(spec[0], validate=True)
        salt = base64.b64decode(spec[1], validate=True)
        ciphertext = base64.b64decode(payload["ct"], validate=True)
        if len(iv) < 12 or len(salt) < 8 or not 16 < len(ciphertext) <= MAX_CIPHERTEXT:
            raise ValueError("sizes")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # lazy: import never fails
        derived = hashlib.pbkdf2_hmac("sha256", key, salt, spec[2], dklen=32)
        aad = json.dumps(adata, separators=(",", ":"), ensure_ascii=False).encode()
        plain = AESGCM(derived).decrypt(iv, ciphertext, aad)
        if spec[7] == "zlib":
            inflater = zlib.decompressobj(-zlib.MAX_WBITS)
            plain = inflater.decompress(plain, MAX_PLAINTEXT + 1)
            if len(plain) > MAX_PLAINTEXT or not inflater.eof:
                raise ValueError("decompressed size")
        elif len(plain) > MAX_PLAINTEXT:
            raise ValueError("size")
        content = json.loads(plain)
        if not isinstance(content, dict) or "attachment" in content:
            raise LinkUnusable("Paste only the secret text, without attachments.")
        text = content.get("paste")
        if not isinstance(text, str) or not text.strip() or "\0" in text:
            raise ValueError("empty")
        return text.strip()
    except LinkUnusable:
        raise
    except Exception:
        raise LinkUnusable("I could not decrypt that paste (wrong or incomplete link, or an "
                           "unsupported PrivateBin version).") from None
