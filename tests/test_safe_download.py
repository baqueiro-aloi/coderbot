"""Download policy tests use injected responses, never external requests."""
import socket
import unittest
from unittest.mock import Mock, patch

import safe_download


PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))]


class Response:
    def __init__(self, data=b'image', status=200, headers=None):
        self.data, self.status = data, status
        self.headers = headers or {}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, size):
        part, self.data = self.data[:size], self.data[size:]
        return part

    def close(self):
        pass


class SafeDownloadTests(unittest.TestCase):
    def setUp(self):
        dns = patch('safe_download.socket.getaddrinfo', return_value=PUBLIC)
        dns.start()
        self.addCleanup(dns.stop)

    def test_foreign_host_never_receives_auth_even_with_github_in_path(self):
        with patch('safe_download._open', return_value=(Mock(), Response())) as send:
            safe_download.download('https://attacker.example/github.png',
                authorization='Bearer synthetic', auth_hosts={'github.com'})
        self.assertNotIn('Authorization', send.call_args.args[2])

    def test_authorized_host_receives_auth_and_redirect_loses_it_permanently(self):
        responses = [(Mock(), Response(status=302, headers={'Location': 'https://cdn.example/a'})),
                     (Mock(), Response(status=302, headers={'Location': 'https://github.com/b'})),
                     (Mock(), Response())]
        with patch('safe_download._open', side_effect=responses) as send:
            self.assertEqual(safe_download.download('https://github.com/a',
                authorization='Bearer synthetic', auth_hosts={'github.com'}), b'image')
        self.assertEqual(send.call_args_list[0].args[2]['Authorization'], 'Bearer synthetic')
        for call in send.call_args_list[1:]:
            self.assertNotIn('Authorization', call.args[2])

    def test_rejects_private_mixed_dns_and_unsafe_urls_before_connect(self):
        for url in ('http://github.com/a', 'https://user:pass@github.com/a',
                    'https://github.com:444/a', 'https://github.com/a#secret',
                    'https://github.com/a\nheader'):
            with self.subTest(url=url), patch('safe_download._open') as send:
                with self.assertRaises(safe_download.DownloadError):
                    safe_download.download(url)
                send.assert_not_called()
        mixed = PUBLIC + [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        with patch('safe_download.socket.getaddrinfo', return_value=mixed), \
             patch('safe_download._open') as send:
            with self.assertRaises(safe_download.DownloadError):
                safe_download.download('https://github.com/a')
            send.assert_not_called()

    def test_redirect_private_destination_is_rejected(self):
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('169.254.169.254', 443))]
        with patch('safe_download.socket.getaddrinfo', side_effect=[PUBLIC, private]), \
             patch('safe_download._open', return_value=(Mock(), Response(status=302,
                 headers={'Location': 'https://metadata.example/'}))) as send:
            with self.assertRaises(safe_download.DownloadError):
                safe_download.download('https://github.com/a')
        self.assertEqual(send.call_count, 1)

    def test_size_redirect_status_and_aggregate_timeout_limits(self):
        for response in (Response(b'12345'), Response(headers={'Content-Length': '100'}),
                         Response(status=403), Response(status=302)):
            with self.subTest(response=response), \
                 patch('safe_download._open', return_value=(Mock(), response)):
                with self.assertRaises(safe_download.DownloadError):
                    safe_download.download('https://github.com/a', max_bytes=4)
        with patch('safe_download._open', return_value=(Mock(), Response(status=302,
            headers={'Location': '/next'}))) as send:
            with self.assertRaises(safe_download.DownloadError):
                safe_download.download('https://github.com/a', max_redirects=1)
            self.assertEqual(send.call_count, 2)
        with patch('safe_download.time.monotonic', side_effect=[0, 100]), \
             patch('safe_download._open') as send:
            with self.assertRaises(safe_download.DownloadError):
                safe_download.download('https://github.com/a', timeout=1)
            send.assert_not_called()

    def test_connect_uses_validated_ip_but_original_tls_hostname(self):
        connection = safe_download.PublicHTTPSConnection('github.com', '8.8.8.8', timeout=1)
        sock = Mock()
        with patch('safe_download.socket.create_connection', return_value=sock) as connect, \
             patch.object(connection._context, 'wrap_socket', return_value=sock) as tls:
            connection.connect()
        self.assertEqual(connect.call_args.args[0], ('8.8.8.8', 443))
        self.assertEqual(tls.call_args.kwargs['server_hostname'], 'github.com')

    def test_host_policy_has_label_boundaries(self):
        self.assertTrue(safe_download.google_image_host('https://lh3.googleusercontent.com/a'))
        for url in ('https://googleusercontent.com.evil.example/a',
                    'https://evilgoogleusercontent.com/a', 'http://lh3.googleusercontent.com/a'):
            self.assertFalse(safe_download.google_image_host(url))

    def test_restricted_receiver_host_and_headers_fail_before_connection(self):
        for kwargs in ({'allowed_hosts': ['trusted.example']},
                       {'headers': {'Authorization': 'Bearer secret'}},
                       {'headers': {'Accept': 'json\r\nCookie: secret'}}):
            with self.subTest(kwargs=kwargs), patch('safe_download._open') as connect:
                with self.assertRaises(safe_download.DownloadError):
                    safe_download.download('https://other.example/paste', **kwargs)
                connect.assert_not_called()

    def test_github_client_routes_download_through_scoped_policy(self):
        import tempfile
        from pathlib import Path
        import github_projects_client as github
        with tempfile.TemporaryDirectory() as root, patch.object(github, 'IMAGES_DIR', Path(root)), \
             patch.dict('os.environ', {'GH_TOKEN': 'synthetic-token'}), \
             patch('safe_download.download', return_value=b'image') as download:
            files = github._download_images({'number': 1,
                'body': '![image](https://attacker.example/github.png)'})
            self.assertEqual(Path(files[0]).read_bytes(), b'image')
            self.assertEqual(download.call_args.kwargs['auth_hosts'], {'github.com', 'api.github.com'})

    def test_google_client_rejects_foreign_and_uses_scoped_policy(self):
        import tempfile
        from pathlib import Path
        import tests.test_gdoc_client
        import gdoc_client as google
        document = {'inlineObjects': {'image': {'inlineObjectProperties': {
            'embeddedObject': {'imageProperties': {'contentUri': 'https://lh3.googleusercontent.com/a'}}}}}}
        with tempfile.TemporaryDirectory() as root, patch.object(google, 'IMAGES_DIR', Path(root)), \
             patch.object(google, 'load_credentials', return_value=Mock(valid=True, token='synthetic-token')), \
             patch('safe_download.download', return_value=b'image') as download:
            self.assertEqual(len(google._download_images(document, ['image'])), 1)
            self.assertEqual(download.call_args.kwargs['auth_hosts'], {'lh3.googleusercontent.com'})
            document['inlineObjects']['image']['inlineObjectProperties']['embeddedObject']['imageProperties']['contentUri'] = 'https://attacker.example/a'
            errors = []
            self.assertEqual(google._download_images(document, ['image'], errors), [])
            self.assertEqual(errors, [{'id': 'image', 'category': 'unavailable'}])
            self.assertEqual(download.call_count, 1)
