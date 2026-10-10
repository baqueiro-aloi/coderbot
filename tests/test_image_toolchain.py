"""Ensure target image preparation has Buildx even with apt recommendations off."""
from pathlib import Path
import re
import unittest


DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


class ImageToolchainTests(unittest.TestCase):
    def test_buildx_is_installed_explicitly_with_docker_tools(self):
        text = DOCKERFILE.read_text().replace("\\\n", " ")
        install = re.search(r"apt-get install -y --no-install-recommends ([^&\n]*docker-ce-cli[^&\n]*)", text)
        self.assertIsNotNone(install)
        packages = install[1].split()
        self.assertIn("docker-compose-plugin", packages)
        self.assertIn("docker-buildx-plugin", packages)

    def test_buildx_is_checked_during_build_as_the_bot_user(self):
        text = DOCKERFILE.read_text()
        probe = "setpriv --reuid=bot --regid=bot --init-groups env HOME=/home/bot docker buildx version"
        self.assertIn("&& docker buildx version", text)
        self.assertIn("RUN " + probe, text)
        self.assertLess(text.index("RUN useradd"), text.index("RUN " + probe))


if __name__ == "__main__":
    unittest.main()
