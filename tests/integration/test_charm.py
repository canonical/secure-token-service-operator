#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant
import pytest

logger = logging.getLogger(__name__)


@pytest.mark.skip(reason="OCI image is not yet published to ghcr.io")
async def test_deploy_charm(juju: jubilant.Juju):
    """Placeholder for future deployment test."""
    pass
