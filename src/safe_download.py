"""Bounded public HTTPS downloads with DNS-pinned connections and scoped auth."""
import http.client
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit


class DownloadError(ValueError):
    """Deliberately contains no URL, headers or upstream error body."""


class PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname, address, *, timeout):
        super().__init__(hostname, timeout=timeout)
        self.address = address

    def connect(self):
        # Connect to the inspected address, keeping certificate/SNI validation on
        # the original hostname. A second DNS lookup would allow DNS rebinding.
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _target(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)
                or parsed.fragment or any(ord(c) <= 32 or ord(c) == 127 for c in url)):
            raise DownloadError('Download requires a public HTTPS URL without credentials or fragment')
        hostname = parsed.hostname.encode('idna').decode().lower()
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise DownloadError('Download destination is not public')
        return parsed, hostname, addresses[0][4][0]
    except (ValueError, OSError, UnicodeError) as error:
        if isinstance(error, DownloadError):
            raise
        raise DownloadError('Download destination could not be validated') from None


def _open(parsed, address, headers, timeout):
    connection = PublicHTTPSConnection(parsed.hostname, address, timeout=timeout)
    try:
        connection.request('GET', (parsed.path or '/') + ('?' + parsed.query if parsed.query else ''),
                           headers=headers)
        return connection, connection.getresponse()
    except BaseException:
        connection.close()
        raise


def download(url, *, authorization=None, auth_hosts=(), max_bytes=10 * 1024 * 1024,
              timeout=60, max_redirects=3, allowed_hosts=None, headers=None):
    """Never forward credentials after a cross-host redirect, even on return."""
    if max_bytes <= 0 or timeout <= 0 or max_redirects < 0:
        raise DownloadError('Invalid download limits')
    deadline = time.monotonic() + timeout
    previous_host = None
    auth_allowed = True

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise DownloadError('Download deadline exceeded')
        return value

    for hop in range(max_redirects + 1):
        remaining()
        parsed, hostname, address = _target(url)
        if allowed_hosts is not None and hostname not in allowed_hosts:
            raise DownloadError('Download destination is not authorized')
        if previous_host is not None and hostname != previous_host:
            auth_allowed = False
        previous_host = hostname
        request_headers = {'User-Agent': 'codebot', **(headers or {})}
        if any(name.lower() in ('authorization', 'cookie', 'host') for name in (headers or {})):
            raise DownloadError('Sensitive headers require scoped authorization')
        if any(not isinstance(value, str) or '\r' in value or '\n' in value
               for value in request_headers.values()):
            raise DownloadError('Invalid download headers')
        if authorization and auth_allowed and hostname in auth_hosts:
            request_headers['Authorization'] = authorization
        try:
            connection, response = _open(parsed, address, request_headers, remaining())
            try:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location or hop == max_redirects:
                        raise DownloadError('Download redirect limit or invalid redirect')
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise DownloadError(f'Download HTTP {response.status}')
                length = response.getheader('Content-Length')
                if length is not None and (not length.isdigit() or int(length) > max_bytes):
                    raise DownloadError('Download size limit or invalid length')
                data = bytearray()
                while True:
                    budget = remaining()
                    if connection.sock is not None:
                        connection.sock.settimeout(budget)
                    chunk = response.read(min(65536, max_bytes + 1 - len(data)))
                    remaining()
                    if not chunk:
                        return bytes(data)
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise DownloadError('Download size limit exceeded')
            finally:
                response.close()
                connection.close()
        except (OSError, http.client.HTTPException):
            raise DownloadError('Download transport failed') from None
    raise DownloadError('Download redirect limit exceeded')


def google_image_host(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    return parsed.scheme == 'https' and (host == 'googleusercontent.com' or
                                        host.endswith('.googleusercontent.com'))
