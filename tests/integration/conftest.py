# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import json
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
    CA_OFFER_NAME,
    DB_APP,
    DB_OFFER_NAME,
    HYDRA_APP,
    HYDRA_PUBLIC_ROUTE_INTEGRATION_NAME,
    ISTIO_INGRESS_APP,
    LOGIN_UI_APP,
    LOGIN_UI_INTEGRATION_NAME,
    STS_APP,
    TRAEFIK_OFFER_NAME,
    TRAEFIK_PUBLIC_APP,
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

    # Create a secondary model for core infrastructure
    core_model_name = f"{model_name}-core"
    juju_core = juju_model_factory(core_model_name)

    juju_.core_model = core_model_name

    try:
        yield juju_
    finally:
        if request.session.testsfailed:
            print(juju_.debug_log(limit=1000), end="")

            with suppress(Exception):
                print(juju_core.debug_log(limit=1000), end="")

        # Respect teardown flags for both models
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
            with suppress(jubilant.CLIError):
                juju_.cli(
                    "destroy-model",
                    core_model_name,
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


def get_valkey_password(juju: jubilant.Juju) -> str:
    """Fetch the operator password from Valkey's Juju secrets."""
    secret_label = f"{VALKEY_APP}-peers.{VALKEY_APP}.app.internal_users_secret"

    try:
        stdout = juju.cli("show-secret", secret_label, "--reveal", "--format=json")
        secret_data = json.loads(stdout)

        secret_id = list(secret_data.keys())[0]
        content = secret_data[secret_id].get("content", {})

        operator_password = content.get("Data", {}).get("charmed-operator-password")

        if not operator_password:
            raise RuntimeError("charmed-operator-password not found in the secret content")

        return operator_password

    except Exception as e:
        raise RuntimeError(f"Failed to retrieve valkey operator password from secret: {e}")


def integrate_core_dependencies(juju: jubilant.Juju) -> None:
    """Integrate infrastructure components within the core model."""
    juju.integrate(f"{TRAEFIK_PUBLIC_APP}:certificates", f"{CA_APP}:certificates")


def integrate_hydra_dependencies(juju: jubilant.Juju) -> None:
    """Integrate Hydra and its dependencies using local apps and consumed offers."""
    juju.integrate(f"{LOGIN_UI_APP}:public-route", TRAEFIK_OFFER_NAME)
    juju.integrate(f"{HYDRA_APP}:{HYDRA_PUBLIC_ROUTE_INTEGRATION_NAME}", TRAEFIK_OFFER_NAME)
    juju.integrate(HYDRA_APP, DB_OFFER_NAME)
    juju.integrate(
        f"{HYDRA_APP}:{LOGIN_UI_INTEGRATION_NAME}", f"{LOGIN_UI_APP}:{LOGIN_UI_INTEGRATION_NAME}"
    )


def integrate_sts_dependencies(juju: jubilant.Juju) -> None:
    """Integrate STS with its core dependencies using local apps and consumed offers."""
    juju.integrate(f"{STS_APP}:oauth", f"{HYDRA_APP}:oauth")
    juju.integrate(f"{STS_APP}:pg-database", DB_OFFER_NAME)
    juju.integrate(f"{STS_APP}:receive-ca-cert", CA_OFFER_NAME)


def integrate_istio_dependencies(juju: jubilant.Juju) -> None:
    """Integrate STS with Istio Ingress Route."""
    juju.integrate(STS_APP, f"{ISTIO_INGRESS_APP}:istio-ingress-route")


def offer_core_endpoints(juju: jubilant.Juju) -> None:
    """Create Juju offers for the core infrastructure endpoints."""
    core_model = juju.core_model
    logger.info("Offering core endpoints via CLI")

    endpoints = [
        (TRAEFIK_PUBLIC_APP, TRAEFIK_OFFER_NAME),
        (DB_APP, DB_OFFER_NAME),
        (CA_APP, CA_OFFER_NAME),
    ]

    for app, offer in endpoints:
        juju.cli("offer", f"{core_model}.{app}:{offer}", offer, include_model=False)


def consume_core_offers(juju: jubilant.Juju) -> None:
    """Consume the core infrastructure offers."""
    core_model = juju.core_model
    logger.info("Consuming core offers in primary model")

    offers = [
        TRAEFIK_OFFER_NAME,
        DB_OFFER_NAME,
        CA_OFFER_NAME,
    ]
    for offer in offers:
        juju.cli("consume", f"admin/{core_model}.{offer}")


@pytest.fixture
def app_integration_data(juju: jubilant.Juju) -> Callable:
    def _get_data(app_name: str, integration_name: str, unit_num: int = 0) -> dict | None:
        return get_app_integration_data(juju, app_name, integration_name, unit_num)

    return _get_data


@pytest.fixture
def leader_peer_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(STS_APP, PEER_INTEGRATION_NAME)
