# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import secrets
import subprocess
from dataclasses import dataclass
from typing import Any, KeysView, Type, TypeAlias, Union

from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificateTransferRequires,
)
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.hydra.v0.oauth import OAuthRequirer
from charms.istio_ingress_k8s.v0.istio_ingress_route import (
    BackendRef,
    HTTPPathMatch,
    HTTPPathMatchType,
    HTTPRoute,
    HTTPRouteMatch,
    IstioIngressRouteConfig,
    IstioIngressRouteRequirer,
    Listener,
    ProtocolType,
)
from dpcharmlibs.interfaces import ResourceRequirerEventHandler, ValkeyResponseModel
from dpcharmlibs.interfaces.errors import (
    DataInterfacesError,
    SecretError,
    SecretsUnavailableError,
)
from ops import CharmBase, Model, ModelError
from pydantic import ValidationError
from typing_extensions import Self

from constants import (
    CERTIFICATES_FILE,
    COOKIE_SECRET_KEY,
    INGRESS_HTTP_PORT,
    LOCAL_CA_BUNDLE_PATH,
    PEER_INTEGRATION_NAME,
    POSTGRESQL_DSN_TEMPLATE,
    RECEIVE_CA_CERT_INTEGRATION_NAME,
    STS_HTTP_PORT,
)
from env_vars import EnvVars

logger = logging.getLogger(__name__)

JsonSerializable: TypeAlias = Union[dict[str, Any], list[Any], int, str, float, bool, Type[None]]


class PeerData:
    def __init__(self, model: Model) -> None:
        self._model = model
        self._app = model.app

        if not self._model.get_relation(PEER_INTEGRATION_NAME) or not self._model.unit.is_leader():
            return

        if not self[COOKIE_SECRET_KEY]:
            self[COOKIE_SECRET_KEY] = secrets.token_hex(32)

    def __getitem__(self, key: str) -> JsonSerializable:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return {}

        value = peers.data[self._app].get(key)
        return json.loads(value) if value else {}

    def __setitem__(self, key: str, value: Any) -> None:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return

        peers.data[self._app][key] = json.dumps(value)

    def pop(self, key: str) -> JsonSerializable:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return {}

        data = peers.data[self._app].pop(key, None)
        return json.loads(data) if data else {}

    def keys(self) -> KeysView[str]:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return KeysView({})

        return peers.data[self._app].keys()

    def to_env_vars(self) -> EnvVars:
        if not (cookie_secret := self[COOKIE_SECRET_KEY]):
            logger.error("Cookie secret not found in the peer integration")
            return {}

        return {
            "COOKIE_HASH_KEY": cookie_secret,
        }


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """The data source from the database integration."""

    endpoint: str = ""
    database: str = ""
    username: str = ""
    password: str = ""
    migration_version: str = ""

    @property
    def dsn(self) -> str:
        return POSTGRESQL_DSN_TEMPLATE.substitute(
            username=self.username,
            password=self.password,
            endpoint=self.endpoint,
            database=self.database,
        )

    def to_env_vars(self) -> EnvVars:
        env = {
            "DATABASE_URL": self.dsn,
        }

        return env

    @classmethod
    def load(cls, requirer: DatabaseRequires) -> Self:
        if not (database_integrations := requirer.relations):
            return cls()

        integration_id = database_integrations[0].id
        integration_data: dict[str, str] = requirer.fetch_relation_data()[integration_id]

        return cls(
            endpoint=integration_data.get("endpoints", "").split(",")[0],
            database=requirer.database,
            username=integration_data.get("username", ""),
            password=integration_data.get("password", ""),
            migration_version=f"migration_version_{integration_id}",
        )


@dataclass(frozen=True, slots=True)
class CacheConfig:
    """The data source from the cache integration."""

    endpoint: str = ""
    username: str = ""
    password: str = ""

    def to_env_vars(self) -> EnvVars:
        if not self.endpoint:
            return {}

        return {
            "CACHE_ADDR": self.endpoint,
            "CACHE_USERNAME": self.username,
            "CACHE_PASSWORD": self.password,
        }

    @classmethod
    def load(cls, requirer: ResourceRequirerEventHandler) -> Self:
        if not (relations := requirer.relations):
            return cls()

        relation = relations[0]
        if not relation.app:
            return cls()

        try:
            model = requirer.interface.build_model(relation_id=relation.id, component=relation.app)
        except (
            DataInterfacesError,
            ValidationError,
            SecretError,
            SecretsUnavailableError,
            ModelError,
            ValueError,
        ) as err:
            logger.warning("Failed to load cache configuration: %s", err)
            return cls()

        if not model.requests:
            return cls()

        response: ValkeyResponseModel = model.requests[0]
        if not response.endpoints or not response.password:
            return cls()

        endpoint, *_ = response.endpoints.partition(",")
        return cls(
            endpoint=endpoint,
            username=response.username or "",
            password=response.password,
        )


@dataclass(frozen=True, slots=True)
class OAuthConfig:
    """The data source from the oauth integration."""

    provider_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    redirect_url: str = ""

    @classmethod
    def load(cls, requirer: OAuthRequirer, redirect_url: str | None) -> "OAuthConfig":
        provider_info = requirer.get_provider_info()
        if not provider_info or not provider_info.client_id:
            return cls(redirect_url=redirect_url or "")

        return cls(
            provider_url=provider_info.issuer_url or "",
            client_id=provider_info.client_id or "",
            client_secret=provider_info.client_secret or "",
            redirect_url=redirect_url or "",
        )

    def to_env_vars(self) -> dict:
        return {
            "OIDC_PROVIDER_URL": self.provider_url,
            "OIDC_CLIENT_ID": self.client_id,
            "OIDC_CLIENT_SECRET": self.client_secret,
            "OIDC_REDIRECT_URL": self.redirect_url,
        }


class TrustedCertificatesTransferIntegration:
    def __init__(self, charm: CharmBase):
        self._charm = charm
        self._container = charm._container
        self.cert_transfer_requires = CertificateTransferRequires(
            charm, relationship_name=RECEIVE_CA_CERT_INTEGRATION_NAME
        )

    def update_trusted_ca_certs(self) -> None:
        """Receive trusted certificates from the certificate_transfer integration.

        This function is needed because relation events are not emitted on upgrade,
        and because there is no persistent storage for certs.
        """
        if not self._charm.model.get_relation(
            relation_name=self.cert_transfer_requires.relationship_name
        ):
            logger.warning("Missing certificate_transfer integration")

        self._push_ca_certs()

    def _push_ca_certs(self) -> None:
        certs = self.cert_transfer_requires.get_all_certificates()
        ca_bundle = "\n".join(sorted(certs))

        with open(LOCAL_CA_BUNDLE_PATH, mode="wt") as f:
            f.write(ca_bundle)

        subprocess.run(["update-ca-certificates", "--fresh"], capture_output=True)
        self._container.push(CERTIFICATES_FILE, CERTIFICATES_FILE.read_text(), make_dirs=True)


class IstioIngressIntegration:
    """Encapsulates the Istio Gateway API configuration for HTTP."""

    def __init__(self, charm: CharmBase, relation_name: str) -> None:
        self.requirer = IstioIngressRouteRequirer(charm, relation_name=relation_name)
        self.app_name = charm.app.name
        self.model_name = charm.model.name

    @property
    def external_url(self) -> str | None:
        """Public URL if provided by the Istio gateway."""
        if not self.requirer.external_host:
            return None

        scheme = "https" if self.requirer.tls_enabled else "http"
        return f"{scheme}://{self.requirer.external_host}"

    def submit_routes(self) -> None:
        """Compiles and submits HTTP Routes to the Istio Ingress Gateway."""
        http_listener = Listener(port=INGRESS_HTTP_PORT, protocol=ProtocolType.HTTP)
        config = IstioIngressRouteConfig(
            model=self.model_name,
            listeners=[http_listener],
            http_routes=[
                HTTPRoute(
                    name="sts-http-route",
                    listener=http_listener,
                    matches=[
                        # Matches /auth*: /auth/login, /auth/callback, /auth/logout, /auth/sessions
                        HTTPRouteMatch(
                            path=HTTPPathMatch(type=HTTPPathMatchType.PathPrefix, value="/auth")
                        ),
                    ],
                    backends=[BackendRef(service=self.app_name, port=STS_HTTP_PORT)],
                )
            ],
        )
        self.requirer.submit_config(config)
