# test_g17_voice_reporting.py
"""Tests for G17 Voice Reporting governor."""

from pathlib import Path
import logging

import pytest

from impl_v1.phase49.governors.g17_voice_reporting import (
    HIGH_IMPACT_SUGGESTIONS,
    ProgressNarration,
    ReportLanguage,
    ReportQueue,
    VoiceReport,
    VoiceReportType,
    VoiceReporter,
    answer_follow_up,
    can_voice_execute,
    clear_reports,
    create_progress_narration,
    explain_report,
    generate_high_impact_tips,
    get_all_narrations,
    get_all_reports,
    get_voice_text,
)


class TestVoiceReportType:
    """Tests for VoiceReportType enum."""
    
    def test_has_progress_narration(self):
        assert VoiceReportType.PROGRESS_NARRATION.value == "PROGRESS_NARRATION"
    
    def test_has_final_explanation(self):
        assert VoiceReportType.FINAL_EXPLANATION.value == "FINAL_EXPLANATION"
    
    def test_has_high_impact_tips(self):
        assert VoiceReportType.HIGH_IMPACT_TIPS.value == "HIGH_IMPACT_TIPS"
    
    def test_has_follow_up_answer(self):
        assert VoiceReportType.FOLLOW_UP_ANSWER.value == "FOLLOW_UP_ANSWER"
    
    def test_has_error_explanation(self):
        assert VoiceReportType.ERROR_EXPLANATION.value == "ERROR_EXPLANATION"


class TestReportLanguage:
    """Tests for ReportLanguage enum."""
    
    def test_has_english(self):
        assert ReportLanguage.ENGLISH.value == "ENGLISH"
    
    def test_has_hindi(self):
        assert ReportLanguage.HINDI.value == "HINDI"


class TestCreateProgressNarration:
    """Tests for create_progress_narration function."""
    
    def setup_method(self):
        clear_reports()
    
    def test_creates_narration(self):
        narration = create_progress_narration(
            phase="scanning",
            percentage=50,
            message_en="Halfway done",
            message_hi="Aadha ho gaya",
        )
        assert isinstance(narration, ProgressNarration)
    
    def test_narration_has_id(self):
        narration = create_progress_narration(
            phase="test",
            percentage=25,
            message_en="Test",
            message_hi="Test",
        )
        assert narration.narration_id.startswith("NAR-")
    
    def test_percentage_clamped_to_100(self):
        narration = create_progress_narration(
            phase="test",
            percentage=150,
            message_en="Test",
            message_hi="Test",
        )
        assert narration.percentage == 100
    
    def test_percentage_clamped_to_0(self):
        narration = create_progress_narration(
            phase="test",
            percentage=-10,
            message_en="Test",
            message_hi="Test",
        )
        assert narration.percentage == 0
    
    def test_narrations_are_stored(self):
        create_progress_narration("test", 50, "En", "Hi")
        narrations = get_all_narrations()
        assert len(narrations) >= 1


class TestGenerateHighImpactTips:
    """Tests for generate_high_impact_tips function."""
    
    def setup_method(self):
        clear_reports()
    
    def test_generates_report(self):
        report = generate_high_impact_tips("xss")
        assert isinstance(report, VoiceReport)
    
    def test_report_type_is_high_impact_tips(self):
        report = generate_high_impact_tips("sqli")
        assert report.report_type == VoiceReportType.HIGH_IMPACT_TIPS
    
    def test_report_has_english_content(self):
        report = generate_high_impact_tips("idor")
        assert len(report.content_en) > 0
    
    def test_report_has_hindi_content(self):
        report = generate_high_impact_tips("rce")
        assert len(report.content_hi) > 0
    
    def test_report_has_suggestions(self):
        report = generate_high_impact_tips("xss")
        assert len(report.suggestions) > 0
    
    def test_unknown_bug_type_uses_default(self):
        report = generate_high_impact_tips("unknown-bug-type")
        assert len(report.suggestions) > 0


class TestExplainReport:
    """Tests for explain_report function."""
    
    def setup_method(self):
        clear_reports()
    
    def test_creates_explanation(self):
        report = explain_report(
            report_summary="Found stored XSS in profile page",
            bug_type="xss",
            severity="HIGH",
        )
        assert isinstance(report, VoiceReport)
    
    def test_report_type_is_final_explanation(self):
        report = explain_report("Summary", "test", "LOW")
        assert report.report_type == VoiceReportType.FINAL_EXPLANATION
    
    def test_includes_bug_type(self):
        report = explain_report("Summary", "sqli", "CRITICAL")
        assert "sqli" in report.content_en.lower()


class TestAnswerFollowUp:
    """Tests for answer_follow_up function."""
    
    def setup_method(self):
        clear_reports()
    
    def test_creates_answer(self):
        report = answer_follow_up("what else can I add", {"bug_type": "xss"})
        assert isinstance(report, VoiceReport)
    
    def test_payout_question_gives_tips(self):
        report = answer_follow_up("how to increase payout", {"bug_type": "xss"})
        assert report.report_type == VoiceReportType.HIGH_IMPACT_TIPS
    
    def test_hindi_payout_question(self):
        report = answer_follow_up("payout kaise badhao", {"bug_type": "xss"})
        assert report.report_type == VoiceReportType.HIGH_IMPACT_TIPS


class TestGetVoiceText:
    """Tests for get_voice_text function."""
    
    def setup_method(self):
        clear_reports()
    
    def test_returns_english_by_default(self):
        report = generate_high_impact_tips("xss")
        text = get_voice_text(report)
        assert text == report.content_en
    
    def test_returns_hindi_when_requested(self):
        report = generate_high_impact_tips("xss")
        text = get_voice_text(report, ReportLanguage.HINDI)
        assert text == report.content_hi


class TestCanVoiceExecute:
    """Tests for can_voice_execute function."""
    
    def test_returns_tuple(self):
        result = can_voice_execute()
        assert isinstance(result, tuple)
    
    def test_voice_cannot_execute(self):
        can_execute, reason = can_voice_execute()
        assert can_execute == False
    
    def test_has_reason(self):
        _, reason = can_voice_execute()
        assert "OUTPUT ONLY" in reason or "cannot" in reason.lower()


class TestHighImpactSuggestions:
    """Tests for HIGH_IMPACT_SUGGESTIONS templates."""
    
    def test_has_xss_suggestions(self):
        assert "xss" in HIGH_IMPACT_SUGGESTIONS
    
    def test_has_sqli_suggestions(self):
        assert "sqli" in HIGH_IMPACT_SUGGESTIONS
    
    def test_has_idor_suggestions(self):
        assert "idor" in HIGH_IMPACT_SUGGESTIONS
    
    def test_has_rce_suggestions(self):
        assert "rce" in HIGH_IMPACT_SUGGESTIONS
    
    def test_has_default_suggestions(self):
        assert "default" in HIGH_IMPACT_SUGGESTIONS
    
    def test_suggestions_are_bilingual(self):
        for tips in HIGH_IMPACT_SUGGESTIONS["xss"]:
            assert len(tips) == 2  # (en, hi)


class TestVoiceReporterQueueing:
    """Tests for queue-backed voice report delivery."""

    def setup_method(self):
        clear_reports()

    def test_generate_report_returns_queued_report_without_tts(self):
        reporter = VoiceReporter()

        report = reporter.generate_report("Queued voice summary")

        assert isinstance(report, VoiceReport)
        assert report.content == "Queued voice summary"
        assert report.delivery_status == "QUEUED"
        assert report.tts_ready is False

    def test_voice_reports_queue_correctly(self):
        reporter = VoiceReporter()

        first = reporter.generate_report("first")
        second = reporter.generate_report("second")

        pending = reporter.report_queue.get_pending()

        assert pending == [first, second]

    def test_queue_overflow_drops_oldest_with_warning(self, caplog):
        reporter = VoiceReporter(report_queue=ReportQueue(max_pending=100))

        with caplog.at_level(logging.WARNING):
            for index in range(101):
                reporter.generate_report(f"report-{index}")

        pending = reporter.report_queue.get_pending()

        assert len(pending) == 100
        assert pending[0].content == "report-1"
        assert pending[-1].content == "report-100"
        assert any("Dropping oldest queued voice report" in record.message for record in caplog.records)

    def test_production_file_has_no_simulated_tts_wording(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "governors"
            / "g17_voice_reporting.py"
        ).read_text(encoding="utf-8").lower()

        assert "simulated" not in source
        assert "simulate" not in source
