"""Progress is derived from documents, never from a stored percentage.

The rule that matters: a mandatory item that is missing or unverified keeps its
stage open. A missing Week 3 report means the weekly-submission stage is NOT
complete, however many other weeks were filed.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from app.models.enums import StageStatus, SubmissionStatus
from app.services.documents import progress, stage_requirements_met


class FakeSession:
    """Minimal Session stand-in: the service only reads through scalar/scalars."""

    def __init__(self, *, document=None, reports=()):
        self._document = document
        self._reports = list(reports)

    def scalar(self, _stmt):
        return self._document

    def scalars(self, _stmt):
        return list(self._reports)


def stage(code="CERTIFICATE", *, requires_document=False, mandatory=True):
    return SimpleNamespace(
        id=1, code=code, name=code.replace("_", " ").title(),
        requires_document=requires_document, is_mandatory=mandatory,
    )


def enrollment(*, weeks=0):
    from app.models.enums import ReportFrequency

    start = dt.date(2026, 5, 4)
    program = SimpleNamespace(
        id=1,
        report_frequency=ReportFrequency.WEEKLY if weeks else ReportFrequency.NONE,
        start_date=start if weeks else None,
        end_date=start + dt.timedelta(weeks=weeks) if weeks else None,
        expected_report_count=weeks,
    )
    return SimpleNamespace(id=1, program=program)


def report(sequence, status):
    return SimpleNamespace(sequence_number=sequence, status=status, report_type="WEEKLY")


def document(status):
    return SimpleNamespace(id=1, status=status)


# ── a stage that needs evidence needs *verified* evidence ─────────────────
def test_missing_document_blocks_its_stage():
    met, reason = stage_requirements_met(
        FakeSession(document=None), enrollment(), stage(requires_document=True),
    )
    assert met is False
    assert "not submitted" in reason


def test_unverified_document_does_not_complete_a_stage():
    """Uploading is not the same as being accepted."""
    for status in (SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW,
                   SubmissionStatus.REJECTED):
        met, reason = stage_requirements_met(
            FakeSession(document=document(status)),
            enrollment(), stage(requires_document=True),
        )
        assert met is False
        assert reason


def test_verified_document_completes_its_stage():
    met, reason = stage_requirements_met(
        FakeSession(document=document(SubmissionStatus.VERIFIED)),
        enrollment(), stage(requires_document=True),
    )
    assert met is True and reason is None


def test_rejection_reason_names_the_stage_and_the_state():
    _, reason = stage_requirements_met(
        FakeSession(document=document(SubmissionStatus.REJECTED)),
        enrollment(), stage("CERTIFICATE", requires_document=True),
    )
    assert "Certificate" in reason and "rejected" in reason


# ── weekly reports gate the in-progress stage ─────────────────────────────
def test_one_missing_week_keeps_the_reporting_stage_open():
    """Weeks 1, 2 and 4 verified but Week 3 missing → stage NOT complete."""
    filed = [report(n, SubmissionStatus.VERIFIED) for n in (1, 2, 4, 5, 6, 7, 8)]
    met, reason = stage_requirements_met(
        FakeSession(reports=filed), enrollment(weeks=8), stage("IN_PROGRESS"),
    )
    assert met is False
    assert "week 3" in reason
    assert "1 of 8" in reason


def test_every_week_verified_completes_the_reporting_stage():
    filed = [report(n, SubmissionStatus.VERIFIED) for n in range(1, 9)]
    met, reason = stage_requirements_met(
        FakeSession(reports=filed), enrollment(weeks=8), stage("IN_PROGRESS"),
    )
    assert met is True and reason is None


def test_a_submitted_but_unverified_week_still_counts_as_outstanding():
    filed = [report(n, SubmissionStatus.VERIFIED) for n in range(1, 8)]
    filed.append(report(8, SubmissionStatus.SUBMITTED))
    met, reason = stage_requirements_met(
        FakeSession(reports=filed), enrollment(weeks=8), stage("IN_PROGRESS"),
    )
    assert met is False
    assert "week 8" in reason


def test_blocker_message_truncates_a_long_list_of_missing_weeks():
    met, reason = stage_requirements_met(
        FakeSession(reports=[]), enrollment(weeks=8), stage("IN_PROGRESS"),
    )
    assert met is False
    assert "…" in reason and "8 of 8" in reason


def test_a_programme_without_reports_is_not_gated_on_them():
    met, reason = stage_requirements_met(
        FakeSession(reports=[]), enrollment(weeks=0), stage("IN_PROGRESS"),
    )
    assert met is True and reason is None


# ── the aggregate ─────────────────────────────────────────────────────────
def _progress_with(monkeypatch, timeline, session):
    from app.services import internships as internship_service

    monkeypatch.setattr(internship_service, "stage_timeline",
                        lambda _db, _enrollment: timeline)
    return progress(session, enrollment())


def test_progress_is_zero_when_there_are_no_stages(monkeypatch):
    assert _progress_with(monkeypatch, [], FakeSession()) == {
        "completed": 0, "total": 0, "percent": 0, "blockers": [],
    }


def test_progress_counts_only_stages_that_are_approved_and_evidenced(monkeypatch):
    timeline = [
        SimpleNamespace(status=StageStatus.APPROVED, stage=stage("A")),
        SimpleNamespace(status=StageStatus.APPROVED, stage=stage("B")),
        SimpleNamespace(status=StageStatus.PENDING, stage=stage("C")),
        SimpleNamespace(status=StageStatus.SUBMITTED, stage=stage("D")),
    ]
    result = _progress_with(monkeypatch, timeline, FakeSession())
    assert result["completed"] == 2
    assert result["total"] == 4
    assert result["percent"] == 50


def test_an_approved_stage_with_a_rejected_document_does_not_count(monkeypatch):
    """Approval alone cannot complete a stage whose evidence was rejected."""
    timeline = [
        SimpleNamespace(status=StageStatus.APPROVED,
                        stage=stage("CERTIFICATE", requires_document=True)),
    ]
    session = FakeSession(document=document(SubmissionStatus.REJECTED))
    result = _progress_with(monkeypatch, timeline, session)
    assert result["completed"] == 0
    assert result["percent"] == 0
    assert any("rejected" in b for b in result["blockers"])


def test_optional_stages_do_not_raise_blockers(monkeypatch):
    timeline = [
        SimpleNamespace(status=StageStatus.PENDING,
                        stage=stage("POSTER", requires_document=True, mandatory=False)),
    ]
    result = _progress_with(monkeypatch, timeline,
                            FakeSession(document=None))
    assert result["blockers"] == []


def test_percent_is_a_count_of_stages_not_an_estimate(monkeypatch):
    timeline = [SimpleNamespace(status=StageStatus.APPROVED, stage=stage(f"S{i}"))
                for i in range(3)]
    result = _progress_with(monkeypatch, timeline, FakeSession())
    assert result["percent"] == 100
    assert result["completed"] == result["total"] == 3
