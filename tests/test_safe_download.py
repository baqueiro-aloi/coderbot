"""safe_download: HTTPS only, bounded, credentials only to allowed hosts."""
import io
import unittest
import urllib.request
from unittest.mock import patch

import github_projects_client as ghp
import safe_download
from safe_download import DownloadError, download, host_allowed


class FakeResponse(io.BytesIO):
    def __init__(self, data=b"img", headers=None):
        super().__init__(data)
        self.headers = {"Content-Type": "image/png", **(headers or {})}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        return self.response


class Download(unittest.TestCase):
    def test_rejects_http_userinfo_and_hostless_urls(self):
        for url in ("http://example.com/a.png", "https://user:pw@example.com/a.png", "https:///a.png"):
            with self.subTest(url=url), self.assertRaises(DownloadError):
                download(url, opener=FakeOpener(FakeResponse()))

    def test_authorization_only_for_allowed_hosts(self):
        opener = FakeOpener(FakeResponse())
        download("https://attacker.example/github.png", auth_hosts=("github.com", "githubusercontent.com"),
                 authorization="Bearer tok", opener=opener)
        self.assertFalse(opener.requests[0].has_header("Authorization"))
        opener = FakeOpener(FakeResponse())
        download("https://private-user-images.githubusercontent.com/x.png",
                 auth_hosts=("github.com", "githubusercontent.com"), authorization="Bearer tok", opener=opener)
        self.assertEqual(opener.requests[0].get_header("Authorization"), "Bearer tok")

    def test_size_and_content_type_limits(self):
        with self.assertRaisesRegex(DownloadError, "limit"):
            download("https://x.example/a", max_bytes=3, opener=FakeOpener(FakeResponse(b"1234")))
        with self.assertRaisesRegex(DownloadError, "bytes"):
            download("https://x.example/a", max_bytes=3,
                     opener=FakeOpener(FakeResponse(b"1", {"Content-Length": "99"})))
        with self.assertRaisesRegex(DownloadError, "expected image/"):
            download("https://x.example/a", content_type_prefix="image/",
                     opener=FakeOpener(FakeResponse(b"<html>", {"Content-Type": "text/html"})))
        self.assertEqual(download("https://x.example/a", max_bytes=4, opener=FakeOpener(FakeResponse(b"1234"))), b"1234")

    def test_transport_errors_become_download_errors(self):
        class Boom:
            def open(self, request, timeout=None):
                raise OSError("connection reset")
        with self.assertRaisesRegex(DownloadError, "connection reset"):
            download("https://x.example/a", opener=Boom())

    def test_redirect_strips_authorization_off_allowed_hosts_and_refuses_http(self):
        handler = safe_download._Redirects(("github.com",))
        request = urllib.request.Request("https://github.com/a.png")
        request.add_header("Authorization", "Bearer tok")
        kept = handler.redirect_request(request, None, 302, "Found", {}, "https://api.github.com/b.png")
        self.assertEqual(kept.get_header("Authorization"), "Bearer tok")
        dropped = handler.redirect_request(request, None, 302, "Found", {}, "https://cdn.example/b.png")
        self.assertFalse(dropped.has_header("Authorization"))
        with self.assertRaises(DownloadError):
            handler.redirect_request(request, None, 302, "Found", {}, "http://github.com/b.png")
        handler.hops = safe_download.MAX_REDIRECTS
        with self.assertRaises(DownloadError):
            handler.redirect_request(request, None, 302, "Found", {}, "https://github.com/c.png")

    def test_host_allowed_matches_exact_and_subdomains_only(self):
        self.assertTrue(host_allowed("github.com", ("github.com",)))
        self.assertTrue(host_allowed("objects.githubusercontent.com", ("githubusercontent.com",)))
        self.assertFalse(host_allowed("notgithub.com", ("github.com",)))
        self.assertFalse(host_allowed("github.com.evil.example", ("github.com",)))
        self.assertFalse(host_allowed(None, ("github.com",)))


class GitHubImages(unittest.TestCase):
    def test_lost_image_does_not_block_the_item_and_token_targets_github_only(self):
        import tempfile
        from pathlib import Path
        task = {"number": 7, "body": "![a](https://evil.example/github.png) ![b](https://github.com/u/b.png)"}
        calls = []

        def fake(url, **kwargs):
            calls.append((url, kwargs))
            if "evil" in url:
                raise DownloadError("refused")
            return b"png"

        with tempfile.TemporaryDirectory() as tmp, patch.object(ghp, "IMAGES_DIR", Path(tmp)), \
                patch.object(ghp.safe_download, "download", side_effect=fake), \
                patch.dict("os.environ", {"GH_TOKEN": "ghp_token"}):
            paths = ghp._download_images(task)
        self.assertEqual(len(paths), 1)
        self.assertEqual([c[1]["auth_hosts"] for c in calls], [ghp.GITHUB_IMAGE_HOSTS] * 2)
        self.assertEqual(calls[1][1]["authorization"], "Bearer ghp_token")


if __name__ == "__main__":
    unittest.main()
