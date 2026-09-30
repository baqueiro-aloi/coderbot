"""Deployment must preserve mount sources resolved before sudo/Compose expansion."""
from pathlib import Path
import unittest

from scripts.rollout_performance import preserved_mounts


class RolloutMountTests(unittest.TestCase):
    def test_release_changes_only_app_mount_and_rollback_restores_original_sources(self):
        inspected = {"Mounts": [
            {"Type": "bind", "Source": "/home/azureuser/app", "Destination": "/app", "RW": True},
            {"Type": "bind", "Source": "/home/azureuser/app/data", "Destination": "/app/data", "RW": True},
            {"Type": "bind", "Source": "/home/azureuser/.npmrc", "Destination": "/seed/.npmrc", "RW": False},
            {"Type": "bind", "Source": "/home/azureuser/target", "Destination": "/home/azureuser/target", "RW": True},
        ]}
        original = preserved_mounts(inspected)
        release = preserved_mounts(inspected, Path("/home/azureuser/release"))
        self.assertEqual(release[0]["source"], "/home/azureuser/release")
        self.assertEqual(release[1:], original[1:])
        self.assertEqual(original[0]["source"], "/home/azureuser/app")
        self.assertTrue(release[2]["read_only"])
