"""Tests for scripts/make_summary.py decision logic."""

import os
import sys
import json
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDecisionLogic:
    """Test the decision logic from make_summary.py."""
    
    def test_clear_winner(self):
        """Test decision with a clear winner."""
        # Simulate results where transkun is clearly the best
        # We'll test the logic directly by importing the function
        from scripts.make_summary import make_decision_section
        
        # Create mock all_metrics
        all_metrics = {
            'maestro_test5': {
                'naive': {'onset_only_f1': 0.25},
                'basic_pitch': {'onset_only_f1': 0.65},
                'kong': {'onset_only_f1': 0.97, 'rt_factor': 0.40},
                'transkun': {'onset_only_f1': 0.99, 'rt_factor': 0.10},
            },
            'smd5': {
                'naive': {'onset_only_f1': 0.20},
                'basic_pitch': {'onset_only_f1': 0.60},
                'kong': {'onset_only_f1': 0.95, 'rt_factor': 0.40},
                'transkun': {'onset_only_f1': 0.98, 'rt_factor': 0.10},
            },
        }
        
        decision_text, status = make_decision_section(all_metrics)
        
        # Should be "採用" (adopted) since smd5 is available
        assert status == "採用"
        # Should select transkun (highest F1)
        assert "transkun" in decision_text
    
    def test_tie_breaks_by_rt(self):
        """Test that when two candidates are within 1.0 point, the faster one is selected."""
        from scripts.make_summary import make_decision_section
        
        # Create mock all_metrics where kong and transkun are tied on smd5
        all_metrics = {
            'maestro_test5': {
                'naive': {'onset_only_f1': 0.25},
                'kong': {'onset_only_f1': 0.97, 'rt_factor': 0.40},
                'transkun': {'onset_only_f1': 0.98, 'rt_factor': 0.10},
            },
            'smd5': {
                'naive': {'onset_only_f1': 0.20},
                'kong': {'onset_only_f1': 0.97, 'rt_factor': 0.40},  # Same as transkun within 0.01
                'transkun': {'onset_only_f1': 0.975, 'rt_factor': 0.10},  # Within 0.01 of kong
            },
        }
        
        decision_text, status = make_decision_section(all_metrics)
        
        # Both should be in tied set, and transkun should be adopted (lower RT)
        assert status == "採用"
        assert "transkun" in decision_text
        assert "同率" in decision_text
    
    def test_smd5_missing_provisional(self):
        """Test that when smd5 is missing, decision is provisional."""
        from scripts.make_summary import make_decision_section
        
        # Create mock all_metrics without smd5
        all_metrics = {
            'maestro_test5': {
                'naive': {'onset_only_f1': 0.25},
                'kong': {'onset_only_f1': 0.97, 'rt_factor': 0.40},
                'transkun': {'onset_only_f1': 0.98, 'rt_factor': 0.10},
            },
            # smd5 is missing
        }
        
        decision_text, status = make_decision_section(all_metrics)
        
        # Should be "暫定採用" (provisional adoption)
        assert status == "暫定採用"
        assert "暫定採用" in decision_text
    
    def test_missing_dataset_shown_as_unmeasured(self):
        """Test that missing datasets are shown as 未測定."""
        from scripts.make_summary import get_unmeasured_datasets
        
        # Create a temporary directory without the result files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temp directory
            orig_dir = os.getcwd()
            os.chdir(tmpdir)
            
            try:
                # Create results directory but no files
                Path("results").mkdir(exist_ok=True)
                
                unmeasured = get_unmeasured_datasets()
                
                # All datasets should be unmeasured
                assert "synth" in unmeasured
                assert "maestro_test5" in unmeasured
                assert "smd5" in unmeasured
                assert "maestro_test5_degraded" in unmeasured
            finally:
                os.chdir(orig_dir)
    
    def test_overview_table_with_missing(self):
        """Test that overview table shows 未測定 for missing datasets."""
        from scripts.make_summary import make_overview_table
        
        # Create mock all_metrics with only some datasets
        all_metrics = {
            'maestro_test5': {
                'naive': {'onset_only_f1': 0.25, 'rt_factor': 0.02, 'rss_mb': 100.0},
                'transkun': {'onset_only_f1': 0.98, 'rt_factor': 0.10, 'rss_mb': 200.0},
            },
            # synth, smd5, maestro_test5_degraded are missing
        }
        
        table = make_overview_table(all_metrics)
        
        # Should contain 未測定 for missing datasets
        assert "未測定" in table
        # Should contain the available data
        assert "0.2500" in table or "0.25" in table
        assert "0.9800" in table or "0.98" in table
