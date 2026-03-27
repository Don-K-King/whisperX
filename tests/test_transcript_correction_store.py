import sqlite3
import tempfile
import unittest
from pathlib import Path

from evodox.jobs.transcript_correction_store import SQLiteTranscriptCorrectionStore


class TranscriptCorrectionStoreTests(unittest.TestCase):
    def test_session_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteTranscriptCorrectionStore(Path(tmp) / 'jobs.db')
            payload = {
                'session_id': 'cs_1',
                'job_id': 'job_1',
                'actor_id': 'u-1',
                'base_version': 1,
                'autosave_enabled': True,
                'speaker_labels': {'S1': 'Alice'},
                'review_status': 'in_review',
                'is_final': False,
                'history_index': 0,
                'history': [{'segments': [{'segment_id': 'seg_1', 'start': 0.0, 'end': 1.0, 'speaker': 'S1', 'text': 'Hallo'}], 'summary': None}],
                'updated_at': '2026-03-24T00:00:00+00:00',
                'created_at': '2026-03-24T00:00:00+00:00',
            }
            store.create_session(tenant_id='tenant-a', payload=payload)
            loaded = store.get_session(tenant_id='tenant-a', session_id='cs_1')
            assert loaded is not None
            self.assertTrue(loaded['autosave_enabled'])
            self.assertEqual(loaded['speaker_labels']['S1'], 'Alice')

    def test_status_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteTranscriptCorrectionStore(Path(tmp) / 'jobs.db')
            updated = store.set_status(
                tenant_id='tenant-a',
                job_id='job_1',
                review_status='reviewed',
                is_final=True,
                actor_id='u-1',
            )
            self.assertEqual(updated['review_status'], 'reviewed')
            self.assertTrue(updated['is_final'])
            fetched = store.get_status(tenant_id='tenant-a', job_id='job_1')
            self.assertEqual(fetched['final_set_by'], 'u-1')

    def test_legacy_session_schema_gets_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'jobs.db'
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """
                CREATE TABLE transcript_correction_sessions (
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    base_version INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, job_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE transcript_status (
                    tenant_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'in_review',
                    is_final INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, job_id)
                )
                """
            )
            conn.commit()
            conn.close()

            store = SQLiteTranscriptCorrectionStore(db_path)
            payload = {
                'session_id': 'cs_legacy',
                'job_id': 'job_legacy',
                'actor_id': 'u-1',
                'base_version': 1,
                'autosave_enabled': False,
                'speaker_labels': {},
                'review_status': 'in_review',
                'is_final': False,
                'history_index': 0,
                'history': [{'segments': [{'segment_id': 'seg_1', 'start': 0.0, 'end': 1.0, 'speaker': 'S1', 'text': 'Hallo'}], 'summary': None}],
                'updated_at': '2026-03-25T00:00:00+00:00',
                'created_at': '2026-03-25T00:00:00+00:00',
            }
            store.create_session(tenant_id='tenant-a', payload=payload)
            loaded = store.get_session(tenant_id='tenant-a', session_id='cs_legacy')
            assert loaded is not None
            self.assertEqual(loaded['job_id'], 'job_legacy')

            # Legacy schema allowed only one correction session per tenant+job.
            # A second start must resume the existing draft instead of failing.
            second = dict(payload)
            second['session_id'] = 'cs_second'
            resumed = store.create_session(tenant_id='tenant-a', payload=second)
            self.assertEqual(resumed['session_id'], 'cs_legacy')


if __name__ == '__main__':
    unittest.main()
