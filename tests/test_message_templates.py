import unittest
from message_templates import translate


class TemplateTests(unittest.TestCase):
    def test_static_task_copy_is_deterministic_and_dynamic_is_explicit(self):
        self.assertEqual(translate("Verification", "Spanish"), "Verificación")
        self.assertIsNone(translate("Dynamic report", "Spanish"))
        self.assertEqual(translate("Dynamic report", "English"), "Dynamic report")
