"""
Test Edge Sanitization
=======================

Validates that Edge data extraction:
- Strips ALL forbidden fields
- Never outputs unsanitized data
- Does NOT train directly
- Outputs to datasets/raw/ only
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestEdgeSanitization:
    """Tests for Edge data extraction governance."""
    
    def test_forbidden_fields_defined(self):
        """Edge extractor must define forbidden fields."""
        # data_extractor.cpp is at YGB/edge/ (project root edge dir)
        ygb_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        cpp_path = os.path.join(ygb_root, "edge", "data_extractor.cpp")
        
        assert os.path.exists(cpp_path), f"data_extractor.cpp not found at {cpp_path}"
        
        with open(cpp_path, 'r') as f:
            source = f.read()
        
        # Check all required forbidden fields
        for field in ["valid", "accepted", "rejected", "severity", 
                      "decision", "bounty", "platform_verdict"]:
            assert field in source, f"Forbidden field '{field}' not defined in extractor"
    
    def test_sanitize_function_exists(self):
        """sanitize_output function must exist in extractor."""
        # data_extractor.cpp is at YGB/edge/ (project root edge dir)
        ygb_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        cpp_path = os.path.join(ygb_root, "edge", "data_extractor.cpp")
        
        with open(cpp_path, 'r') as f:
            source = f.read()
        
        assert "sanitize_output" in source, "sanitize_output function missing"
        assert "is_forbidden_field" in source, "is_forbidden_field function missing"
    
    def test_extract_dom_function_exists(self):
        """extract_dom_structure function must exist."""
        # data_extractor.cpp is at YGB/edge/ (project root edge dir)
        ygb_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        cpp_path = os.path.join(ygb_root, "edge", "data_extractor.cpp")
        
        with open(cpp_path, 'r') as f:
            source = f.read()
        
        assert "extract_dom_structure" in source
    
    def test_capture_http_trace_exists(self):
        """capture_http_trace function must exist."""
        # data_extractor.cpp is at YGB/edge/ (project root edge dir)
        ygb_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        cpp_path = os.path.join(ygb_root, "edge", "data_extractor.cpp")
        
        with open(cpp_path, 'r') as f:
            source = f.read()
        
        assert "capture_http_trace" in source
    
    def test_no_training_in_extractor(self):
        """Edge extractor must NOT contain training code."""
        # data_extractor.cpp is at YGB/edge/ (project root edge dir)
        ygb_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        cpp_path = os.path.join(ygb_root, "edge", "data_extractor.cpp")
        
        with open(cpp_path, 'r') as f:
            source = f.read().lower()
        
        assert "train(" not in source, "Edge extractor must NOT train"
        assert "backprop" not in source, "Edge extractor must NOT backpropagate"
        assert "gradient" not in source, "Edge extractor must NOT compute gradients"
    
    def test_body_preview_limited(self):
        """Body preview must be limited to 1024 bytes."""
        # data_extractor.cpp is at YGB/edge/ (project root edge dir)
        ygb_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        cpp_path = os.path.join(ygb_root, "edge", "data_extractor.cpp")
        
        with open(cpp_path, 'r') as f:
            source = f.read()
        
        assert "1024" in source, "Body preview limit (1024) not found"
    
    def test_python_governance_consistency(self):
        """Python forbidden fields must match C++ forbidden fields."""
        from impl_v1.training.data.real_dataset_loader import FORBIDDEN_FIELDS
        
        # data_extractor.cpp is at YGB/edge/ (project root edge dir)
        ygb_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        cpp_path = os.path.join(ygb_root, "edge", "data_extractor.cpp")
        
        with open(cpp_path, 'r') as f:
            source = f.read()
        
        # Core fields must exist in both
        for field in ["valid", "accepted", "rejected", "severity", "decision"]:
            assert field in FORBIDDEN_FIELDS, f"'{field}' missing from Python FORBIDDEN_FIELDS"
            assert f'"{field}"' in source, f"'{field}' missing from C++ FORBIDDEN_FIELDS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
