# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Any
from unittest.mock import MagicMock, PropertyMock, create_autospec

import pytest
from ops import ActiveStatus, Container, Unit, testing
from pytest_mock import MockerFixture

from constants import (
    DATABASE_INTEGRATION_NAME,
    OAUTH_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    RECEIVE_CA_CERT_INTEGRATION_NAME,
    STS_INFO_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)

APP_NAME = "secure-token-service"
MODEL_NAME = "testing"
COOKIE_SECRET = "8f4e9b2d7c1a5f6e3d0b8c9a2f4e1d7b0c3a5f8e9d2b4c6a1f3e5d7b0c9a8f2e"
OAUTH_CLIENT_ID = "sts_client_id"
OAUTH_CLIENT_SECRET = "s3cR#T"
OAUTH_PROVIDER_INFO = {
    "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
    "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
    "issuer_url": "https://example.oidc.com",
    "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
    "scope": "openid profile email phone",
    "token_endpoint": "https://example.oidc.com/oauth2/token",
    "userinfo_endpoint": "https://example.oidc.com/userinfo",
}
OAUTH_SECRET_ID = "secret:hydra-test-secret-123"
VALKEY_ADDRESS = "valkey:6379"
VALKEY_PASSWORD = "some-pwd"
VALKEY_USERNAME = "valkey-user"


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture) -> None:
    """Mocks the KubernetesComputeResourcesPatch to prevent file lookups during tests."""
    mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="testing",
        _patch=lambda *a, **kw: None,
        is_ready=lambda *a, **kw: True,
        get_status=lambda *a, **kw: ActiveStatus(),
    )


def create_state(
    *,
    leader: bool = True,
    can_connect: bool = True,
    config: dict[str, Any] | None = None,
    container: testing.Container | None = None,
    relations: list[testing.Relation] | None = None,
    secrets: list[testing.Secret] | None = None,
    execs: list[testing.Exec] | None = None,
) -> testing.State:
    """Factory function to create charm state with explicit parameters."""
    if container is None:
        execs_list = [
            testing.Exec(
                ["/usr/bin/app", "version"],
                return_code=0,
                stdout="0.2.1\n",
            )
        ] if can_connect else []

        if execs and can_connect:
            execs_list.extend(execs)

        container = testing.Container(
            name=WORKLOAD_CONTAINER,
            can_connect=can_connect,
            execs=execs_list,
        )

    return testing.State(
        containers=[container],
        config=config or {},
        leader=leader,
        model=testing.Model(name=MODEL_NAME),
        relations=relations or [],
        secrets=secrets or [],
    )


@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


@pytest.fixture
def mocked_unit(mocked_container: MagicMock) -> MagicMock:
    mocked = create_autospec(Unit)
    mocked.get_container.return_value = mocked_container
    return mocked


@pytest.fixture
def mocked_migration_needed(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.SecureTokenServiceCharm.migration_needed", new_callable=PropertyMock, return_value=False
    )


@pytest.fixture
def mocked_cli_migrate(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.CommandLine.migrate")


@pytest.fixture
def peer_integration() -> testing.PeerRelation:
    return testing.PeerRelation(
        endpoint=PEER_INTEGRATION_NAME,
        interface="secure-token-service-peer",
        local_app_data={"cookies_key": json.dumps(COOKIE_SECRET)},
    )


@pytest.fixture
def database_integration() -> testing.Relation:
    return testing.Relation(
        endpoint=DATABASE_INTEGRATION_NAME,
        interface="postgresql_client",
        remote_app_name="database",
        remote_app_data={
            "data": '{"database": "sts", "extra-user-roles": "SUPERUSER"}',
            "database": "sts",
            "endpoints": "pg.internal:5432",
            "username": "sts_user",
            "password": "sts_password",
        },
    )


@pytest.fixture
def oauth_secret() -> testing.Secret:
    """Creates the Secret object containing the client_secret."""
    return testing.Secret(
        id=OAUTH_SECRET_ID,
        label="hydra-oauth-secret",
        tracked_content={"secret": OAUTH_CLIENT_SECRET},
        owner="remote",
    )


@pytest.fixture
def oauth_integration() -> testing.Relation:
    return testing.Relation(
        endpoint=OAUTH_INTEGRATION_NAME,
        interface="oauth",
        remote_app_name="hydra",
        remote_app_data={
            "client_id": OAUTH_CLIENT_ID,
            "client_secret_id": OAUTH_SECRET_ID,
            **OAUTH_PROVIDER_INFO,
        },
        local_app_data={
            "audience": "[]",
            "redirect_uri": "http://secure-token-service.testing.svc.cluster.local:8080/auth/callback",
            "scope": "openid email profile offline_access",
            "token_endpoint_auth_method": "client_secret_basic",
            "grant_types": '["authorization_code", "refresh_token"]',
        },
    )


@pytest.fixture
def receive_ca_cert_integration() -> testing.Relation:
    return testing.Relation(
        endpoint=RECEIVE_CA_CERT_INTEGRATION_NAME,
        interface="certificate_transfer",
        remote_app_name="send-ca-cert",
    )


@pytest.fixture
def ingress_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="ingress",
        interface="istio_ingress_route",
        remote_app_name="istio-ingress-k8s",
    )


@pytest.fixture
def service_mesh_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="service-mesh",
        interface="service_mesh",
        remote_app_name="istio-beacon-k8s",
    )


@pytest.fixture
def mocked_workload_service_version(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.WorkloadService.version", new_callable=PropertyMock, return_value="0.2.1"
    )


@pytest.fixture
def mocked_charm_holistic_handler(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.SecureTokenServiceCharm._holistic_handler")


@pytest.fixture(autouse=True)
def mocked_push_ca_certs(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "integrations.TrustedCertificatesTransferIntegration._push_ca_certs", return_value=None
    )


@pytest.fixture
def mocked_submit_routes(mocker: MockerFixture) -> MagicMock:
    """Mocks the Istio integration route submission."""
    return mocker.patch("integrations.IstioIngressIntegration.submit_routes")


@pytest.fixture
def mocked_update_client_config(mocker: MockerFixture) -> MagicMock:
    """Mocks the OAuth library client configuration update."""
    return mocker.patch("charms.hydra.v0.oauth.OAuthRequirer.update_client_config")


@pytest.fixture
def sts_info_integration() -> testing.Relation:
    return testing.Relation(
        endpoint=STS_INFO_INTEGRATION_NAME,
        interface="sts_info",
        remote_app_name="some-consumer",
    )
