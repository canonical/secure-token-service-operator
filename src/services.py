# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from collections import ChainMap

from ops import Container, ModelError, Unit
from ops.pebble import Layer, LayerDict

from cli import CommandLine
from constants import (
    STS_GRPC_PORT,
    STS_HTTP_PORT,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleServiceError

logger = logging.getLogger(__name__)

PEBBLE_LAYER_DICT = {
    "summary": "pebble layer",
    "description": "pebble layer for secure token service",
    "services": {
        WORKLOAD_SERVICE: {
            "override": "replace",
            "summary": "entrypoint of the secure token service image",
            "command": "/usr/bin/app serve",
            "startup": "disabled",
        }
    },
    "checks": {
        "http-check": {
            "override": "replace",
            "period": "1m",
            "http": {"url": f"http://127.0.0.1:{STS_HTTP_PORT}/.well-known/jwks.json"},
        },
        "grpc-check": {
            "override": "replace",
            "period": "1m",
            "level": "alive",
            "tcp": {
                "port": STS_GRPC_PORT,
            },
        },
    },
}


class WorkloadService:
    """Workload service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._version = ""

        self._unit: Unit = unit
        self._container: Container = unit.get_container(WORKLOAD_CONTAINER)
        self._cli = CommandLine(self._container)

    @property
    def version(self) -> str:
        return self._cli.get_service_version() or ""

    def update_workload_version(self) -> None:
        version = self.version
        if not version:
            return

        try:
            self._unit.set_workload_version(version)
        except Exception as e:
            logger.error("Failed to set workload version: %s", e)

    @property
    def is_running(self) -> bool:
        try:
            workload_service = self._container.get_service(WORKLOAD_SERVICE)
        except ModelError:
            return False

        return workload_service.is_running()

    def open_ports(self) -> None:
        self._unit.open_port(protocol="tcp", port=STS_HTTP_PORT)
        self._unit.open_port(protocol="tcp", port=STS_GRPC_PORT)


class PebbleService:
    """Pebble service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit
        self._container = unit.get_container(WORKLOAD_CONTAINER)
        self._layer_dict: LayerDict = PEBBLE_LAYER_DICT

    def _restart_service(self) -> None:
        if not self._container.get_service(WORKLOAD_SERVICE).is_running():
            self._container.start(WORKLOAD_SERVICE)
        else:
            self._container.replan()

    def plan(self, layer: Layer) -> None:
        self._container.add_layer(WORKLOAD_SERVICE, layer, combine=True)

        try:
            self._restart_service()
        except Exception as e:
            raise PebbleServiceError(f"Pebble failed to restart the workload service. Error: {e}")

    def render_pebble_layer(self, *env_var_sources: EnvVarConvertible) -> Layer:
        updated_env_vars = ChainMap(*(source.to_env_vars() for source in env_var_sources))  # type: ignore
        env_vars = {
            **DEFAULT_CONTAINER_ENV,
            **updated_env_vars,
        }
        self._layer_dict["services"][WORKLOAD_SERVICE]["environment"] = env_vars

        return Layer(self._layer_dict)
