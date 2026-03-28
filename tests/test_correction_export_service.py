import io
import unittest
import zipfile
from datetime import datetime, timezone

from evodox.jobs.correction_export_service import (
    CorrectionExportValidationError,
    build_correction_court_export_artifact,
    build_court_transcript_plain_text,
)


class CorrectionExportServiceTests(unittest.TestCase):
    def test_build_court_transcript_plain_text_uses_alias_without_suffix(self):
        content = build_court_transcript_plain_text(
            job_id="job_1",
            session_id="cs_1",
            base_version=2,
            working_version=4,
            review_status="in_review",
            is_final=False,
            segments=[
                {"speaker": "SPEAKER_01", "start": 4, "end": 11, "text": "Bitte nennen Sie Ihren Namen."},
                {"speaker": "SPEAKER_03", "start": 18, "end": 24, "text": "Ich bestaetige die Angabe."},
            ],
            speaker_labels={"SPEAKER_01": "Staatsanwalt"},
            created_at=datetime(2026, 3, 28, 11, 15, 42, tzinfo=timezone.utc),
        )
        self.assertIn("Einvernahmeprotokoll", content)
        self.assertIn("[00:00:04 - 00:00:11] Staatsanwalt:", content)
        self.assertNotIn("Staatsanwalt (SPEAKER_01)", content)
        self.assertIn("[00:00:18 - 00:00:24] SPEAKER_03:", content)
        self.assertIn("Exportzeitpunkt (UTC): 2026-03-28T11:15:42+00:00", content)

    def test_compact_mode_merges_consecutive_speaker_segments(self):
        artifact = build_correction_court_export_artifact(
            job_id="job_merge",
            session_id="cs_merge",
            base_version=1,
            working_version=2,
            review_status="in_review",
            is_final=False,
            segments=[
                {"speaker": "S1", "start": 0, "end": 2, "text": "A"},
                {"speaker": "S1", "start": 5, "end": 7, "text": "B"},
            ],
            speaker_labels={},
            fmt="txt",
            profile="court_transcript",
            mode="compact",
            created_at=datetime(2026, 3, 28, 11, 15, 42, tzinfo=timezone.utc),
        )
        text = artifact.content.decode("utf-8")
        self.assertIn("[00:00:00 - 00:00:07] S1:", text)
        self.assertIn("A\nB", text)

    def test_docx_export_emits_valid_zip_with_document_xml(self):
        artifact = build_correction_court_export_artifact(
            job_id="job_docx",
            session_id="cs_docx",
            base_version=1,
            working_version=1,
            review_status="in_review",
            is_final=False,
            segments=[
                {"speaker": "S1", "start": 0, "end": 1, "text": "Hallo Welt"},
            ],
            speaker_labels={"S1": "Max Muster"},
            fmt="docx",
            profile="court_transcript",
            mode="raw",
            created_at=datetime(2026, 3, 28, 11, 15, 42, tzinfo=timezone.utc),
        )
        self.assertEqual(
            artifact.content_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertTrue(artifact.filename.endswith(".docx"))
        self.assertTrue(artifact.content.startswith(b"PK"))
        with zipfile.ZipFile(io.BytesIO(artifact.content), "r") as archive:
            names = set(archive.namelist())
            self.assertIn("[Content_Types].xml", names)
            self.assertIn("_rels/.rels", names)
            self.assertIn("word/document.xml", names)
            document_xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("Max Muster", document_xml)
            self.assertIn("Einvernahmeprotokoll", document_xml)

    def test_invalid_format_raises_validation_error(self):
        with self.assertRaises(CorrectionExportValidationError) as ctx:
            build_correction_court_export_artifact(
                job_id="job_1",
                session_id="cs_1",
                base_version=1,
                working_version=1,
                review_status="in_review",
                is_final=False,
                segments=[],
                speaker_labels={},
                fmt="pdf",
                profile="court_transcript",
                mode="raw",
            )
        self.assertEqual(ctx.exception.error_code, "transcript.correction_export_invalid_format")


if __name__ == "__main__":
    unittest.main()
