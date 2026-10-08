import unittest
from unittest.mock import Mock

import drive_client


class DrivePayloadContractTests(unittest.TestCase):
    def test_collections_and_ids_are_not_inferred_from_missing_payload(self):
        for value in ({}, {'files': None}, {'files': [{}]}, {'files': [None]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                drive_client._collection(value, 'files') if value.get('files') != [{}] else drive_client._id(value['files'][0])

    def test_missing_permission_collection_does_not_verify_access(self):
        service = Mock()
        service.files.return_value.get.return_value.execute.return_value = {
            'id': 'file', 'parents': ['folder'], 'trashed': False}
        service.permissions.return_value.list.return_value.execute.return_value = {}
        with self.assertRaises(ValueError):
            drive_client.verify_inherited(service, 'file', 'folder')
