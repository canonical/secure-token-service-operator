# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, create_autospec, patch

import pytest
from charmlibs.interfaces.istio_ingress_route import ProtocolType
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.hydra.v0.oauth import OAuthRequirer
from dpcharmlibs.interfaces.errors import (
    DataInterfacesError,
    SecretError,
    SecretsUnavailableError,
)
from ops import ModelError
from pydantic import ValidationError
from pytest_mock import MockerFixture

from constants import (
    COOKIE_SECRET_KEY,
    POSTGRESQL_DSN_TEMPLATE,
)
from integrations import (
    CacheConfig,
    DatabaseConfig,
    IstioIngressIntegration,
    OAuthConfig,
    PeerData,
    TrustedCertificatesTransferIntegration,
)


class TestPeerData:
    @pytest.fixture
    def mocked_app(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mocked_model(self, mocked_app: MagicMock) -> MagicMock:
        model = MagicMock()
        model.app = mocked_app
        model.unit.is_leader.return_value = True
        return model

    @pytest.fixture
    def mocked_peer_integration_data(self, mocked_app: MagicMock, mocked_model: MagicMock) -> dict:
        peer_integration = MagicMock()
        peer_integration.data = {mocked_app: {}}
        mocked_model.get_relation.return_value = peer_integration
        return peer_integration.data[mocked_app]

    @pytest.fixture
    def peer_data(self, mocked_model: MagicMock, mocked_peer_integration_data: dict) -> PeerData:
        return PeerData(mocked_model)

    def test_get_with_existing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        mocked_peer_integration_data["key"] = '"val"'
        assert peer_data["key"] == "val"

    def test_get_with_missing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        assert not peer_data["missing"]

    def test_get_without_peer_integration(self, mocked_model: MagicMock) -> None:
        mocked_model.get_relation.return_value = None
        peer_data = PeerData(mocked_model)
        assert not peer_data["key"]

    def test_set(self, mocked_peer_integration_data: dict, peer_data: PeerData) -> None:
        peer_data["key"] = "val"
        assert mocked_peer_integration_data["key"] == '"val"'

    def test_pop_with_existing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        mocked_peer_integration_data["key"] = '"val"'

        actual = peer_data.pop("key")
        assert actual == "val"
        assert "key" not in mocked_peer_integration_data

    def test_keys(self, mocked_peer_integration_data: dict, peer_data: PeerData) -> None:
        mocked_peer_integration_data.update({"x": "1", "y": "2"})
        keys = [k for k in peer_data.keys() if k != COOKIE_SECRET_KEY]
        assert keys == ["x", "y"]

    def test_to_env_vars(self, peer_data: PeerData) -> None:
        peer_data[COOKIE_SECRET_KEY] = "test-secret"
        env = peer_data.to_env_vars()
        assert env["COOKIE_HASH_KEY"] == "test-secret"


class TestDatabaseConfig:
    @pytest.fixture
    def database_config(self) -> DatabaseConfig:
        return DatabaseConfig(
            username="sts_user",
            password="sts_password",
            endpoint="pg.internal",
            database="sts",
            migration_version="migration_version_1",
        )

    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(DatabaseRequires)

    def test_dsn(self, database_config: DatabaseConfig) -> None:
        expected = POSTGRESQL_DSN_TEMPLATE.substitute(
            username="sts_user",
            password="sts_password",
            endpoint="pg.internal",
            database="sts",
        )

        actual = database_config.dsn
        assert actual == expected

    def test_to_env_vars(self, database_config: DatabaseConfig) -> None:
        env_vars = database_config.to_env_vars()
        assert env_vars["DATABASE_URL"] == database_config.dsn

    def test_load_with_integration(self, mocked_requirer: MagicMock) -> None:
        integration_id = 1
        mocked_requirer.relations = [MagicMock(id=integration_id)]
        mocked_requirer.database = "sts"
        mocked_requirer.fetch_relation_data.return_value = {
            integration_id: {
                "endpoints": "pg.internal:5432,pg2.internal:5432",
                "username": "sts_user",
                "password": "sts_password",
            }
        }

        actual = DatabaseConfig.load(mocked_requirer)
        assert actual == DatabaseConfig(
            username="sts_user",
            password="sts_password",
            endpoint="pg.internal:5432",
            database="sts",
            migration_version="migration_version_1",
        )

    def test_load_without_integration(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.database = "sts"
        mocked_requirer.relations = []

        actual = DatabaseConfig.load(mocked_requirer)
        assert actual == DatabaseConfig()


class TestCacheConfig:
    @pytest.fixture
    def cache_config(self) -> CacheConfig:
        return CacheConfig(
            endpoint="valkey.internal:6379",
            username="sts_cache_user",
            password="sts_cache_password",
        )

    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return MagicMock()

    def test_to_env_vars(self, cache_config: CacheConfig) -> None:
        env_vars = cache_config.to_env_vars()
        assert env_vars == {
            "CACHE_ADDR": "valkey.internal:6379",
            "CACHE_USERNAME": "sts_cache_user",
            "CACHE_PASSWORD": "sts_cache_password",
        }

    def test_to_env_vars_empty(self) -> None:
        cache_config = CacheConfig()
        assert cache_config.to_env_vars() == {}

    def test_load_without_integration(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.relations = []

        actual = CacheConfig.load(mocked_requirer)
        assert actual == CacheConfig()

    def test_load_when_no_relation_app(self, mocked_requirer: MagicMock) -> None:
        mocked_relation = MagicMock(id=1, app=None)
        mocked_requirer.relations = [mocked_relation]

        actual = CacheConfig.load(mocked_requirer)
        assert actual == CacheConfig()

    def test_load_when_no_requests(self, mocked_requirer: MagicMock) -> None:
        mocked_relation = MagicMock(id=1, app=MagicMock())
        mocked_requirer.relations = [mocked_relation]
        mock_model = MagicMock()
        mock_model.requests = []
        mocked_requirer.interface.build_model.return_value = mock_model

        actual = CacheConfig.load(mocked_requirer)
        assert actual == CacheConfig()

    def test_load_when_no_endpoints(self, mocked_requirer: MagicMock) -> None:
        mocked_relation = MagicMock(id=1, app=MagicMock())
        mocked_requirer.relations = [mocked_relation]
        mock_response = MagicMock()
        mock_response.endpoints = ""
        mock_response.password = "sts_cache_password"
        mock_model = MagicMock()
        mock_model.requests = [mock_response]
        mocked_requirer.interface.build_model.return_value = mock_model

        actual = CacheConfig.load(mocked_requirer)
        assert actual == CacheConfig()

    def test_load_when_no_password(self, mocked_requirer: MagicMock) -> None:
        mocked_relation = MagicMock(id=1, app=MagicMock())
        mocked_requirer.relations = [mocked_relation]
        mock_response = MagicMock()
        mock_response.endpoints = "valkey.internal:6379"
        mock_response.password = ""
        mock_model = MagicMock()
        mock_model.requests = [mock_response]
        mocked_requirer.interface.build_model.return_value = mock_model

        actual = CacheConfig.load(mocked_requirer)
        assert actual == CacheConfig()

    def test_load_with_integration_ready(self, mocked_requirer: MagicMock) -> None:
        mocked_relation = MagicMock(id=1, app=MagicMock())
        mocked_requirer.relations = [mocked_relation]

        mock_response = MagicMock()
        mock_response.endpoints = "valkey.internal:6379,valkey-replica.internal:6379"
        mock_response.username = "sts_cache_user"
        mock_response.password = "sts_cache_password"

        mock_model = MagicMock()
        mock_model.requests = [mock_response]
        mocked_requirer.interface.build_model.return_value = mock_model

        actual = CacheConfig.load(mocked_requirer)
        assert actual == CacheConfig(
            endpoint="valkey.internal:6379",
            username="sts_cache_user",
            password="sts_cache_password",
        )

    @pytest.mark.parametrize(
        "exception",
        [
            DataInterfacesError("Invalid databag"),
            ValidationError.from_exception_data(title="test", line_errors=[]),
            SecretError("Secret not ready"),
            SecretsUnavailableError("Secrets unavailable"),
            ModelError("Juju model error"),
            ValueError("Missing relation"),
        ],
    )
    def test_load_when_exception_raised(
        self,
        mocked_requirer: MagicMock,
        exception: Exception,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        mocked_relation = MagicMock(id=1, app=MagicMock())
        mocked_requirer.relations = [mocked_relation]
        mocked_requirer.interface.build_model.side_effect = exception

        actual = CacheConfig.load(mocked_requirer)
        assert actual == CacheConfig()
        assert "Failed to load cache configuration" in caplog.text


class TestOAuthConfig:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(OAuthRequirer)

    def test_load_with_provider_info(self, mocked_requirer: MagicMock) -> None:
        mock_provider_info = MagicMock()
        mock_provider_info.issuer_url = "https://hydra.internal"
        mock_provider_info.client_id = "sts-client"
        mock_provider_info.client_secret = "secret-123"
        mocked_requirer.get_provider_info.return_value = mock_provider_info

        actual = OAuthConfig.load(mocked_requirer, redirect_url="https://sts.com/callback")

        assert actual == OAuthConfig(
            provider_url="https://hydra.internal",
            client_id="sts-client",
            client_secret="secret-123",
            redirect_url="https://sts.com/callback",
        )

    def test_load_without_provider_info(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_provider_info.return_value = None

        actual = OAuthConfig.load(mocked_requirer, redirect_url="https://sts.com/callback")
        assert actual == OAuthConfig(redirect_url="https://sts.com/callback")

    def test_to_env_vars(self) -> None:
        config = OAuthConfig(
            provider_url="https://hydra.internal",
            client_id="sts-client",
            client_secret="secret",
            redirect_url="https://sts.com/callback",
        )
        actual = config.to_env_vars()

        assert actual == {
            "OIDC_PROVIDER_URL": "https://hydra.internal",
            "OIDC_CLIENT_ID": "sts-client",
            "OIDC_CLIENT_SECRET": "secret",
            "OIDC_REDIRECT_URL": "https://sts.com/callback",
        }


class TestTrustedCertificatesTransferIntegration:
    @pytest.fixture
    def mocked_charm(self) -> MagicMock:
        charm = MagicMock()
        charm._container = MagicMock()
        return charm

    def test_update_trusted_ca_certs(self, mocked_charm: MagicMock, mocker: MockerFixture) -> None:
        integration = TrustedCertificatesTransferIntegration(mocked_charm)
        mock_push = mocker.patch.object(integration, "_push_ca_certs")
        mocked_charm.model.get_relation.return_value = True

        integration.update_trusted_ca_certs()

        mock_push.assert_called_once()


class TestIstioIngressIntegration:
    @pytest.fixture
    def mocked_charm(self) -> MagicMock:
        charm = MagicMock()
        charm.model.name = "testing"
        charm.app.name = "secure-token-service"
        return charm

    def test_external_url_with_tls(self, mocked_charm: MagicMock) -> None:
        integration = IstioIngressIntegration(mocked_charm, relation_name="ingress")
        integration.requirer = MagicMock()
        integration.requirer.external_host = "sts.com"
        integration.requirer.tls_enabled = True

        assert integration.external_url == "https://sts.com"

    def test_external_url_without_tls(self, mocked_charm: MagicMock) -> None:
        integration = IstioIngressIntegration(mocked_charm, relation_name="ingress")
        integration.requirer = MagicMock()
        integration.requirer.external_host = "sts.com"
        integration.requirer.tls_enabled = False

        assert integration.external_url == "http://sts.com"

    def test_external_url_not_ready(self, mocked_charm: MagicMock) -> None:
        integration = IstioIngressIntegration(mocked_charm, relation_name="ingress")
        integration.requirer = MagicMock()
        integration.requirer.external_host = None

        assert integration.external_url is None

    @patch("integrations.IstioIngressRouteConfig")
    def test_submit_routes_tls_enabled(
        self, mocked_route_config: MagicMock, mocked_charm: MagicMock
    ) -> None:
        integration = IstioIngressIntegration(mocked_charm, relation_name="ingress")
        integration.requirer = MagicMock()
        integration.requirer.tls_enabled = True

        integration.submit_routes()

        mocked_route_config.assert_called_once()
        listeners = mocked_route_config.call_args.kwargs["listeners"]
        assert len(listeners) == 1
        assert listeners[0].port == 443
        assert listeners[0].protocol == ProtocolType.HTTP
        integration.requirer.submit_config.assert_called_once_with(
            mocked_route_config.return_value
        )

    @patch("integrations.IstioIngressRouteConfig")
    def test_submit_routes_tls_disabled(
        self, mocked_route_config: MagicMock, mocked_charm: MagicMock
    ) -> None:
        integration = IstioIngressIntegration(mocked_charm, relation_name="ingress")
        integration.requirer = MagicMock()
        integration.requirer.tls_enabled = False

        integration.submit_routes()

        mocked_route_config.assert_called_once()
        listeners = mocked_route_config.call_args.kwargs["listeners"]
        assert len(listeners) == 1
        assert listeners[0].port == 80
        assert listeners[0].protocol == ProtocolType.HTTP
        integration.requirer.submit_config.assert_called_once_with(
            mocked_route_config.return_value
        )
