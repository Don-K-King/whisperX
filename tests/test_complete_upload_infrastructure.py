import tempfile
import unittest
from pathlib import Path

from evodox.jobs.infrastructure import (
    DuplicateDeliveryError,
    InMemoryQueueDispatchMetrics,
    InMemoryQueuePublisher,
    OutboxQueueDispatcher,
    RetryablePublishError,
    SQLiteOutbox,
    TerminalPublishError,
)


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

    def test_sqlite_outbox_can_filter_pending_events_by_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            outbox = SQLiteOutbox(db_path)
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_gpu",
                    "queue": "gpu-standard",
                    "payload": {"job_id": "job_gpu"},
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_cpu",
                    "queue": "cpu-short",
                    "payload": {"job_id": "job_cpu"},
                }
            )

            gpu_events = outbox.list_pending(limit=10, queues=("gpu-standard",))

            self.assertEqual(len(gpu_events), 1)
            self.assertEqual(gpu_events[0]["job_id"], "job_gpu")

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

    def test_dispatcher_retries_retryable_errors_with_backoff_and_jitter(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            outbox = SQLiteOutbox(db_path)
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_3",
                    "queue": "gpu-standard",
                    "payload": {"job_id": "job_3"},
                }
            )
            publisher = _FlakyPublisher([RetryablePublishError("network.timeout"), None])
            metrics = InMemoryQueueDispatchMetrics()
            clock = _StepClock([100, 101, 102])
            dispatcher = OutboxQueueDispatcher(
                outbox=outbox,
                queue_publisher=publisher,
                metrics=metrics,
                now_factory=clock.now,
                jitter_factory=lambda lower, upper: upper,
            )

            first_run = dispatcher.dispatch_pending(limit=10)
            second_run = dispatcher.dispatch_pending(limit=10)

            self.assertEqual(first_run, 0)
            self.assertEqual(second_run, 1)
            self.assertEqual(metrics.retry_count, 1)
            self.assertEqual(len(outbox.list_pending(limit=10)), 0)

    def test_dispatcher_routes_terminal_error_to_dlq(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            outbox = SQLiteOutbox(db_path)
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_4",
                    "queue": "gpu-standard",
                    "payload": {"job_id": "job_4"},
                }
            )
            publisher = _FlakyPublisher([TerminalPublishError("validation.invalid_payload")])
            metrics = InMemoryQueueDispatchMetrics()
            dispatcher = OutboxQueueDispatcher(
                outbox=outbox,
                queue_publisher=publisher,
                metrics=metrics,
                now_factory=lambda: _fixed_timestamp(100),
            )

            published = dispatcher.dispatch_pending(limit=10)

            self.assertEqual(published, 0)
            self.assertEqual(metrics.dlq_count, 1)
            self.assertEqual(len(outbox.list_pending(limit=10)), 0)
            dlq_events = outbox.list_dlq(limit=10)
            self.assertEqual(len(dlq_events), 1)
            self.assertEqual(dlq_events[0]["last_error_code"], "validation.invalid_payload")

    def test_dispatcher_marks_duplicate_delivery_as_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "evodox.db"
            outbox = SQLiteOutbox(db_path)
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_5",
                    "queue": "gpu-standard",
                    "payload": {"job_id": "job_5"},
                }
            )
            publisher = _FlakyPublisher([DuplicateDeliveryError("duplicate.delivery")])
            dispatcher = OutboxQueueDispatcher(outbox=outbox, queue_publisher=publisher, now_factory=lambda: _fixed_timestamp(100))

            published = dispatcher.dispatch_pending(limit=10)

            self.assertEqual(published, 0)
            self.assertEqual(len(outbox.list_pending(limit=10)), 0)
            self.assertEqual(len(outbox.list_dlq(limit=10)), 0)


class _FlakyPublisher:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    def publish(self, queue_name: str, payload: dict, *, message_id: str | None = None, headers: dict | None = None):
        del queue_name, payload, message_id, headers
        result = self._outcomes.pop(0)
        if isinstance(result, Exception):
            raise result


def _fixed_timestamp(value: int):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value, tz=timezone.utc)


class _StepClock:
    def __init__(self, values):
        self._values = list(values)
        self._idx = 0

    def now(self):
        idx = min(self._idx, len(self._values) - 1)
        self._idx += 1
        return _fixed_timestamp(self._values[idx])



if __name__ == "__main__":
    unittest.main()
