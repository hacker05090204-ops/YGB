# Phase-48 Tests
import pytest
from impl_v1.phase48.analytics import *


class TestEnumClosure:
    def test_metric_type_6(self): assert len(MetricType) == 6
    def test_rejection_reason_8(self): assert len(RejectionReason) == 8
    def test_skill_level_5(self): assert len(SkillLevel) == 5
    def test_skill_gap_6(self): assert len(SkillGap) == 6


class TestRates:
    def test_acceptance_rate(self):
        assert calculate_acceptance_rate(8, 10) == 0.8
    
    def test_acceptance_rate_zero(self):
        assert calculate_acceptance_rate(0, 0) == 0.0
    
    def test_duplicate_rate(self):
        assert calculate_duplicate_rate(3, 10) == 0.3


class TestSkillLevel:
    def test_unknown_low_submissions(self):
        m = HunterMetrics("H-001", 3, 2, 1, 0, 5.0, SkillLevel.UNKNOWN)
        assert determine_skill_level(m) == SkillLevel.UNKNOWN
    
    def test_expert(self):
        m = HunterMetrics("H-001", 100, 85, 15, 0, 8.0, SkillLevel.UNKNOWN)
        assert determine_skill_level(m) == SkillLevel.EXPERT
    
    def test_beginner(self):
        m = HunterMetrics("H-001", 20, 3, 17, 10, 2.0, SkillLevel.UNKNOWN)
        assert determine_skill_level(m) == SkillLevel.BEGINNER


class TestSkillGaps:
    def test_no_gaps(self):
        m = HunterMetrics("H-001", 10, 8, 2, 0, 7.0, SkillLevel.EXPERT)
        gaps = detect_skill_gaps(m, [])
        assert SkillGap.NONE in gaps
    
    def test_duplicate_gap(self):
        m = HunterMetrics("H-001", 10, 5, 5, 3, 5.0, SkillLevel.INTERMEDIATE)
        history = [RejectionReason.DUPLICATE] * 4 + [RejectionReason.OTHER]
        gaps = detect_skill_gaps(m, history)
        assert SkillGap.DUPLICATE_DETECTION in gaps
    
    def test_scope_gap(self):
        m = HunterMetrics("H-001", 10, 5, 5, 0, 5.0, SkillLevel.INTERMEDIATE)
        history = [RejectionReason.OUT_OF_SCOPE] * 3 + [RejectionReason.OTHER] * 2
        gaps = detect_skill_gaps(m, history)
        assert SkillGap.SCOPE_AWARENESS in gaps


class TestFeedback:
    def test_generate_feedback(self):
        m = HunterMetrics("H-001", 10, 5, 5, 3, 5.0, SkillLevel.INTERMEDIATE)
        history = [RejectionReason.DUPLICATE] * 4
        
        fb = generate_feedback("H-001", m, history)
        assert fb.feedback_id.startswith("FBK-")
        assert SkillGap.DUPLICATE_DETECTION in fb.skill_gaps
        assert len(fb.recommendations) > 0
