# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.


from ops import ConfigData

from env_vars import EnvVars


class CharmConfig:
    """A class representing the data source of charm configurations."""

    def __init__(self, config: ConfigData) -> None:
        self._config = config

    def to_env_vars(self) -> EnvVars:
        return {
            "LOG_LEVEL": self._config["log_level"],
            "HTTP_PROXY": self._config["http_proxy"],
            "HTTPS_PROXY": self._config["https_proxy"],
            "NO_PROXY": self._config["no_proxy"],
        }
