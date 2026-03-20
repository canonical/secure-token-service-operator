#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Secure Token Service (STS) Operator."""

import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus

logger = logging.getLogger(__name__)


class SecureTokenServiceCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self.container_name = "secure-token-service"

        self.framework.observe(
            self.on.secure_token_service_pebble_ready,
            self._on_pebble_ready
        )

    def _on_pebble_ready(self, event):
        """Handle pebble-ready event."""
        container = event.workload
        container.add_layer(self.container_name, self._pebble_layer, combine=True)
        container.autostart()
        self.unit.status = ActiveStatus()

    @property
    def _pebble_layer(self):
        return {
            "summary": "secure token service layer",
            "description": "pebble config layer for sts",
            "services": {
                self.container_name: {
                    "override": "replace",
                    "summary": "secure token service",
                    # TEMPLATE-TODO: Update with the actual entrypoint command of your image
                    "command": "/usr/local/bin/secure-token-service",
                    "startup": "enabled",
                    "environment": {
                        "LOG_LEVEL": self.model.config.get("log_level", "info")
                    },
                }
            },
        }


if __name__ == "__main__":
    main(SecureTokenServiceCharm)
