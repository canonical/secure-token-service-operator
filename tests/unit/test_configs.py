# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

from configs import CharmConfig

DEFAULT_CHARM_DATA = {
    "log_level": "info",
    "http_proxy": "http://squid.internal:3128",
    "https_proxy": "http://squid.internal:3128",
    "no_proxy": "localhost,127.0.0.1,.svc.cluster.local",
    "default_auth_provider": "oidc",
    "ubuntu_one_openid_url": "https://login.ubuntu.com/+openid",
    "ubuntu_one_realm": "",
}


def create_charm_config(external_url: str | None = None, **overrides: str) -> CharmConfig:
    config_data = {**DEFAULT_CHARM_DATA, **overrides}
    mocked_config = MagicMock()
    mocked_config.__getitem__.side_effect = lambda key: config_data[key]
    return CharmConfig(mocked_config, lambda: external_url)


class TestCharmConfig:
    @patch("ops.model.ConfigData", autospec=True)
    def test_to_env_vars(self, mocked_class: MagicMock) -> None:
        mocked_config = mocked_class.return_value

        mocked_charm_data = {
            "log_level": "info",
            "http_proxy": "http://squid.internal:3128",
            "https_proxy": "http://squid.internal:3128",
            "no_proxy": "localhost,127.0.0.1,.svc.cluster.local",
            "default_auth_provider": "oidc",
            "ubuntu_one_openid_url": "https://login.ubuntu.com/+openid",
            "ubuntu_one_realm": "",
        }

        mocked_config.__getitem__.side_effect = lambda key: mocked_charm_data[key]
        charm_config = CharmConfig(mocked_config)

        result = charm_config.to_env_vars()

        assert result == {
            "LOG_LEVEL": "info",
            "HTTP_PROXY": "http://squid.internal:3128",
            "HTTPS_PROXY": "http://squid.internal:3128",
            "NO_PROXY": "localhost,127.0.0.1,.svc.cluster.local",
            "DEFAULT_AUTH_PROVIDER": "oidc",
            "UBUNTU_ONE_OPENID_URL": "https://login.ubuntu.com/+openid",
        }

    def test_provider_property(self) -> None:
        charm_config = create_charm_config(default_auth_provider="openid")

        assert charm_config.provider == "openid"

    def test_explicit_realm_is_mapped(self) -> None:
        charm_config = create_charm_config(
            default_auth_provider="openid",
            ubuntu_one_realm="https://sts.example.com",
        )

        result = charm_config.to_env_vars()

        assert result["UBUNTU_ONE_REALM"] == "https://sts.example.com"

    def test_realm_derived_from_external_url_for_openid(self) -> None:
        charm_config = create_charm_config(
            external_url="https://ingress.example.com",
            default_auth_provider="openid",
        )

        result = charm_config.to_env_vars()

        assert result["UBUNTU_ONE_REALM"] == "https://ingress.example.com"

    def test_explicit_realm_wins_over_external_url(self) -> None:
        charm_config = create_charm_config(
            external_url="https://ingress.example.com",
            default_auth_provider="openid",
            ubuntu_one_realm="https://sts.example.com",
        )

        result = charm_config.to_env_vars()

        assert result["UBUNTU_ONE_REALM"] == "https://sts.example.com"

    def test_no_realm_emitted_for_oidc(self) -> None:
        charm_config = create_charm_config(external_url="https://ingress.example.com")

        result = charm_config.to_env_vars()

        assert "UBUNTU_ONE_REALM" not in result

    def test_no_realm_emitted_for_openid_without_resolution(self) -> None:
        charm_config = create_charm_config(default_auth_provider="openid")

        result = charm_config.to_env_vars()

        assert "UBUNTU_ONE_REALM" not in result
