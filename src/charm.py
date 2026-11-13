#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Secure Token Service Operator."""

import logging
from typing import Any
from urllib.parse import urljoin

from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificatesAvailableEvent,
    CertificatesRemovedEvent,
)
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.hydra.v0.oauth import ClientConfig as OauthClientConfig
from charms.hydra.v0.oauth import OAuthInfoChangedEvent, OAuthRequirer
from charms.istio_beacon_k8s.v0.service_mesh import ServiceMeshConsumer
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.secure_token_service.v0.sts_info import StsInfoProvider, StsInfoRelationReadyEvent
from dpcharmlibs.interfaces import (
    RequirerCommonModel,
    ResourceRequirerEvent,
    ResourceRequirerEventHandler,
    ValkeyResponseModel,
)
from dpcharmlibs.interfaces.errors import (
    DataInterfacesError,
    SecretError,
    SecretsUnavailableError,
)
from ops import (
    ActionEvent,
    ActiveStatus,
    BlockedStatus,
    CharmBase,
    ConfigChangedEvent,
    HookEvent,
    MaintenanceStatus,
    ModelError,
    PebbleReadyEvent,
    RelationBrokenEvent,
    StartEvent,
    StatusBase,
    WaitingStatus,
    main,
)
from ops.pebble import Layer
from pydantic import ValidationError

from cli import CommandLine
from configs import CharmConfig
from constants import (
    CACHE_INTEGRATION_NAME,
    DATABASE_INTEGRATION_NAME,
    ISTIO_INGRESS_INTEGRATION_NAME,
    OAUTH_GRANT_TYPES,
    OAUTH_INTEGRATION_NAME,
    OAUTH_SCOPES,
    OPENID_PROVIDER,
    PEER_INTEGRATION_NAME,
    RECEIVE_CA_CERT_INTEGRATION_NAME,
    STS_GRPC_PORT,
    STS_HTTP_PORT,
    STS_INFO_INTEGRATION_NAME,
    VALID_AUTH_PROVIDERS,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from exceptions import MigrationError, PebbleServiceError
from integrations import (
    CacheConfig,
    DatabaseConfig,
    IstioIngressIntegration,
    OAuthConfig,
    PeerData,
    TrustedCertificatesTransferIntegration,
)
from services import PebbleService, WorkloadService
from utils import (
    cache_integration_exists,
    container_connectivity,
    database_integration_exists,
    oauth_integration_exists,
    peer_integration_exists,
    receive_certs_integration_exists,
)

logger = logging.getLogger(__name__)


class SecureTokenServiceCharm(CharmBase):
    """Orchestrates the lifecycle of the Secure Token Service."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        self._container = self.unit.get_container(WORKLOAD_CONTAINER)
        self._workload_service = WorkloadService(self.unit)
        self._pebble_service = PebbleService(self.unit)
        self._cli = CommandLine(self._container)

        self.peer_data = PeerData(self.model)
        self.charm_config = CharmConfig(self.config, lambda: self.istio_ingress.external_url)

        self.database = DatabaseRequires(
            self,
            relation_name=DATABASE_INTEGRATION_NAME,
            database_name=f"{self.model.name}_{self.app.name}",
        )

        self.valkey_interface = ResourceRequirerEventHandler(
            charm=self,
            relation_name=CACHE_INTEGRATION_NAME,
            requests=[RequirerCommonModel(resource="*")],
            response_model=ValkeyResponseModel,
        )

        self.istio_ingress = IstioIngressIntegration(
            self, relation_name=ISTIO_INGRESS_INTEGRATION_NAME
        )

        self.sts_info = StsInfoProvider(self, relation_name=STS_INFO_INTEGRATION_NAME)

        # TODO: Add metrics policy when integration is implemented
        self._service_mesh = ServiceMeshConsumer(self)

        self.oauth = OAuthRequirer(self, self._oauth_client_config)

        self.trusted_cert_transfer = TrustedCertificatesTransferIntegration(self)

        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.secure_token_service_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.run_migration_action, self._on_run_migration_action)

        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(self.database.on.endpoints_changed, self._on_database_changed)
        self.framework.observe(
            self.on[DATABASE_INTEGRATION_NAME].relation_broken, self._on_database_relation_broken
        )

        for event in (
            self.valkey_interface.on.resource_created,
            self.valkey_interface.on.endpoints_changed,
            self.valkey_interface.on.read_only_endpoints_changed,
            self.valkey_interface.on.authentication_updated,
            self.valkey_interface.on.status_raised,
            self.valkey_interface.on.status_resolved,
        ):
            self.framework.observe(event, self._on_cache_relation_event)

        self.framework.observe(
            self.on[CACHE_INTEGRATION_NAME].relation_broken,
            self._on_cache_relation_broken,
        )

        # The requirer's `ready` event is emitted on the leader unit only, so observe the
        # raw relation events to let follower units reconcile ingress changes as well.
        self.framework.observe(
            self.on[ISTIO_INGRESS_INTEGRATION_NAME].relation_changed, self._on_ingress_ready
        )
        self.framework.observe(
            self.on[ISTIO_INGRESS_INTEGRATION_NAME].relation_broken, self._on_ingress_ready
        )
        self.framework.observe(self.sts_info.on.sts_info_ready, self._on_sts_info_ready)

        self.framework.observe(self.oauth.on.oauth_info_changed, self._on_oauth_info_changed)
        self.framework.observe(self.oauth.on.oauth_info_removed, self._on_oauth_info_changed)

        self.framework.observe(
            self.trusted_cert_transfer.cert_transfer_requires.on.certificate_set_updated,
            self._on_trusted_certificates_available,
        )
        self.framework.observe(
            self.trusted_cert_transfer.cert_transfer_requires.on.certificates_removed,
            self._on_trusted_certificates_removed,
        )

        # Resources patching
        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            WORKLOAD_CONTAINER,
            resource_reqs_func=self._resource_reqs_from_config,
        )

    @property
    def _pebble_layer(self) -> Layer:
        database_config = DatabaseConfig.load(self.database)
        oauth_config = OAuthConfig.load(self.oauth, self._redirect_url)
        cache_config = CacheConfig.load(self.valkey_interface)
        return self._pebble_service.render_pebble_layer(
            self.charm_config,
            self.peer_data,
            database_config,
            oauth_config,
            cache_config,
        )

    @property
    def migration_needed(self) -> bool:
        """Check if database migrations are required."""
        if not container_connectivity(self) or not self.database.is_resource_created():
            return False

        dsn = DatabaseConfig.load(self.database).dsn
        pebble_env = self._pebble_layer.services[WORKLOAD_SERVICE].environment

        return self._cli.check_migrations(dsn, environment=pebble_env)

    @property
    def _sts_http_address(self) -> str:
        """STS HTTP base URL."""
        if external_url := self.istio_ingress.external_url:
            return external_url
        return f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{STS_HTTP_PORT}"

    @property
    def _sts_grpc_address(self) -> str:
        """STS gRPC address (k8s service address)."""
        return f"{self.app.name}.{self.model.name}.svc.cluster.local:{STS_GRPC_PORT}"

    @property
    def _redirect_url(self) -> str:
        """OIDC redirect URI based on the external URL."""
        return urljoin(self._sts_http_address, "/auth/callback")

    @property
    def _oauth_client_config(self) -> OauthClientConfig:
        return OauthClientConfig(
            redirect_uri=self._redirect_url,
            scope=OAUTH_SCOPES,
            grant_types=OAUTH_GRANT_TYPES,
        )

    def _on_start(self, event: StartEvent) -> None:
        self._holistic_handler(event)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_pebble_ready(self, event: PebbleReadyEvent) -> None:
        if not container_connectivity(self):
            self.unit.status = WaitingStatus("Container is not connected yet")
            event.defer()
            return

        self._workload_service.open_ports()
        self._workload_service.update_workload_version()

        self._holistic_handler(event)

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        requests = {"cpu": "100m", "memory": "200Mi"}
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)

    def _send_sts_info_rel_data(self) -> None:
        self.sts_info.update_relations_app_data(
            http_address=self._sts_http_address,
            grpc_address=self._sts_grpc_address,
            tls_enabled=self.istio_ingress.requirer.tls_enabled,
        )

    def _on_ingress_ready(self, event) -> None:
        if self.model.relations.get(ISTIO_INGRESS_INTEGRATION_NAME) and self.unit.is_leader():
            self.istio_ingress.submit_routes()

        self._holistic_handler(event)
        if self.unit.is_leader():
            logger.info("This app's ingress URL: %s", self.istio_ingress.external_url)
            self.oauth.update_client_config(client_config=self._oauth_client_config)

    def _on_sts_info_ready(self, event: StsInfoRelationReadyEvent) -> None:
        self._holistic_handler(event)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        self._holistic_handler(event)

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_database_relation_broken(self, event: RelationBrokenEvent) -> None:
        self._holistic_handler(event)

    def _on_cache_relation_event(self, event: ResourceRequirerEvent) -> None:
        self._holistic_handler(event)

    def _on_cache_relation_broken(self, event: RelationBrokenEvent) -> None:
        self._holistic_handler(event)

    def _on_oauth_info_changed(self, event: OAuthInfoChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_trusted_certificates_available(self, event: CertificatesAvailableEvent) -> None:
        self._holistic_handler(event)

    def _on_trusted_certificates_removed(self, event: CertificatesRemovedEvent) -> None:
        self._holistic_handler(event)

    def _on_run_migration_action(self, event: ActionEvent) -> None:
        if not self.unit.is_leader():
            event.fail("Only the leader unit can run the database migration")
            return

        if not container_connectivity(self):
            event.fail("Container is not connected yet")
            return

        if not peer_integration_exists(self):
            event.fail("Peer integration is not ready")
            return

        event.log("Started migrating the database")

        timeout = float(event.params.get("timeout", 120))
        try:
            self._cli.migrate(
                dsn=DatabaseConfig.load(self.database).dsn,
                timeout=timeout,
            )
        except MigrationError as err:
            event.fail(f"Database migration failed: {err}")
            return
        else:
            event.log("Successfully migrated the database")

    def _check_prerequisites(self) -> tuple[StatusBase | None, bool]:  # noqa: C901
        """Evaluate if all charm prerequisites are met before configuring the workload.

        This method checks for the presence of required integrations,
        valid configurations, and database readiness. It acts as a guard circuit
        to prevent the workload from starting in a broken state.

        Returns:
            - StatusBase object detailing the missing requirement,
              or None if all prerequisites are met.
            - bool indicating whether the current hook event should be deferred.
        """
        if not container_connectivity(self):
            return WaitingStatus("Container is not connected yet"), True

        if self.charm_config.provider not in VALID_AUTH_PROVIDERS:
            return (
                BlockedStatus(
                    f"Invalid default_auth_provider '{self.charm_config.provider}': "
                    f"must be one of {', '.join(VALID_AUTH_PROVIDERS)}"
                ),
                False,
            )

        if (
            self.charm_config.provider == OPENID_PROVIDER
            and not self.model.config["ubuntu_one_realm"]
        ):
            if not self.model.relations.get(ISTIO_INGRESS_INTEGRATION_NAME):
                return (
                    BlockedStatus(
                        "OpenID provider requires the 'ubuntu_one_realm' config "
                        "or an ingress integration to derive the OpenID realm"
                    ),
                    False,
                )
            if not self.istio_ingress.external_url:
                return WaitingStatus("Waiting for ingress to provide an external URL"), False

        patch_status = self.resources_patch.get_status()
        if not isinstance(patch_status, ActiveStatus):
            return patch_status, False

        if not peer_integration_exists(self):
            return WaitingStatus(f"Missing {PEER_INTEGRATION_NAME} integration"), True

        if not oauth_integration_exists(self):
            return BlockedStatus(f"Missing {OAUTH_INTEGRATION_NAME} integration"), False

        oauth_config = OAuthConfig.load(self.oauth, self._redirect_url)
        if not oauth_config.provider_url or not oauth_config.client_id:
            return WaitingStatus(f"Waiting for {OAUTH_INTEGRATION_NAME} config"), False

        if not database_integration_exists(self):
            return BlockedStatus(f"Missing {DATABASE_INTEGRATION_NAME} integration"), False

        if not self.database.is_resource_created():
            return WaitingStatus("Waiting for database creation"), False

        if not receive_certs_integration_exists(self):
            return BlockedStatus(f"Missing {RECEIVE_CA_CERT_INTEGRATION_NAME} integration"), False

        if not cache_integration_exists(self):
            return BlockedStatus(f"Missing {CACHE_INTEGRATION_NAME} integration"), False

        for rel in self.valkey_interface.relations:
            try:
                statuses = self.valkey_interface.get_statuses(rel.id)
            except (
                DataInterfacesError,
                ValidationError,
                SecretError,
                SecretsUnavailableError,
                ModelError,
                ValueError,
            ) as err:
                logger.debug("Failed to get cache status for relation %s: %s", rel.id, err)
                continue

            for rel_status in statuses.values():
                if rel_status.is_fatal:
                    return BlockedStatus(f"Cache error: {rel_status.message}"), False

            for rel_status in statuses.values():
                if rel_status.is_transitory:
                    return WaitingStatus(f"Cache: {rel_status.message}"), False

        cache_config = CacheConfig.load(self.valkey_interface)
        if not cache_config.endpoint or not cache_config.password:
            return WaitingStatus("Waiting for cache creation"), False

        # Everything is ready
        return None, False

    def _holistic_handler(self, event: HookEvent) -> None:
        """Update the application status and configuration and restart the container.

        Args:
            event: The event triggered when the application needs to be updated.
        """
        status, should_defer = self._check_prerequisites()
        if status:
            self.unit.status = status
            if should_defer:
                event.defer()
            return

        if self.migration_needed:
            if not self.unit.is_leader():
                self.unit.status = WaitingStatus("Waiting for leader unit to run the migration")
                event.defer()
                return

            self.unit.status = MaintenanceStatus("Running database migrations")
            pebble_env = self._pebble_layer.services[WORKLOAD_SERVICE].environment
            try:
                self._cli.migrate(DatabaseConfig.load(self.database).dsn, environment=pebble_env)
                logger.info("Database migration completed successfully")
            except MigrationError:
                self.unit.status = BlockedStatus("Database migration failed")
                logger.error("Auto migration job failed. Please run the migration manually")
                return

        self.unit.status = MaintenanceStatus("Configuring the container")
        self.trusted_cert_transfer.update_trusted_ca_certs()

        try:
            self._pebble_service.plan(self._pebble_layer)
        except PebbleServiceError:
            logger.error("Failed to start the service, please check the container logs")
            self.unit.status = BlockedStatus(
                f"Failed to restart the service, please check the {WORKLOAD_CONTAINER} logs"
            )
            return

        self._send_sts_info_rel_data()

        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(SecureTokenServiceCharm)
