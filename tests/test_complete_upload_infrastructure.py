import tempfile
import unittest
from pathlib import Path

from evodox.jobs.infrastructure import InMemoryQueuePublisher, OutboxQueueDispatcher, SQLiteOutbox


class OutboxInfrastructureTests(unittest.TestCase):
    def test_sqlite_outbox_appends_and_lists_pending_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            outbox = SQLiteOutbox(db_path)
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_1",
                    "queue": "gpu-standard",
                    "payload": {"k": "v"},
                }
            )

            events = outbox.list_pending(limit=10)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "job.queued")
            self.assertEqual(events[0]["tenant_id"], "tenant-a")

    def test_outbox_dispatcher_publishes_and_marks_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            outbox = SQLiteOutbox(db_path)
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_2",
                    "queue": "gpu-standard",
                    "payload": {"job_id": "job_2"},
                }
            )
            publisher = InMemoryQueuePublisher()
            dispatcher = OutboxQueueDispatcher(outbox=outbox, queue_publisher=publisher)

            published = dispatcher.dispatch_pending(limit=10)

            self.assertEqual(published, 1)
            self.assertEqual(len(publisher.messages), 1)
            self.assertEqual(outbox.list_pending(limit=10), [])



if __name__ == "__main__":
    unittest.main()
