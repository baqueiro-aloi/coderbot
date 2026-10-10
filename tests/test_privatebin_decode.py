"""PrivateBin v2 decryption against a real server capture and independent WebCrypto vectors."""
import base64
import copy
import io
import json
import shutil
import subprocess
import unittest
import zlib
from pathlib import Path

import privatebin
from privatebin import LinkUnusable, b58decode, decode, fetch, parse_link

FIXTURE = json.loads((Path(__file__).parent / "fixtures/privatebin_v2.json").read_text())
LOCAL = {"http://127.0.0.1:48081/": "http://127.0.0.1:48081/"}

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data: bytes) -> str:
    number, out = int.from_bytes(data, "big"), ""
    while number:
        number, rem = divmod(number, 58)
        out = _B58[rem] + out
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + out


def encrypt(text, key, *, compression="zlib", burn=1, extra=None, iterations=100000):
    """Reference encryptor written from the protocol description (not the decoder)."""
    import hashlib
    import os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    iv, salt = os.urandom(16), os.urandom(8)
    adata = [[base64.b64encode(iv).decode(), base64.b64encode(salt).decode(), iterations, 256, 128,
              "aes", "gcm", compression], "plaintext", 0, burn]
    body = json.dumps({"paste": text, **(extra or {})}).encode()
    if compression == "zlib":
        deflater = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        body = deflater.compress(body) + deflater.flush()
    aes = hashlib.pbkdf2_hmac("sha256", key, salt, iterations, dklen=32)
    ct = AESGCM(aes).encrypt(iv, body, json.dumps(adata, separators=(",", ":")).encode())
    return {"v": 2, "adata": adata, "ct": base64.b64encode(ct).decode(), "meta": {}}


class RealServer(unittest.TestCase):
    def test_captured_paste_decrypts(self):
        url, key = parse_link(FIXTURE["link"], LOCAL)
        self.assertEqual(url, "http://127.0.0.1:48081/?pasteid=a5dfe97e7615aff2")
        self.assertEqual(decode(FIXTURE["payload"], key), FIXTURE["plaintext"])

    def test_burned_paste_is_reported_as_gone(self):
        class Opener:
            def open(self, request, timeout=None):
                self.request = request
                return _Response(json.dumps(FIXTURE["burned_response"]).encode())
        opener = Opener()
        with self.assertRaisesRegex(LinkUnusable, "already read or it expired"):
            fetch("http://127.0.0.1:48081/?pasteid=a5dfe97e7615aff2", opener=opener)
        self.assertEqual(opener.request.get_header("X-requested-with"), "JSONHttpRequest")


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@unittest.skipUnless(shutil.which("node"), "node is required for the WebCrypto vectors")
class WebCryptoVectors(unittest.TestCase):
    """Encrypted by Node's WebCrypto exactly as PrivateBin's browser code does."""
    SCRIPT = """
import {webcrypto} from 'node:crypto'; import zlib from 'node:zlib';
const compression = process.argv[1];
const key=Buffer.alloc(32,1), iv=Buffer.alloc(16,2), salt=Buffer.alloc(8,3);
const adata=[[iv.toString('base64'),salt.toString('base64'),100000,256,128,'aes','gcm',compression],'plaintext',0,1];
const material=await webcrypto.subtle.importKey('raw',key,'PBKDF2',false,['deriveKey']);
const aes=await webcrypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',salt,iterations:100000},material,{name:'AES-GCM',length:256},false,['encrypt']);
let body=Buffer.from(JSON.stringify({paste:'synthetic-node-value'}));
if (compression==='zlib') body=zlib.deflateRawSync(body);
const ct=await webcrypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:Buffer.from(JSON.stringify(adata)),tagLength:128},aes,body);
console.log(JSON.stringify({v:2,adata,ct:Buffer.from(ct).toString('base64')}));
"""

    def test_none_and_zlib(self):
        for compression in ("none", "zlib"):
            with self.subTest(compression=compression):
                out = subprocess.run(["node", "--input-type=module", "-e", self.SCRIPT, compression],
                                     capture_output=True, text=True, check=True, timeout=30).stdout
                self.assertEqual(decode(json.loads(out), bytes([1]) * 32), "synthetic-node-value")


class Rejections(unittest.TestCase):
    key = bytes(range(32))

    def test_round_trip(self):
        for compression in ("none", "zlib"):
            self.assertEqual(decode(encrypt("s3cret", self.key, compression=compression), self.key), "s3cret")

    def test_tampering_wrong_key_and_unsupported_options(self):
        payload = encrypt("s3cret", self.key)
        mutations = (lambda p: p.update(v=1), lambda p: p["adata"].__setitem__(1, "bogus"),
                     lambda p: p["adata"][0].__setitem__(2, 10), lambda p: p.update(ct="AAAA"),
                     lambda p: p["adata"][0].__setitem__(5, "des"))
        for mutate in mutations:
            value = copy.deepcopy(payload)
            mutate(value)
            with self.assertRaises(LinkUnusable):
                decode(value, self.key)
        with self.assertRaises(LinkUnusable):
            decode(payload, bytes(32))

    def test_requires_burn_after_reading_and_no_attachments(self):
        with self.assertRaisesRegex(LinkUnusable, "Burn after reading"):
            decode(encrypt("s", self.key, burn=0), self.key)
        with self.assertRaisesRegex(LinkUnusable, "attachments"):
            decode(encrypt("s", self.key, extra={"attachment": "data:..."}), self.key)

    def test_decompression_bomb(self):
        with self.assertRaises(LinkUnusable):
            decode(encrypt("x" * 200_000, self.key), self.key)


class Links(unittest.TestCase):
    key = b58encode(bytes([7]) * 32)

    def test_accepted_hosts_only_and_local_fetch_rewrite(self):
        accepted = {"https://abc123.lhr.life/": "http://127.0.0.1:48080/",
                    "https://bin.example/private/": "https://bin.example/private/"}
        url, key = parse_link(f"https://abc123.lhr.life/?0123456789abcdef#{self.key}", accepted)
        self.assertEqual(url, "http://127.0.0.1:48080/?pasteid=0123456789abcdef")
        self.assertEqual(key, bytes([7]) * 32)
        url, _ = parse_link(f"https://bin.example/private/?0123456789abcdef#{self.key}", accepted)
        self.assertEqual(url, "https://bin.example/private/?pasteid=0123456789abcdef")
        for bad in (f"https://evil.example/?0123456789abcdef#{self.key}",
                    f"http://bin.example/private/?0123456789abcdef#{self.key}",
                    f"https://u:p@bin.example/private/?0123456789abcdef#{self.key}",
                    f"https://bin.example/private/?0123456789abcdeX#{self.key}",
                    "https://bin.example/private/?0123456789abcdef#0OIl"):
            with self.subTest(bad=bad), self.assertRaises(LinkUnusable):
                parse_link(bad, accepted)

    def test_short_keys_are_left_padded(self):
        short = b58encode(bytes([5]) * 20)
        _, key = parse_link(f"https://bin.example/?0123456789abcdef#{short}",
                            {"https://bin.example/": "https://bin.example/"})
        self.assertEqual(key, bytes(12) + bytes([5]) * 20)

    def test_b58_round_trip_and_link_regex(self):
        data = b"\0\0" + bytes(range(1, 30))
        self.assertEqual(b58decode(b58encode(data)), data)
        text = f"here it is https://abc.lhr.life/?0123456789abcdef#{self.key} thanks"
        self.assertEqual(len(privatebin.LINK_RE.findall(text)), 1)


if __name__ == "__main__":
    unittest.main()
