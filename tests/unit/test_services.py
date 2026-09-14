# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Optional
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from ops.model import ModelError

from constants import (
    STS_GRPC_PORT,
    STS_HTTP_PORT,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleServiceError
from services import PebbleService, WorkloadService


class TestWorkloadService:
    @pytest.fixture
    def workload_service(
        self, mocked_container: MagicMock, mocked_unit: MagicMock
    ) -> WorkloadService:
        return WorkloadService(mocked_unit)

    @pytest.mark.parametrize("version, expected", [("v0.2.1", "v0.2.1"), (None, "")])
    def test_get_version(
        self, workload_service: WorkloadService, version: Optional[str], expected: str
    ) -> None:
        with patch("cli.CommandLine.get_service_version", return_value=version):
            assert workload_service.version == expected

    def test_update_workload_version(
        self, mocked_unit: MagicMock, workload_service: WorkloadService
    ) -> None:
        with patch(
            "services.WorkloadService.version", new_callable=PropertyMock, return_value="v0.2.1"
        ):
            workload_service.update_workload_version()
        mocked_unit.set_workload_version.assert_called_once_with("v0.2.1")

    def test_update_workload_version_empty(
        self, mocked_unit: MagicMock, workload_service: WorkloadService
    ) -> None:
        with patch("services.WorkloadService.version", new_callable=PropertyMock, return_value=""):
            workload_service.update_workload_version()
        mocked_unit.set_workload_version.assert_not_called()

    def test_update_workload_version_with_error(
        self,
        mocked_unit: MagicMock,
        workload_service: WorkloadService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        error_msg = "Error from unit"
        mocked_unit.set_workload_version.side_effect = Exception(error_msg)

        with caplog.at_level("ERROR"):
            with patch(
                "services.WorkloadService.version",
                new_callable=PropertyMock,
                return_value="v0.2.1",
            ):
                workload_service.update_workload_version()

        mocked_unit.set_workload_version.assert_called_once_with("v0.2.1")
        assert f"Failed to set workload version: {error_msg}" in caplog.text

    def test_is_running(
        self, mocked_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        mocked_service_info = MagicMock()
        mocked_service_info.is_running.return_value = True

        with patch.object(
            mocked_container, "get_service", return_value=mocked_service_info
        ) as get_service:
            is_running = workload_service.is_running

        assert is_running is True
        get_service.assert_called_once_with(WORKLOAD_SERVICE)

    def test_is_running_with_error(
        self, mocked_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        with patch.object(mocked_container, "get_service", side_effect=ModelError):
            is_running = workload_service.is_running

        assert is_running is False

    def test_open_ports(self, mocked_unit: MagicMock, workload_service: WorkloadService) -> None:
        workload_service.open_ports()

        assert mocked_unit.open_port.call_count == 2
        mocked_unit.open_port.assert_any_call(protocol="tcp", port=STS_HTTP_PORT)
        mocked_unit.open_port.assert_any_call(protocol="tcp", port=STS_GRPC_PORT)


class TestPebbleService:
    @pytest.fixture
    def pebble_service(self, mocked_unit: MagicMock) -> PebbleService:
        return PebbleService(mocked_unit)

    @patch("ops.pebble.Layer")
    def test_plan_with_running_service_triggers_replan(
        self,
        mocked_layer: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        mocked_service_info = MagicMock()
        mocked_service_info.is_running.return_value = True
        mocked_container.get_service.return_value = mocked_service_info

        pebble_service.plan(mocked_layer)

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_SERVICE, mocked_layer, combine=True
        )
        mocked_container.replan.assert_called_once()
        mocked_container.start.assert_not_called()

    @patch("ops.pebble.Layer")
    def test_plan_with_stopped_service_triggers_start(
        self,
        mocked_layer: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        mocked_service_info = MagicMock()
        mocked_service_info.is_running.return_value = False
        mocked_container.get_service.return_value = mocked_service_info

        pebble_service.plan(mocked_layer)

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_SERVICE, mocked_layer, combine=True
        )
        mocked_container.start.assert_called_once_with(WORKLOAD_SERVICE)
        mocked_container.replan.assert_not_called()

    @patch("ops.pebble.Layer")
    def test_plan_failure(
        self,
        mocked_layer: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        with patch.object(
            mocked_container, "replan", side_effect=Exception
        ) as replan, pytest.raises(PebbleServiceError):
            pebble_service.plan(mocked_layer)

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_SERVICE, mocked_layer, combine=True
        )
        replan.assert_called_once()

    def test_render_pebble_layer(self, pebble_service: PebbleService) -> None:
        mock_source = MagicMock(spec=EnvVarConvertible)
        mock_source.to_env_vars.return_value = {
            "CACHE_ADDR": "valkey:6379",
            "LOG_LEVEL": "debug",
        }

        layer = pebble_service.render_pebble_layer(mock_source)
        layer_dict = layer.to_dict()

        expected_env = {
            **DEFAULT_CONTAINER_ENV,
            "CACHE_ADDR": "valkey:6379",
            "LOG_LEVEL": "debug",
        }
        assert layer_dict["services"][WORKLOAD_SERVICE]["environment"] == expected_env
        assert (
            layer_dict["checks"]["http-check"]["http"]["url"]
            == f"http://127.0.0.1:{STS_HTTP_PORT}/.well-known/jwks.json"
        )
        assert layer_dict["checks"]["grpc-check"]["tcp"]["port"] == STS_GRPC_PORT
