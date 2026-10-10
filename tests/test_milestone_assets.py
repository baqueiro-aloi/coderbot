"""Pregenerated images are complete and identify the active lifecycle stage."""
import struct
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ASSETS = Path(__file__).resolve().parent.parent / "src" / "assets" / "milestones"
STAGES = ("exploring", "proposing", "approval", "implementing", "verifying",
          "archiving", "pr_review", "merged")


class MilestoneAssets(unittest.TestCase):
    def test_each_stage_has_accessible_vector_and_viewable_raster(self):
        self.assertEqual({p.stem for p in ASSETS.glob("*.svg")}, set(STAGES))
        self.assertEqual({p.stem for p in ASSETS.glob("*.png")}, set(STAGES))
        for index, stage in enumerate(STAGES):
            with self.subTest(stage=stage):
                root = ET.parse(ASSETS / f"{stage}.svg").getroot()
                self.assertIn(f"step {index + 1} of 8", root.attrib["aria-label"])
                circles = root.findall("{http://www.w3.org/2000/svg}circle")
                self.assertEqual(len(circles), 8)
                self.assertEqual(circles[index].attrib["fill"], "#155eef")
                raster = (ASSETS / f"{stage}.png").read_bytes()
                self.assertTrue(raster.startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertEqual(struct.unpack(">II", raster[16:24]), (1000, 140))
