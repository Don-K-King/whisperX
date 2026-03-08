import unittest

from evodox.jobs.export_service import ExportQueuedResponse
from evodox.web.fastapi_adapter import map_export_response


class ExportHttpAdapterTests(unittest.TestCase):
    def test_maps_export_response(self):
        payload = map_export_response(ExportQueuedResponse(export_id="exp_1", status="queued"))
        self.assertEqual(payload["export_id"], "exp_1")
        self.assertEqual(payload["status"], "queued")


if __name__ == "__main__":
    unittest.main()
