from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import gdoc_client


class DocsErrorTests(unittest.TestCase):
    def test_400_requires_actual_revision_change(self):
        class HttpError(Exception):
            resp = SimpleNamespace(status=400)
        for fresh, stale in [({'revisionId': 'new'}, True), ({'revisionId': 'old'}, False), ({}, False), ([], False)]:
            service = Mock()
            error = HttpError('Invalid request')
            service.documents.return_value.batchUpdate.return_value.execute.side_effect = error
            service.documents.return_value.get.return_value.execute.return_value = fresh
            with self.subTest(fresh=fresh), patch.object(gdoc_client, 'HttpError', HttpError):
                if stale:
                    self.assertFalse(gdoc_client._cas_update(service, {'revisionId': 'old'}, []))
                else:
                    with self.assertRaises(HttpError):
                        gdoc_client._cas_update(service, {'revisionId': 'old'}, [])
            service.documents.return_value.batchUpdate.assert_called_once()
