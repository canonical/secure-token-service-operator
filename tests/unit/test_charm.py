#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from ops.model import ActiveStatus
from scenario import Container, Context, State

from charm import SecureTokenServiceCharm


@pytest.fixture
def context():
    """Provides a Scenario Context for the charm."""
    return Context(SecureTokenServiceCharm)


def test_pebble_ready(context):
    """Test that the pebble_ready event sets up the container and goes active."""
    # 1. Arrange
    container = Container("secure-token-service", can_connect=True)
    state_in = State(containers=[container])

    # 2. Act
    # Using the string name of the event is the safest way across all scenario versions
    state_out = context.run(context.on.pebble_ready(container), state_in)

    # 3. Assert
    assert state_out.unit_status == ActiveStatus()

    # Verify the pebble layer was applied correctly with the default config (info)
    container_out = state_out.get_container("secure-token-service")
    layer = container_out.layers["secure-token-service"]

    assert "secure-token-service" in layer.services
    service = layer.services["secure-token-service"]
    assert service.environment["LOG_LEVEL"] == "info"
