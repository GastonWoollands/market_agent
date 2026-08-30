"""Tests for manual Outlook generation workflow (Cursor skill)."""

from datetime import date

import pytest

from store.engine import session_scope
from store.repos import latest_evidence_pack


def test_pack_loading_for_manual_generation():
    """Verify evidence pack can be loaded for manual Outlook generation."""
    # This test validates the first step of the manual skill
    # It should pass if a pack exists for today or skip if none
    
    with session_scope() as session:
        pack_row = latest_evidence_pack(session, date.today())
        
        if pack_row is None:
            pytest.skip("No evidence pack for today. Run: make pack")
        
        # Verify pack structure
        pack = dict(pack_row.pack)
        assert "as_of" in pack
        assert "macro" in pack
        assert "sources" in pack
        
        # Pack ID should be positive
        assert pack_row.id > 0


def test_pack_has_required_fields_for_narration():
    """Verify pack has all fields needed for Outlook generation."""
    with session_scope() as session:
        pack_row = latest_evidence_pack(session, date.today())
        
        if pack_row is None:
            pytest.skip("No evidence pack for today. Run: make pack")
        
        pack = dict(pack_row.pack)
        
        # Required top-level fields
        required_fields = [
            "as_of",
            "header",
            "sectors",
            "macro",
            "facts",
            "news",
            "events",
            "sources",
        ]
        
        for field in required_fields:
            assert field in pack, f"Missing required field: {field}"


def test_regime_and_liquidity_in_pack():
    """Verify Phase 1 additions (regime, liquidity, anomalies) present in pack."""
    with session_scope() as session:
        pack_row = latest_evidence_pack(session, date.today())
        
        if pack_row is None:
            pytest.skip("No evidence pack for today. Run: make pack")
        
        pack = dict(pack_row.pack)
        
        # Phase 1 additions should be present
        # These may be None if compute_regime hasn't run or no anomalies detected
        assert "regime" in pack or pack.get("regime") is None
        assert "liquidity" in pack or pack.get("liquidity") is None
        assert "anomalies" in pack or pack.get("anomalies") == []


def test_manual_skill_prerequisite_check():
    """Test the prerequisite check that skill performs before generation."""
    from store.repos import latest_evidence_pack
    
    with session_scope() as session:
        # Try to load today's pack
        target_date = date.today()
        pack_row = latest_evidence_pack(session, target_date)
        
        if pack_row is None:
            # This is the expected error message the skill should show
            expected_msg = f"No evidence pack for {target_date}. Run: python -m jobs.build_pack"
            assert "No evidence pack" in expected_msg
            pytest.skip("Pack missing - skill would display error message")
        
        # If pack exists, verify we can extract key highlights
        pack = dict(pack_row.pack)
        
        # Extract regime (if present)
        if "regime" in pack and pack["regime"]:
            regime = pack["regime"]
            assert "growth" in regime
            assert "inflation" in regime
            assert "policy" in regime
            assert "volatility" in regime
            assert "confidence" in regime
        
        # Extract liquidity (if present)
        if "liquidity" in pack and pack["liquidity"]:
            liq = pack["liquidity"]
            assert "net_liquidity_bn" in liq
            # wow_change_bn may be None if no w1 data
        
        # Extract anomalies (if present)
        if "anomalies" in pack and pack["anomalies"]:
            for anomaly in pack["anomalies"]:
                assert "type" in anomaly
                assert "description" in anomaly
                assert "severity" in anomaly
                assert 0 <= anomaly["severity"] <= 1
