# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.


from collections.abc import Callable

from ops import ConfigData

from constants import OPENID_PROVIDER
from env_vars import EnvVars


class CharmConfig:
    """A class representing the data source of charm configurations."""

    def __init__(
        self, config: ConfigData, external_url: Callable[[], str | None] = lambda: None
    ) -> None:
        self._config = config
        self._external_url = external_url

    @property
    def provider(self) -> str:
        """The configured default authentication provider."""
        return str(self._config["default_auth_provider"])

    def _resolve_realm(self) -> str:
        """Resolve the OpenID realm from config or, for openid, the ingress external URL."""
        if realm := self._config["ubuntu_one_realm"]:
            return str(realm)
        if self.provider == OPENID_PROVIDER:
            return self._external_url() or ""
        return ""

    def to_env_vars(self) -> EnvVars:
        env_vars = {
            "LOG_LEVEL": self._config["log_level"],
            "HTTP_PROXY": self._config["http_proxy"],
            "HTTPS_PROXY": self._config["https_proxy"],
            "NO_PROXY": self._config["no_proxy"],
            "DEFAULT_AUTH_PROVIDER": self.provider,
            "UBUNTU_ONE_OPENID_URL": self._config["ubuntu_one_openid_url"],
        }
        if realm := self._resolve_realm():
            env_vars["UBUNTU_ONE_REALM"] = realm
        return env_vars
