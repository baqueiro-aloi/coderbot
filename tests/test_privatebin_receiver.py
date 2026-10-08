import base64
import copy
import json
import subprocess
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile

import base58
from pbincli.format import Paste
from privatebin_receiver import decode, link, receive
from private_secrets import SecretUnavailable, PrivateSecrets
from check_plan import Check
import secret_safety


class PrivateBinTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(secret_safety.clear)

    def vector(self, compression='none'):
        paste = Paste()
        paste.setCompression(compression)
        paste.setText('synthetic-privatebin-value')
        paste.encrypt('plaintext', True, False, '5min')
        return json.loads(paste.getJSON()), paste.getHash()

    def test_pinned_client_none_and_deflate_compatibility(self):
        for compression in ('none', 'zlib'):
            with self.subTest(compression=compression):
                payload, key = self.vector(compression)
                self.assertEqual(decode(payload, key), 'synthetic-privatebin-value')

    def test_independent_webcrypto_vector_matches_official_v2_contract(self):
        script = """
import {webcrypto} from 'node:crypto';
const key=Buffer.alloc(32,1), iv=Buffer.alloc(16,2), salt=Buffer.alloc(8,3);
const adata=[[iv.toString('base64'),salt.toString('base64'),100000,256,128,'aes','gcm','none'],'plaintext',0,1];
const material=await webcrypto.subtle.importKey('raw',key,'PBKDF2',false,['deriveKey']);
const aes=await webcrypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',salt,iterations:100000},material,{name:'AES-GCM',length:256},false,['encrypt']);
const ct=await webcrypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:Buffer.from(JSON.stringify(adata)),tagLength:128},aes,Buffer.from(JSON.stringify({paste:'synthetic-node-value'})));
console.log(JSON.stringify({v:2,adata,ct:Buffer.from(ct).toString('base64')}));
"""
        result = subprocess.run(['node', '--input-type=module', '-e', script],
                                capture_output=True, text=True, check=True, timeout=15)
        self.assertEqual(decode(json.loads(result.stdout), base58.b58encode(bytes([1]) * 32).decode()),
                         'synthetic-node-value')

    def test_tampered_adata_cipher_and_unsupported_protocol_rejected(self):
        payload, key = self.vector()
        for mutation in (lambda p: p.update(v=1), lambda p: p['adata'].__setitem__(3, 0),
                         lambda p: p['adata'][0].__setitem__(2, 10000000),
                         lambda p: p.update(ct=base64.b64encode(b'tampered ciphertext').decode())):
            value = copy.deepcopy(payload)
            mutation(value)
            with self.assertRaises(SecretUnavailable):
                decode(value, key)

    def test_decompression_bomb_rejected(self):
        paste = Paste()
        paste.setText('x' * 1000000)
        paste.encrypt('plaintext', True, False, '5min')
        with self.assertRaises(SecretUnavailable):
            decode(json.loads(paste.getJSON()), paste.getHash())

    def test_exact_instance_and_fragment_not_in_transport_url(self):
        url = 'https://bin.example/private/?0123456789abcdef#' + base58.b58encode(bytes([1]) * 32).decode()
        target, key = link(url, ['https://bin.example/private/'])
        self.assertEqual(target, 'https://bin.example/private/?pasteid=0123456789abcdef')
        self.assertNotIn('#', target)
        self.assertNotIn(url, secret_safety.redact(url))
        for bad in (url.replace('bin.example', 'evil.example'), url.replace('/private/', '/other/'),
                    url.replace('https:', 'http:'), url.replace('?0123', '?extra=0123')):
            with self.assertRaises(SecretUnavailable):
                link(bad, ['https://bin.example/private/'])

    def test_receiver_transport_and_private_provisioning_contract(self):
        payload, key = self.vector()
        url = 'https://bin.example/private/?0123456789abcdef#' + key
        with tempfile.TemporaryDirectory() as root, patch('safe_download.download', return_value=json.dumps(payload).encode()) as download:
            private = PrivateSecrets(Path(root) / 'private')
            check = Check('live', ['test'], env_keys=['SERVICE_KEY'])
            handle = receive(url, ['https://bin.example/private/'], private,
                task_id='task', check=check, env_key='SERVICE_KEY')
            self.assertEqual(private.resolve(handle, task_id='task', check=check)[1], 'synthetic-privatebin-value')
            self.assertEqual(download.call_args.kwargs['max_redirects'], 0)
            self.assertEqual(download.call_args.kwargs['allowed_hosts'], ['bin.example'])
            self.assertNotIn(key, download.call_args.args[0])
