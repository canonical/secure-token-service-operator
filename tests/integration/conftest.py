# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import secrets
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Callable, Generator

import jubilant
import pytest
from integration.constants import (
    CA_APP,
    DB_APP,
    HYDRA_APP,
    HYDRA_PUBLIC_ROUTE_INTEGRATION_NAME,
    ISTIO_INGRESS_APP,
    LOGIN_UI_APP,
    LOGIN_UI_INTEGRATION_NAME,
    STS_APP,
    VALKEY_APP,
)
from integration.utils import get_app_integration_data, juju_model_factory

from src.constants import PEER_INTEGRATION_NAME

logger = logging.getLogger(__name__)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options for model management and deployment control."""
    parser.addoption(
        "--keep-models",
        "--no-teardown",
        action="store_true",
        dest="no_teardown",
        default=False,
        help="Keep the model after the test is finished.",
    )
    parser.addoption(
        "--model",
        action="store",
        dest="model",
        default=None,
        help="The model to run the tests on.",
    )
    parser.addoption(
        "--no-deploy",
        "--no-setup",
        action="store_true",
        dest="no_setup",
        default=False,
        help="Skip deployment of the charm.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "setup: tests that setup some parts of the environment")
    config.addinivalue_line(
        "markers", "teardown: tests that teardown some parts of the environment."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Modify collected test items based on command-line options."""
    skip_setup = pytest.mark.skip(reason="no_setup provided")
    skip_teardown = pytest.mark.skip(reason="no_teardown provided")
    for item in items:
        if config.getoption("no_setup") and "setup" in item.keywords:
            item.add_marker(skip_setup)
        if config.getoption("no_teardown") and "teardown" in item.keywords:
            item.add_marker(skip_teardown)


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    model_name = request.config.getoption("--model") or f"test-sts-{secrets.token_hex(4)}"
    juju_ = juju_model_factory(model_name)
    juju_.wait_timeout = 15 * 60

    try:
        yield juju_
    finally:
        if request.session.testsfailed:
            print(juju_.debug_log(limit=1000), end="")

        if not (request.config.getoption("--no-teardown") or request.session.testsfailed > 0):
            with suppress(jubilant.CLIError):
                juju_.cli(
                    "destroy-model",
                    juju_.model,
                    "--no-prompt",
                    "--destroy-storage",
                    "--force",
                    "--timeout",
                    "600s",
                    include_model=False,
                )


@pytest.fixture(scope="session")
def local_charm() -> Path:
    """Get the path to the charm-under-test."""
    charm: str | Path | None = os.getenv("CHARM_PATH")
    if not charm:
        subprocess.run(["charmcraft", "pack"], check=True)
        if not (charms := list(Path(".").glob("*.charm"))):
            raise RuntimeError("Charm not found and build failed")
        charm = charms[0].absolute()
    return Path(charm)


def integrate_hydra_dependencies(juju: jubilant.Juju) -> None:
    """Integrate Hydra and its dependencies."""
    juju.integrate(f"{LOGIN_UI_APP}:public-route", f"{ISTIO_INGRESS_APP}:istio-ingress-route")
    juju.integrate(
        f"{HYDRA_APP}:{HYDRA_PUBLIC_ROUTE_INTEGRATION_NAME}",
        f"{ISTIO_INGRESS_APP}:istio-ingress-route",
    )
    juju.integrate(HYDRA_APP, DB_APP)
    juju.integrate(
        f"{HYDRA_APP}:{LOGIN_UI_INTEGRATION_NAME}", f"{LOGIN_UI_APP}:{LOGIN_UI_INTEGRATION_NAME}"
    )


def integrate_sts_dependencies(juju: jubilant.Juju) -> None:
    """Integrate STS with its core dependencies."""
    juju.integrate(f"{STS_APP}:oauth", f"{HYDRA_APP}:oauth")
    juju.integrate(f"{STS_APP}:pg-database", DB_APP)
    juju.integrate(f"{STS_APP}:receive-ca-cert", f"{CA_APP}:send-ca-cert")
    juju.integrate(STS_APP, f"{ISTIO_INGRESS_APP}:istio-ingress-route")
    juju.integrate(f"{STS_APP}:cache", f"{VALKEY_APP}:valkey-client")


@pytest.fixture
def app_integration_data(juju: jubilant.Juju) -> Callable:
    def _get_data(app_name: str, integration_name: str, unit_num: int = 0) -> dict | None:
        return get_app_integration_data(juju, app_name, integration_name, unit_num)

    return _get_data


@pytest.fixture
def leader_peer_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(STS_APP, PEER_INTEGRATION_NAME)
