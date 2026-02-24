"""
Tests for Issue #33: Universe context isolation in crossover powers.

This test suite verifies that PowerOrigin entries prevent universe-specific
terminology from leaking into story mechanics when powers are used across
different universes (e.g., JJK power in Wormverse story).
"""

import os
import sys
import pytest
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.bible_validator import (
    check_power_origin_context_leakage,
    clean_power_origin_context,
    _remove_universe_terms,
)


class TestPowerOriginLeakageDetection:
    """Test detection of universe-specific terminology in power mechanics."""

    def test_detects_jjk_terminology_in_techniques(self):
        """Detect JJK terminology like 'Cursed Technique' in canon_techniques."""
        power_origin = {
            "power_name": "Reversal Counter",
            "original_wielder": "Gojo Satoru",
            "canon_techniques": [
                {
                    "name": "Cursed Technique Reversal",  # ← JJK term
                    "description": "Inversion technique that reverses attacks",
                }
            ],
            "source_universe_context": None,
        }

        warnings = check_power_origin_context_leakage(power_origin)

        assert len(warnings) > 0
        assert any("cursed technique" in w.lower() for w in warnings)
        assert any("canon_techniques" in w for w in warnings)

    def test_detects_cursed_energy_terminology(self):
        """Detect 'Cursed Energy' terminology in descriptions."""
        power_origin = {
            "power_name": "Energy Inversion",
            "original_wielder": "Gojo Satoru",
            "canon_techniques": [
                {
                    "name": "Inversion",
                    "description": "Uses Cursed Energy to invert attacks",  # ← JJK term
                }
            ],
        }

        warnings = check_power_origin_context_leakage(power_origin)

        assert len(warnings) > 0
        assert any("cursed energy" in w.lower() for w in warnings)

    def test_detects_worm_terminology(self):
        """Detect Worm-specific terminology like 'trigger event' and 'parahuman'."""
        power_origin = {
            "power_name": "Master",
            "original_wielder": "Skitter",
            "combat_style": "Swarm control through trigger event powers",  # ← Worm term
            "canon_techniques": [
                {
                    "name": "Swarm Control",
                    "description": "Parahuman ability to control insects",  # ← Worm term
                }
            ],
        }

        warnings = check_power_origin_context_leakage(power_origin)

        assert len(warnings) > 0
        assert any("trigger event" in w.lower() or "parahuman" in w.lower() for w in warnings)

    def test_detects_generic_anime_system_terms(self):
        """Detect generic anime system terms like 'qi', 'chakra', 'mana'."""
        power_origin = {
            "power_name": "Elemental Control",
            "original_wielder": "Generic Cultivator",
            "combat_style": "Uses qi and chakra to control elements",  # ← System terms
            "canon_techniques": [
                {
                    "name": "Fire Mastery",
                    "description": "Mana-based fire technique at cultivation stage 5",  # ← Terms
                }
            ],
        }

        warnings = check_power_origin_context_leakage(power_origin)

        assert len(warnings) > 0
        # Should detect qi, chakra, mana, or cultivation stage
        warning_text = " ".join(warnings).lower()
        assert any(term in warning_text for term in ["qi", "chakra", "mana", "cultivation"])

    def test_no_warnings_for_clean_power_origin(self):
        """Ensure clean power origins pass without warnings."""
        power_origin = {
            "power_name": "Reversal Counter",
            "original_wielder": "Gojo Satoru",
            "canon_techniques": [
                {
                    "name": "Reversal Counter",
                    "description": "Technique that negates and reverses incoming attacks",
                }
            ],
            "combat_style": "Defensive counter-attack using inversion mechanics",
            "source_universe_context": {
                "original_name": "Cursed Technique Reversal",
                "source_system": "Jujutsu Kaisen cursed energy system",
            },
        }

        warnings = check_power_origin_context_leakage(power_origin)

        assert len(warnings) == 0

    def test_handles_empty_canon_techniques(self):
        """Handle power_origin with no canon_techniques gracefully."""
        power_origin = {
            "power_name": "Unknown Power",
            "original_wielder": "Unknown",
            "canon_techniques": [],
        }

        warnings = check_power_origin_context_leakage(power_origin)

        assert isinstance(warnings, list)
        # Should not raise an error, may be empty or have other warnings

    def test_handles_missing_optional_fields(self):
        """Handle power_origin missing optional fields."""
        power_origin = {
            "power_name": "Simple Power",
            "original_wielder": "Someone",
            # Missing: canon_techniques, combat_style, etc.
        }

        warnings = check_power_origin_context_leakage(power_origin)

        assert isinstance(warnings, list)


class TestPowerOriginContextCleaning:
    """Test automatic cleanup of universe-specific terminology."""

    def test_cleans_jjk_terminology_from_techniques(self):
        """Remove JJK terminology from canon techniques."""
        power_origin = {
            "power_name": "Reversal",
            "original_wielder": "Gojo Satoru",
            "canon_techniques": [
                {
                    "name": "Cursed Technique Reversal",
                    "description": "Uses Cursed Energy to reverse attacks",
                }
            ],
        }

        cleaned = clean_power_origin_context(power_origin)

        # Should replace problematic terms with generic ones
        technique = cleaned["canon_techniques"][0]
        assert "cursed technique" not in technique["name"].lower()
        assert "cursed energy" not in technique["description"].lower()
        assert "technique" in technique["name"].lower()  # Generic replacement
        assert "energy" in technique["description"].lower()  # Generic replacement

    def test_cleans_combat_style_field(self):
        """Remove universe terms from combat_style field."""
        power_origin = {
            "power_name": "Combat Power",
            "original_wielder": "Fighter",
            "combat_style": "Uses Cursed Technique to control domain expansion",
            "canon_techniques": [],
        }

        cleaned = clean_power_origin_context(power_origin)

        style = cleaned["combat_style"]
        assert "cursed technique" not in style.lower()
        assert "domain expansion" not in style.lower()
        # Should have generic replacements
        assert "technique" in style.lower()
        assert "ability" in style.lower()

    def test_cleans_weaknesses_list(self):
        """Remove universe terms from weaknesses_and_counters list."""
        power_origin = {
            "power_name": "Magic Caster",
            "original_wielder": "Wizard",
            "weaknesses_and_counters": [
                "Vulnerable to Cursed Energy attacks",
                "Binding Vow contracts limit power",
            ],
            "canon_techniques": [],
        }

        cleaned = clean_power_origin_context(power_origin)

        weaknesses = cleaned["weaknesses_and_counters"]
        combined = " ".join(weaknesses).lower()
        assert "cursed energy" not in combined
        assert "binding vow" not in combined
        # Should have replacements
        assert "energy" in combined
        assert "limitation" in combined or "contract" in combined

    def test_preserves_non_leakage_content(self):
        """Ensure clean content is not modified."""
        power_origin = {
            "power_name": "Time Manipulation",
            "original_wielder": "Time Keeper",
            "canon_techniques": [
                {
                    "name": "Temporal Acceleration",
                    "description": "Speed up local time flow in targeted area",
                }
            ],
            "combat_style": "Defensive use of time slowing to avoid attacks",
            "signature_moves": ["Time Dilation", "Chronological Lock"],
        }

        cleaned = clean_power_origin_context(power_origin)

        # Original content should be preserved
        assert cleaned["power_name"] == power_origin["power_name"]
        assert cleaned["canon_techniques"] == power_origin["canon_techniques"]
        assert cleaned["combat_style"] == power_origin["combat_style"]
        assert cleaned["signature_moves"] == power_origin["signature_moves"]

    def test_preserves_source_universe_context(self):
        """source_universe_context field should not be cleaned."""
        power_origin = {
            "power_name": "Clean Power",
            "original_wielder": "Someone",
            "canon_techniques": [],
            "source_universe_context": {
                "original_name": "Cursed Technique Reversal",
                "source_system": "Jujutsu Kaisen cursed energy system",
                "universe_context": "Uses Cursed Energy mechanics from JJK",
            },
        }

        cleaned = clean_power_origin_context(power_origin)

        # source_universe_context should be unchanged
        assert cleaned["source_universe_context"] == power_origin["source_universe_context"]

    def test_handles_missing_canon_techniques(self):
        """Handle cleaning when canon_techniques is missing."""
        power_origin = {
            "power_name": "Power",
            "original_wielder": "User",
            # Missing: canon_techniques
        }

        cleaned = clean_power_origin_context(power_origin)

        assert isinstance(cleaned, dict)
        assert "power_name" in cleaned


class TestRemoveUniverseTermsHelper:
    """Test the _remove_universe_terms helper function."""

    def test_removes_jjk_terms(self):
        """Remove JJK-specific terminology."""
        text = "Cursed Technique Reversal uses Cursed Energy"
        all_terms = {
            "cursed technique": "jjk",
            "cursed energy": "jjk",
        }

        result = _remove_universe_terms(text, all_terms)

        assert "cursed technique" not in result.lower()
        assert "cursed energy" not in result.lower()
        assert "technique" in result
        assert "energy" in result

    def test_case_insensitive_replacement(self):
        """Replace terms regardless of case."""
        text = "Uses CURSED ENERGY and Cursed Energy and cursed energy"
        all_terms = {"cursed energy": "jjk"}

        result = _remove_universe_terms(text, all_terms)

        # All variants should be replaced
        assert "cursed energy" not in result.lower()
        assert "CURSED ENERGY" not in result
        assert "energy" in result.lower()

    def test_preserves_non_matching_text(self):
        """Don't modify text that doesn't contain forbidden terms."""
        text = "This is a clean description with no universe-specific terms"
        all_terms = {"cursed energy": "jjk"}

        result = _remove_universe_terms(text, all_terms)

        assert result == text

    def test_handles_multiple_terms_in_text(self):
        """Replace multiple different terms in single text."""
        text = "Cursed Technique using Cursed Energy with domain expansion"
        all_terms = {
            "cursed technique": "jjk",
            "cursed energy": "jjk",
            "domain expansion": "jjk",
        }

        result = _remove_universe_terms(text, all_terms)

        assert "cursed" not in result.lower()
        assert "domain expansion" not in result.lower()


class TestCrossoverPowerIsolation:
    """Test the complete workflow for crossover power isolation."""

    def test_jjk_power_in_wormverse_story(self):
        """
        Integration test: JJK power (Gojo's Reversal) in Wormverse story.

        This is the canonical use case for Issue #33:
        - A power from Jujutsu Kaisen universe
        - Being used in a Wormverse fanfic
        - Should have universe context isolated from mechanics
        """
        # Power as it might be imported from JJK universe
        jjk_power_leaky = {
            "power_name": "Reversal Counter",
            "original_wielder": "Gojo Satoru",
            "canon_techniques": [
                {
                    "name": "Cursed Technique Reversal",
                    "description": "Inversion technique that inverts Cursed Energy attacks",
                }
            ],
            "combat_style": "Uses domain expansion and Cursed Energy manipulation",
            "weaknesses_and_counters": [
                "Vulnerable to techniques that bypass Cursed Technique defenses",
                "Cannot be used in areas where Cursed Energy is suppressed",
            ],
        }

        # Detect leakage
        warnings = check_power_origin_context_leakage(jjk_power_leaky)
        assert len(warnings) > 0, "Should detect JJK terminology leakage"

        # Clean for Wormverse usage
        cleaned_power = clean_power_origin_context(jjk_power_leaky)

        # Verify no leakage after cleaning
        warnings_after = check_power_origin_context_leakage(cleaned_power)
        assert len(warnings_after) == 0, "No warnings should remain after cleaning"

        # Verify mechanics are preserved but generalized
        technique = cleaned_power["canon_techniques"][0]
        assert "reversal" in technique["name"].lower()  # Core mechanic preserved
        assert "inversion" in technique["description"].lower()  # Core mechanic preserved
        assert "cursed" not in technique["description"].lower()  # JJK term removed
        assert "cursed technique" not in technique["name"].lower()

        # Verify combat style is generalized
        style = cleaned_power["combat_style"].lower()
        assert "domain" not in style or "ability" in style  # domain_expansion → large-scale ability
        assert "energy" in style  # cursed energy → energy

    def test_worm_power_in_jjk_universe(self):
        """
        Integration test: Worm power (Skitter's control) in JJK story.

        Reverse scenario: Worm power adapted for JJK universe.
        """
        worm_power_leaky = {
            "power_name": "Master",
            "original_wielder": "Skitter",
            "canon_techniques": [
                {
                    "name": "Swarm Control",
                    "description": "Parahuman power to trigger and control insects",
                }
            ],
            "combat_style": "Uses trigger event powers to swarm opponents",
        }

        # Detect leakage
        warnings = check_power_origin_context_leakage(worm_power_leaky)
        assert len(warnings) > 0, "Should detect Worm terminology"

        # Clean
        cleaned = clean_power_origin_context(worm_power_leaky)

        # Verify no leakage
        warnings_after = check_power_origin_context_leakage(cleaned)
        assert len(warnings_after) == 0

        # Verify mechanics are preserved
        assert "swarm" in cleaned["power_name"].lower() or "control" in cleaned["canon_techniques"][0]["name"].lower()
        assert "parahuman" not in cleaned["canon_techniques"][0]["description"].lower()
        assert "trigger event" not in cleaned["combat_style"].lower()

    def test_consecutive_cleaning_is_idempotent(self):
        """Cleaning an already-clean power shouldn't change it."""
        power_origin = {
            "power_name": "Reversal",
            "original_wielder": "Someone",
            "canon_techniques": [
                {
                    "name": "Reversal Technique",
                    "description": "Inversion technique that negates incoming attacks",
                }
            ],
        }

        cleaned_once = clean_power_origin_context(power_origin)
        cleaned_twice = clean_power_origin_context(cleaned_once)

        # Should be identical after second cleaning
        assert cleaned_once == cleaned_twice


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
