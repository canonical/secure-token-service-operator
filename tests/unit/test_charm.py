#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import MagicMock, patch

from conftest import (
    APP_NAME,
    COOKIE_SECRET,
    MODEL_NAME,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_PROVIDER_INFO,
    VALKEY_ADDRESS,
    VALKEY_PASSWORD,
    VALKEY_USERNAME,
    create_state,
)
from dpcharmlibs.interfaces import ResourceRequirerEventHandler, ValkeyResponseModel
from ops import testing
from scenario import TCPPort

from charm import SecureTokenServiceCharm
from constants import CACHE_INTEGRATION_NAME, STS_GRPC_PORT, STS_HTTP_PORT, WORKLOAD_CONTAINER


class TestStartEvent:
    def test_when_start_event_emitted(self, mocked_charm_holistic_handler: MagicMock) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=False)

        ctx.run(ctx.on.start(), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestPebbleReadyEvent:
    def test_when_container_not_connected(self) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=False)

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.unit_status == testing.WaitingStatus("Container is not connected yet")

    def test_when_missing_peer_integration(self) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True)

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.unit_status == testing.WaitingStatus("Missing peer integration")

    def test_when_missing_oauth_integration(self, peer_integration: testing.Relation) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True, relations=[peer_integration])

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.unit_status == testing.BlockedStatus("Missing oauth integration")

    def test_when_missing_database_integration(
        self,
        peer_integration: testing.Relation,
        oauth_integration: testing.Relation,
        oauth_secret: testing.Secret,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[peer_integration, oauth_integration],
            secrets=[oauth_secret],
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.unit_status == testing.BlockedStatus("Missing pg-database integration")

    def test_when_missing_receive_ca_cert_integration(
        self,
        peer_integration: testing.Relation,
        oauth_integration: testing.Relation,
        database_integration: testing.Relation,
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        mocked_migration_needed.return_value = False
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            relations=[peer_integration, oauth_integration, database_integration],
            secrets=[oauth_secret],
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.unit_status == testing.BlockedStatus(
            "Missing receive-ca-cert integration"
        )

    def test_when_missing_cache_integration(
        self,
        peer_integration: testing.Relation,
        oauth_integration: testing.Relation,
        database_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        mocked_migration_needed.return_value = False
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            relations=[
                peer_integration,
                oauth_integration,
                database_integration,
                receive_ca_cert_integration,
            ],
            secrets=[oauth_secret],
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.unit_status == testing.BlockedStatus(
            f"Missing {CACHE_INTEGRATION_NAME} integration"
        )

    def test_when_cache_relation_present_and_waiting(
        self,
        peer_integration: testing.Relation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        mocked_migration_needed.return_value = False
        cache_unready_integration = testing.Relation(
            endpoint=CACHE_INTEGRATION_NAME,
            interface="valkey_client",
            remote_app_name="valkey",
        )
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_unready_integration,
            ],
            secrets=[oauth_secret],
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.unit_status == testing.WaitingStatus("Waiting for cache creation")

    def test_when_cache_relation_has_fatal_status(
        self,
        peer_integration: testing.Relation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        mocked_migration_needed.return_value = False
        cache_fatal_integration = testing.Relation(
            endpoint=CACHE_INTEGRATION_NAME,
            interface="valkey_client",
            remote_app_name="valkey",
            remote_app_data={
                "status": json.dumps([
                    {"code": 5001, "message": "Cluster quota exceeded", "resolution": "Fix"}
                ])
            },
        )
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_fatal_integration,
            ],
            secrets=[oauth_secret],
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.unit_status == testing.BlockedStatus(
            "Cache error: Cluster quota exceeded"
        )

    def test_when_cache_relation_has_transitory_status(
        self,
        peer_integration: testing.Relation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        mocked_migration_needed.return_value = False
        cache_transitory_integration = testing.Relation(
            endpoint=CACHE_INTEGRATION_NAME,
            interface="valkey_client",
            remote_app_name="valkey",
            remote_app_data={
                "status": json.dumps([
                    {"code": 4001, "message": "Rebalancing shards", "resolution": "Wait"}
                ])
            },
        )
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_transitory_integration,
            ],
            secrets=[oauth_secret],
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.unit_status == testing.WaitingStatus("Cache: Rebalancing shards")

    def test_auto_migration_completed_successfully(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        oauth_secret: testing.Secret,
        cache_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
        mocked_cli_migrate: MagicMock,
    ) -> None:
        mocked_migration_needed.return_value = True
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
            ],
            secrets=[oauth_secret, cache_secret],
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert isinstance(state_out.unit_status, testing.ActiveStatus)

    def test_when_ready_and_integrations_present_migration_not_needed(
        self,
        peer_integration: testing.Relation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        oauth_secret: testing.Secret,
        cache_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
            ],
            secrets=[oauth_secret, cache_secret],
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert isinstance(state_out.unit_status, testing.ActiveStatus)

        out_container = state_out.get_container(WORKLOAD_CONTAINER)
        assert len(out_container.layers) > 0

    def test_workload_service_set_when_event_emitted(
        self,
        mocked_workload_service_version: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.opened_ports == {
            TCPPort(port=STS_HTTP_PORT, protocol="tcp"),
            TCPPort(port=STS_GRPC_PORT, protocol="tcp"),
        }
        mocked_charm_holistic_handler.assert_called_once()
        assert state_out.workload_version == "0.2.1", "workload service version should be set"

    def test_on_pebble_ready_correct_plan_with_cache(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        oauth_secret: testing.Secret,
        cache_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
            ],
            secrets=[oauth_secret, cache_secret],
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)
        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container_out.layers[WORKLOAD_CONTAINER]

        expected_plan = {
            "summary": "pebble layer",
            "description": "pebble layer for secure token service",
            "services": {
                "secure-token-service": {
                    "override": "replace",
                    "summary": "entrypoint of the secure token service image",
                    "command": "/usr/bin/app serve",
                    "startup": "disabled",
                    "environment": {
                        "CACHE_ADDR": VALKEY_ADDRESS,
                        "CACHE_PASSWORD": VALKEY_PASSWORD,
                        "CACHE_USERNAME": VALKEY_USERNAME,
                        "COOKIE_HASH_KEY": COOKIE_SECRET,
                        "DATABASE_URL": "postgres://sts_user:sts_password@pg.internal:5432/testing_secure-token-service",
                        "DEFAULT_AUTH_PROVIDER": "oidc",
                        "HTTPS_PROXY": "",
                        "HTTP_PROXY": "",
                        "LOG_FORMAT": "json",
                        "LOG_LEVEL": "info",
                        "NO_PROXY": "",
                        "OIDC_CLIENT_ID": OAUTH_CLIENT_ID,
                        "OIDC_CLIENT_SECRET": OAUTH_CLIENT_SECRET,
                        "OIDC_PROVIDER_URL": OAUTH_PROVIDER_INFO["issuer_url"],
                        "OIDC_REDIRECT_URL": "http://secure-token-service.testing.svc.cluster.local:8080/auth/callback",
                        "UBUNTU_ONE_OPENID_URL": "https://login.ubuntu.com/+openid",
                    },
                },
            },
            "checks": {
                "grpc-check": {
                    "override": "replace",
                    "period": "1m",
                    "level": "alive",
                    "tcp": {"port": STS_GRPC_PORT},
                },
                "http-check": {
                    "override": "replace",
                    "period": "1m",
                    "http": {"url": f"http://127.0.0.1:{STS_HTTP_PORT}/.well-known/jwks.json"},
                },
            },
        }

        assert expected_plan == layer.to_dict()


class TestConfigChangedEvent:
    def test_when_config_changed_event_emitted(
        self, mocked_charm_holistic_handler: MagicMock
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=False)

        ctx.run(ctx.on.config_changed(), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestAuthProviderConfig:
    @staticmethod
    def ingress_with_host(host: str = "sts.example.com") -> testing.Relation:
        return testing.Relation(
            endpoint="ingress",
            interface="istio_ingress_route",
            remote_app_name="istio-ingress-k8s",
            remote_app_data={"external_host": host, "tls_enabled": "True"},
        )

    def test_invalid_provider_is_blocked(self) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={"default_auth_provider": "saml"},
        )

        state_out = ctx.run(ctx.on.config_changed(), state_in)

        assert state_out.unit_status == testing.BlockedStatus(
            "Invalid default_auth_provider 'saml': must be one of oidc, openid"
        )

    def test_openid_without_realm_or_ingress_is_blocked(self) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={"default_auth_provider": "openid"},
        )

        state_out = ctx.run(ctx.on.config_changed(), state_in)

        assert state_out.unit_status == testing.BlockedStatus(
            "OpenID provider requires the 'ubuntu_one_realm' config "
            "or an ingress integration to derive the OpenID realm"
        )

    def test_openid_waits_for_ingress_external_url(
        self,
        ingress_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={"default_auth_provider": "openid"},
            relations=[ingress_integration],
        )

        state_out = ctx.run(ctx.on.config_changed(), state_in)

        assert state_out.unit_status == testing.WaitingStatus(
            "Waiting for ingress to provide an external URL"
        )

    def test_openid_realm_derived_from_ingress(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        oauth_secret: testing.Secret,
        cache_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={"default_auth_provider": "openid"},
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
                self.ingress_with_host(),
            ],
            secrets=[oauth_secret, cache_secret],
        )

        state_out = ctx.run(ctx.on.config_changed(), state_in)

        assert isinstance(state_out.unit_status, testing.ActiveStatus)
        layer = state_out.get_container(WORKLOAD_CONTAINER).layers[WORKLOAD_CONTAINER]
        env = layer.services[WORKLOAD_CONTAINER].environment
        assert env["DEFAULT_AUTH_PROVIDER"] == "openid"
        assert env["UBUNTU_ONE_REALM"] == "https://sts.example.com"

    def test_openid_with_explicit_realm_needs_no_ingress(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        oauth_secret: testing.Secret,
        cache_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={
                "default_auth_provider": "openid",
                "ubuntu_one_realm": "https://sts.example.com",
            },
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
            ],
            secrets=[oauth_secret, cache_secret],
        )

        state_out = ctx.run(ctx.on.config_changed(), state_in)

        assert isinstance(state_out.unit_status, testing.ActiveStatus)
        layer = state_out.get_container(WORKLOAD_CONTAINER).layers[WORKLOAD_CONTAINER]
        env = layer.services[WORKLOAD_CONTAINER].environment
        assert env["UBUNTU_ONE_REALM"] == "https://sts.example.com"

    def test_oidc_never_derives_realm(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        oauth_secret: testing.Secret,
        cache_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
                self.ingress_with_host(),
            ],
            secrets=[oauth_secret, cache_secret],
        )

        state_out = ctx.run(ctx.on.config_changed(), state_in)

        assert isinstance(state_out.unit_status, testing.ActiveStatus)
        layer = state_out.get_container(WORKLOAD_CONTAINER).layers[WORKLOAD_CONTAINER]
        env = layer.services[WORKLOAD_CONTAINER].environment
        assert env["DEFAULT_AUTH_PROVIDER"] == "oidc"
        assert "UBUNTU_ONE_REALM" not in env


class TestDatabaseIntegrationEvents:
    def test_when_container_not_connected(
        self,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=False,
            relations=[database_integration, peer_integration],
            leader=True,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.WaitingStatus("Container is not connected yet")

    def test_when_no_peer_integration(
        self,
        database_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[database_integration],
            leader=True,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.WaitingStatus("Missing peer integration")

    def test_waiting_for_migration_when_no_oauth_integration(
        self,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[database_integration, peer_integration],
            leader=True,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.BlockedStatus("Missing oauth integration")

    def test_waiting_for_migration_when_not_leader(
        self,
        peer_integration: testing.Relation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        oauth_secret: testing.Secret,
        cache_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        mocked_migration_needed.return_value = True
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
            ],
            secrets=[oauth_secret, cache_secret],
            leader=False,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.WaitingStatus(
            "Waiting for leader unit to run the migration"
        )

    @patch("charm.CommandLine.migrate")
    def test_when_migration_not_needed(
        self,
        mocked_cli_migrate: MagicMock,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
        oauth_integration: testing.Relation,
        oauth_secret: testing.Secret,
        mocked_charm_holistic_handler: MagicMock,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            relations=[database_integration, peer_integration, oauth_integration],
            secrets=[oauth_secret],
        )

        ctx.run(ctx.on.relation_changed(database_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()
        mocked_cli_migrate.assert_not_called()

    def test_when_relation_broken_event_emitted(
        self,
        database_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True, relations=[database_integration])

        ctx.run(ctx.on.relation_broken(database_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestOAuthIntegrationEvents:
    def test_info_changed_emitted(
        self,
        oauth_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True, relations=[oauth_integration])

        ctx.run(ctx.on.relation_changed(oauth_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()

    def test_info_removed_emitted(
        self,
        oauth_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True, relations=[oauth_integration])

        ctx.run(ctx.on.relation_broken(oauth_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()

    def test_config_is_updated_with_oauth_integration_data(
        self,
        peer_integration: testing.PeerRelation,
        oauth_integration: testing.Relation,
        database_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        oauth_secret: testing.Secret,
        cache_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            relations=[
                peer_integration,
                oauth_integration,
                database_integration,
                receive_ca_cert_integration,
                cache_integration,
            ],
            secrets=[oauth_secret, cache_secret],
        )

        state_out = ctx.run(ctx.on.relation_changed(oauth_integration), state_in)
        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container_out.layers[WORKLOAD_CONTAINER]
        env = layer.services[WORKLOAD_CONTAINER].environment

        assert env["OIDC_CLIENT_ID"] == OAUTH_CLIENT_ID
        assert env["OIDC_CLIENT_SECRET"] == OAUTH_CLIENT_SECRET
        assert env["OIDC_PROVIDER_URL"] == OAUTH_PROVIDER_INFO["issuer_url"]


class TestTrustedCertificatesIntegrationEvents:
    def test_certificates_available(
        self,
        receive_ca_cert_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True, relations=[receive_ca_cert_integration])

        ctx.run(ctx.on.relation_changed(receive_ca_cert_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()

    def test_certificates_removed(
        self,
        receive_ca_cert_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True, relations=[receive_ca_cert_integration])

        ctx.run(ctx.on.relation_broken(receive_ca_cert_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestIstioIngressIntegration:
    def test_ingress_ready_event(
        self,
        ingress_integration: testing.Relation,
        mocked_submit_routes: MagicMock,
        mocked_update_client_config: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)

        state_in = create_state(
            can_connect=True,
            relations=[ingress_integration],
            leader=True,
        )

        ctx.run(ctx.on.relation_changed(ingress_integration), state_in)

        mocked_submit_routes.assert_called_once()
        mocked_charm_holistic_handler.assert_called_once()
        mocked_update_client_config.assert_called_once()

    @staticmethod
    def ingress_with_host(host: str = "sts.example.com") -> testing.Relation:
        return testing.Relation(
            endpoint="ingress",
            interface="istio_ingress_route",
            remote_app_name="istio-ingress-k8s",
            remote_app_data={"external_host": host, "tls_enabled": "True"},
        )

    def test_follower_reconciles_when_ingress_publishes_external_host(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        oauth_secret: testing.Secret,
        cache_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
        mocked_submit_routes: MagicMock,
        mocked_update_client_config: MagicMock,
    ) -> None:
        ingress_integration = self.ingress_with_host()
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={"default_auth_provider": "openid"},
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
                ingress_integration,
            ],
            secrets=[oauth_secret, cache_secret],
            leader=False,
        )

        state_out = ctx.run(ctx.on.relation_changed(ingress_integration), state_in)

        assert isinstance(state_out.unit_status, testing.ActiveStatus)
        layer = state_out.get_container(WORKLOAD_CONTAINER).layers[WORKLOAD_CONTAINER]
        env = layer.services[WORKLOAD_CONTAINER].environment
        assert env["UBUNTU_ONE_REALM"] == "https://sts.example.com"
        mocked_submit_routes.assert_not_called()
        mocked_update_client_config.assert_not_called()

    def test_follower_reconciles_when_ingress_relation_removed(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        oauth_secret: testing.Secret,
        cache_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ingress_integration = self.ingress_with_host()
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={"default_auth_provider": "openid"},
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
                ingress_integration,
            ],
            secrets=[oauth_secret, cache_secret],
            leader=False,
        )

        state_out = ctx.run(ctx.on.relation_broken(ingress_integration), state_in)

        assert state_out.unit_status == testing.BlockedStatus(
            "OpenID provider requires the 'ubuntu_one_realm' config "
            "or an ingress integration to derive the OpenID realm"
        )


class TestCacheIntegrationEvents:
    def test_cache_resource_created_event_triggers_holistic_handler(
        self,
        cache_integration: testing.Relation,
        cache_secret: testing.Secret,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[cache_integration],
            secrets=[cache_secret],
        )

        ctx.run(
            ctx.on.custom(
                ResourceRequirerEventHandler.on.resource_created,
                cache_integration,
                None,
                None,
                ValkeyResponseModel(),
            ),
            state_in,
        )

        mocked_charm_holistic_handler.assert_called_once()

    def test_cache_relation_broken_triggers_holistic_handler(
        self,
        cache_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True, relations=[cache_integration])

        ctx.run(ctx.on.relation_broken(cache_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()

    def test_cache_relation_status_events_observed(self) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True)
        with ctx(ctx.on.start(), state_in) as mgr:
            charm = mgr.charm
            observed_events = [obs[3] for obs in charm.framework._observers]
            assert "status_raised" in observed_events
            assert "status_resolved" in observed_events

    def test_cache_relation_event_triggers_holistic_handler(
        self,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True)
        with ctx(ctx.on.start(), state_in) as mgr:
            charm = mgr.charm
            mock_event = MagicMock()
            charm._on_cache_relation_event(mock_event)
            mocked_charm_holistic_handler.assert_called_with(mock_event)


class TestStsInfoIntegration:
    def test_sts_info_ready_populates_relation_databag(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        oauth_secret: testing.Secret,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        cache_secret: testing.Secret,
        sts_info_integration: testing.Relation,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            leader=True,
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
                sts_info_integration,
            ],
            secrets=[oauth_secret, cache_secret],
        )

        state_out = ctx.run(ctx.on.relation_created(sts_info_integration), state_in)

        rel_out = state_out.get_relation(sts_info_integration.id)
        assert rel_out.local_app_data["http_address"] == (
            f"http://{APP_NAME}.{MODEL_NAME}.svc.cluster.local:{STS_HTTP_PORT}"
        )
        assert rel_out.local_app_data["grpc_address"] == (
            f"{APP_NAME}.{MODEL_NAME}.svc.cluster.local:{STS_GRPC_PORT}"
        )
        assert rel_out.local_app_data["jwks_url"] == (
            f"http://{APP_NAME}.{MODEL_NAME}.svc.cluster.local:{STS_HTTP_PORT}/.well-known/jwks.json"
        )
        assert rel_out.local_app_data["tls_enabled"] == "false"

    def test_non_leader_does_not_write_to_sts_info_databag(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        oauth_secret: testing.Secret,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        cache_secret: testing.Secret,
        sts_info_integration: testing.Relation,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            leader=False,
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
                sts_info_integration,
            ],
            secrets=[oauth_secret, cache_secret],
        )

        state_out = ctx.run(ctx.on.relation_created(sts_info_integration), state_in)

        rel_out = state_out.get_relation(sts_info_integration.id)
        assert rel_out.local_app_data == {}

    def test_ingress_ready_refreshes_sts_info_databag(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        oauth_secret: testing.Secret,
        receive_ca_cert_integration: testing.Relation,
        cache_integration: testing.Relation,
        cache_secret: testing.Secret,
        ingress_integration: testing.Relation,
        sts_info_integration: testing.Relation,
        mocked_submit_routes: MagicMock,
        mocked_update_client_config: MagicMock,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            leader=True,
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
                cache_integration,
                ingress_integration,
                sts_info_integration,
            ],
            secrets=[oauth_secret, cache_secret],
        )

        state_out = ctx.run(ctx.on.relation_changed(ingress_integration), state_in)

        rel_out = state_out.get_relation(sts_info_integration.id)
        assert "http_address" in rel_out.local_app_data
        assert "grpc_address" in rel_out.local_app_data
        assert "jwks_url" in rel_out.local_app_data
        assert "tls_enabled" in rel_out.local_app_data
