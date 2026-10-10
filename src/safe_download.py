"""Bounded HTTPS downloads that never hand credentials to a foreign host.

Used for task-source attachments (issue screenshots, Jira images). The rules:
HTTPS only, no userinfo in the URL, the Authorization header is sent only to
explicitly allowed hosts and dropped on a redirect elsewhere, and both size and
time are capped. Any failure is a ``DownloadError`` (an ``OSError``), so callers'
existing best-effort ``except`` clauses keep treating a lost image as non-fatal.
"""
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
USER_AGENT = "codebot"


class DownloadError(OSError):
    pass


def host_allowed(hostname: str | None, allowed) -> bool:
    """Exact host match, or a subdomain of an allowed host."""
    if not hostname:
        return False
    hostname = hostname.lower()
    for entry in allowed:
        entry = (entry or "").lower().lstrip("*.")
        if entry and (hostname == entry or hostname.endswith("." + entry)):
            return True
    return False


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Follow a few HTTPS redirects; strip Authorization when leaving the allowed hosts."""

    def __init__(self, auth_hosts):
        self.auth_hosts = tuple(auth_hosts)
        self.hops = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hops += 1
        if self.hops > MAX_REDIRECTS:
            raise DownloadError(f"too many redirects (> {MAX_REDIRECTS})")
        target = urllib.parse.urlparse(newurl)
        if target.scheme != "https":
            raise DownloadError(f"redirect to non-HTTPS URL refused: {newurl}")
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and not host_allowed(target.hostname, self.auth_hosts):
            new.remove_header("Authorization")
        return new


def download(url: str, *, auth_hosts=(), authorization: str | None = None,
             max_bytes: int = MAX_BYTES, timeout: float = 30,
             content_type_prefix: str | None = None, opener=None) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise DownloadError(f"only HTTPS downloads are allowed: {url}")
    if parsed.username or parsed.password:
        raise DownloadError("credentials embedded in the URL are not allowed")
    if not parsed.hostname:
        raise DownloadError(f"URL has no host: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if authorization and host_allowed(parsed.hostname, auth_hosts):
        request.add_header("Authorization", authorization)
    if opener is None:
        opener = urllib.request.build_opener(_Redirects(auth_hosts))
    try:
        with opener.open(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > max_bytes:
                raise DownloadError(f"{url} is {length} bytes; limit is {max_bytes}")
            content_type = response.headers.get("Content-Type", "")
            if content_type_prefix and not content_type.startswith(content_type_prefix):
                raise DownloadError(f"{url} returned {content_type or 'no content type'}, "
                                    f"expected {content_type_prefix}*")
            data = response.read(max_bytes + 1)
    except DownloadError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise DownloadError(f"{url}: {error}") from error
    if len(data) > max_bytes:
        raise DownloadError(f"{url} exceeds the {max_bytes} byte download limit")
    return data
