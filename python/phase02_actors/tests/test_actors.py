"""
Test Actors - Phase-02 Actors
REIMPLEMENTED-2026

Tests for Actor definitions.
These tests MUST fail initially until implementation is complete.
"""

import pytest


class TestActorRegistry:
    """Tests for actor registry."""

    def test_actor_registry_exists(self):
        """Verify ActorRegistry exists."""
        from python.phase02_actors.actors import ActorRegistry
        assert ActorRegistry is not None

    def test_actor_registry_has_human(self):
        """Verify registry has HUMAN actor."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        assert registry.get_actor("HUMAN") is not None

    def test_actor_registry_has_system(self):
        """Verify registry has SYSTEM actor."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        assert registry.get_actor("SYSTEM") is not None

    def test_actor_registry_only_two_actors(self):
        """Verify registry has exactly two actors."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        all_actors = registry.get_all_actors()
        assert len(all_actors) == 2


class TestActorClass:
    """Tests for Actor class."""

    def test_actor_class_exists(self):
        """Verify Actor class exists."""
        from python.phase02_actors.actors import Actor
        assert Actor is not None

    def test_actor_has_id(self):
        """Verify Actor has actor_id."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        human = registry.get_actor("HUMAN")
        assert hasattr(human, 'actor_id')
        assert human.actor_id == "HUMAN"

    def test_actor_has_actor_type(self):
        """Verify Actor has actor_type."""
        from python.phase02_actors.actors import ActorRegistry, ActorType
        registry = ActorRegistry()
        human = registry.get_actor("HUMAN")
        assert hasattr(human, 'actor_type')
        assert human.actor_type == ActorType.HUMAN

    def test_actor_has_name(self):
        """Verify Actor has name."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        human = registry.get_actor("HUMAN")
        assert hasattr(human, 'name')
        assert len(human.name) > 0

    def test_actor_has_trust_level(self):
        """Verify Actor has trust_level."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        human = registry.get_actor("HUMAN")
        assert hasattr(human, 'trust_level')


class TestActorType:
    """Tests for ActorType enum."""

    def test_actor_type_enum_exists(self):
        """Verify ActorType enum exists."""
        from python.phase02_actors.actors import ActorType
        assert ActorType is not None

    def test_actor_type_has_human(self):
        """Verify ActorType has HUMAN."""
        from python.phase02_actors.actors import ActorType
        assert ActorType.HUMAN is not None

    def test_actor_type_has_system(self):
        """Verify ActorType has SYSTEM."""
        from python.phase02_actors.actors import ActorType
        assert ActorType.SYSTEM is not None

    def test_only_two_actor_types(self):
        """Verify only HUMAN and SYSTEM actor types exist."""
        from python.phase02_actors.actors import ActorType
        assert len(ActorType) == 2


class TestActorImmutability:
    """Tests for actor immutability."""

    def test_actor_is_frozen(self):
        """Verify Actor is immutable."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        human = registry.get_actor("HUMAN")
        
        with pytest.raises((AttributeError, TypeError)):
            human.actor_id = "HACKED"

    def test_registry_actors_immutable(self):
        """Verify registry returns same actors."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        
        human1 = registry.get_actor("HUMAN")
        human2 = registry.get_actor("HUMAN")
        
        assert human1 is human2


class TestActorTrustLevels:
    """Tests for actor trust levels."""

    def test_human_has_full_trust(self):
        """Verify HUMAN has maximum trust level."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        human = registry.get_actor("HUMAN")
        assert human.trust_level == 100

    def test_system_has_no_trust(self):
        """Verify SYSTEM has zero trust level."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        system = registry.get_actor("SYSTEM")
        assert system.trust_level == 0

    def test_human_trust_greater_than_system(self):
        """Verify HUMAN trust is always greater than SYSTEM."""
        from python.phase02_actors.actors import ActorRegistry
        registry = ActorRegistry()
        human = registry.get_actor("HUMAN")
        system = registry.get_actor("SYSTEM")
        assert human.trust_level > system.trust_level
