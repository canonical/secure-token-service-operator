#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
from pathlib import Path
from typing import Callable, Optional

import jubilant
import pytest
import requests
from integration.conftest import (
    integrate_hydra_dependencies,
    integrate_sts_dependencies,
)
from integration.constants import (
    CA_APP,
    DB_APP,
    HYDRA_APP,
    ISTIO_APP,
    ISTIO_INGRESS_APP,
    LOGIN_UI_APP,
    STS_APP,
    STS_IMAGE,
    VALKEY_APP,
)
from integration.utils import (
    StatusPredicate,
    all_active,
    and_,
    any_error,
    get_ingress_external_host,
    is_blocked,
    remove_integration,
    unit_number,
)

from src.constants import (
    CACHE_INTEGRATION_NAME,
    DATABASE_INTEGRATION_NAME,
    OAUTH_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    RECEIVE_CA_CERT_INTEGRATION_NAME,
)

logger = logging.getLogger(__name__)


@pytest.mark.setup
def test_build_and_deploy_hydra_core_deps(juju: jubilant.Juju) -> None:
    """Deploy and integrate Hydra and core dependencies."""
    logger.info("Deploying Postgres DB and CA")
    juju.deploy(DB_APP, channel="14/stable", trust=True)
    juju.deploy(CA_APP, channel="1/stable", trust=True)

    logger.info("Deploying Istio, Hydra, and Login UI")
    juju.deploy(
        ISTIO_APP,
        channel="2/stable",
        trust=True,
    )
    juju.deploy(
        ISTIO_INGRESS_APP,
        channel="2/stable",
        trust=True,
    )
    juju.integrate(ISTIO_INGRESS_APP, ISTIO_APP)
    juju.integrate(f"{ISTIO_INGRESS_APP}:certificates", f"{CA_APP}:certificates")

    juju.deploy(LOGIN_UI_APP, channel="istio/edge", trust=True)
    juju.deploy(
        HYDRA_APP,
        channel="istio/edge",
        config={"dev": True},
        trust=True
    )

    logger.info("Integrating Hydra and Login UI")
    integrate_hydra_dependencies(juju)

    juju.wait(
        ready=all_active(
            DB_APP,
            CA_APP,
            HYDRA_APP,
            LOGIN_UI_APP,
            ISTIO_APP,
            ISTIO_INGRESS_APP,
        ),
        timeout=15 * 60,
    )


@pytest.mark.setup
def test_build_and_deploy(juju: jubilant.Juju, local_charm: Path, tmp_path: Path) -> None:
    """Deploy STS with Valkey and integrate their dependencies."""
    logger.info("Fetching Secure Token Service image")
    gh_username = os.getenv("GH_USERNAME")
    gh_pat = os.getenv("GH_PAT")

    # Handle the image resource based on environment (GitHub CI/local)
    if gh_username and gh_pat:
        # Create the file inside the pytest temporary directory
        image_resource_path = tmp_path / "image.yaml"

        content = f"registrypath: {STS_IMAGE}\nusername: {gh_username}\npassword: {gh_pat}\n"
        image_resource_path.write_text(content)
        resource = {"oci-image": str(image_resource_path)}
    else:
        resource = {"oci-image": STS_IMAGE}

    logger.info("Deploying Secure Token Service")
    juju.deploy(
        str(local_charm),
        resources=resource,
        app=STS_APP,
        trust=True,
    )

    logger.info("Deploying Valkey")
    juju.deploy(
        VALKEY_APP,
        channel="9/edge",
        trust=True,
    )

    integrate_sts_dependencies(juju)

    juju.wait(
        ready=all_active(
            STS_APP,
            CA_APP,
            ISTIO_APP,
            ISTIO_INGRESS_APP,
            VALKEY_APP,
        ),
        timeout=10 * 60,
    )


def test_ingress_routing_and_redirect(juju) -> None:
    """Verifies HTTP routing via Istio Ingress and Hydra redirects from STS."""
    try:
        ingress_ip = get_ingress_external_host(juju, app_name=STS_APP)
    except Exception as e:
        pytest.fail(str(e))

    login_url = f"http://{ingress_ip}/auth/login"
    logger.info(f"Testing login endpoint access at {login_url}")

    # allow_redirects=False ensures we capture the 302/303 response from STS
    try:
        response = requests.get(login_url, allow_redirects=False)
    except requests.RequestException as e:
        pytest.fail(f"Failed to connect to Istio Ingress at {login_url}: {e}")

    # Verify the redirection to Hydra
    assert response.status_code in (302, 303), (
        f"Expected redirect, got {response.status_code}. Response body: {response.text}"
    )


def test_sts_scale_up(
    juju: jubilant.Juju,
    leader_peer_integration_data: Optional[dict],
    app_integration_data: Callable,
) -> None:
    target_unit_number = 2
    juju.cli("scale-application", STS_APP, str(target_unit_number))

    juju.wait(
        ready=and_(
            all_active(STS_APP),
            unit_number(STS_APP, target_unit_number),
        ),
        error=any_error(STS_APP),
        timeout=5 * 60,
    )

    follower_peer_data = app_integration_data(STS_APP, PEER_INTEGRATION_NAME, 1)
    assert follower_peer_data
    assert leader_peer_integration_data == follower_peer_data


@pytest.mark.parametrize(
    "remote_app_name,integration_name,endpoint,is_status",
    [
        (DB_APP, DATABASE_INTEGRATION_NAME, "", is_blocked),
        (HYDRA_APP, OAUTH_INTEGRATION_NAME, "", is_blocked),
        (CA_APP, RECEIVE_CA_CERT_INTEGRATION_NAME, "send-ca-cert", is_blocked),
        (VALKEY_APP, CACHE_INTEGRATION_NAME, "", is_blocked),
    ],
)
def test_remove_integration(
    juju: jubilant.Juju,
    remote_app_name: str,
    integration_name: str,
    endpoint: str,
    is_status: Callable[[str], StatusPredicate],
) -> None:
    """Test removing and re-adding mandatory integrations."""
    with remove_integration(juju, remote_app_name, integration_name, endpoint):
        juju.wait(
            ready=is_status(STS_APP),
            error=any_error(STS_APP),
            timeout=10 * 60,
        )

    juju.wait(
        ready=all_active(STS_APP),
        error=any_error(STS_APP),
        timeout=10 * 60,
    )


def test_sts_scale_down(juju: jubilant.Juju) -> None:
    target_unit_num = 1
    juju.cli("scale-application", STS_APP, str(target_unit_num))

    juju.wait(
        ready=and_(
            all_active(STS_APP),
            unit_number(STS_APP, target_unit_num),
        ),
        error=any_error(STS_APP),
        timeout=5 * 60,
    )


@pytest.mark.teardown
def test_remove_application(juju: jubilant.Juju) -> None:
    """Test removing the application."""
    juju.remove_application(STS_APP, destroy_storage=True)
    juju.wait(lambda s: STS_APP not in s.apps, timeout=10 * 60)
