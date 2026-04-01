#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

from conftest import (
    COOKIE_SECRET,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_PROVIDER_INFO,
    VALKEY_ADDRESS,
    VALKEY_PASSWORD,
    VALKEY_USERNAME,
    create_state,
)
from ops import testing
from scenario import TCPPort

from charm import SecureTokenServiceCharm
from constants import STS_GRPC_PORT, STS_HTTP_PORT, WORKLOAD_CONTAINER


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

        assert state_out.unit_status == testing.BlockedStatus("Missing receive-ca-cert integration")

    def test_when_missing_cache_config(
        self,
        peer_integration: testing.Relation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        mocked_migration_needed.return_value = False
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            config={"cache_address": VALKEY_ADDRESS, "cache_password": ""},
            relations=[peer_integration, database_integration, oauth_integration, receive_ca_cert_integration],
            secrets=[oauth_secret],
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.unit_status == testing.BlockedStatus("Missing valkey/redis configuration")

    def test_auto_migration_completed_successfully(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
        mocked_cli_migrate: MagicMock,
    ) -> None:
        mocked_migration_needed.return_value = True
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={
                "cache_address": VALKEY_ADDRESS,
                "cache_password": VALKEY_PASSWORD,
                "cache_username": VALKEY_USERNAME,
            },
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
            ],
            secrets=[oauth_secret],
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
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={
                "cache_address": VALKEY_ADDRESS,
                "cache_password": VALKEY_PASSWORD,
                "cache_username": VALKEY_USERNAME,
            },
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
            ],
            secrets=[oauth_secret],
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

    def test_on_pebble_ready_correct_plan(
        self,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
        oauth_integration: testing.Relation,
        receive_ca_cert_integration: testing.Relation,
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={
                "cache_address": VALKEY_ADDRESS,
                "cache_password": VALKEY_PASSWORD,
                "cache_username": VALKEY_USERNAME,
            },
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
            ],
            secrets=[oauth_secret],
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
                        "CACHE_DB": "0",
                        "CACHE_PASSWORD": VALKEY_PASSWORD,
                        "CACHE_USERNAME": VALKEY_USERNAME,
                        "COOKIE_HASH_KEY": COOKIE_SECRET,
                        "DATABASE_URL": "postgres://sts_user:sts_password@pg.internal:5432/testing_secure-token-service",
                        "HTTPS_PROXY": "",
                        "HTTP_PROXY": "",
                        "LOG_FORMAT": "json",
                        "LOG_LEVEL": "info",
                        "NO_PROXY": "",
                        "OIDC_CLIENT_ID": OAUTH_CLIENT_ID,
                        "OIDC_CLIENT_SECRET": OAUTH_CLIENT_SECRET,
                        "OIDC_PROVIDER_URL": OAUTH_PROVIDER_INFO["issuer_url"],
                        "OIDC_REDIRECT_URL": "http://secure-token-service.testing.svc.cluster.local:8080/auth/callback",
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
    def test_when_config_changed_event_emitted(self, mocked_charm_holistic_handler: MagicMock) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=False)

        ctx.run(ctx.on.config_changed(), state_in)

        mocked_charm_holistic_handler.assert_called_once()


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
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        mocked_migration_needed.return_value = True
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            config={
                "cache_address": VALKEY_ADDRESS,
                "cache_password": VALKEY_PASSWORD,
                "cache_username": VALKEY_USERNAME,
            },
            relations=[
                peer_integration,
                database_integration,
                oauth_integration,
                receive_ca_cert_integration,
            ],
            secrets=[oauth_secret],
            leader=False,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.WaitingStatus("Waiting for leader unit to run the migration")

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
        oauth_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            config={
                "cache_address": VALKEY_ADDRESS,
                "cache_password": VALKEY_PASSWORD,
                "cache_username": VALKEY_USERNAME,
            },
            relations=[peer_integration, oauth_integration, database_integration, receive_ca_cert_integration],
            secrets=[oauth_secret],
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
