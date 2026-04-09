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
    consume_core_offers,
    integrate_core_dependencies,
    integrate_hydra_dependencies,
    integrate_istio_dependencies,
    integrate_sts_dependencies,
    offer_core_endpoints,
)
from integration.constants import (
    CA_APP,
    CA_OFFER_NAME,
    DB_APP,
    DB_OFFER_NAME,
    HYDRA_APP,
    ISTIO_APP,
    ISTIO_INGRESS_APP,
    LOGIN_UI_APP,
    STS_APP,
    STS_IMAGE,
    TRAEFIK_CHARM,
    TRAEFIK_PUBLIC_APP,
    VALKEY_APP,
)
from integration.utils import (
    StatusPredicate,
    all_active,
    and_,
    any_error,
    get_ingress_external_host,
    is_active_and_idle,
    is_blocked,
    remove_integration,
    unit_number,
)

from src.constants import (
    DATABASE_INTEGRATION_NAME,
    OAUTH_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    RECEIVE_CA_CERT_INTEGRATION_NAME,
)

logger = logging.getLogger(__name__)


@pytest.mark.setup
def test_build_and_deploy_hydra_core_deps(juju: jubilant.Juju) -> None:
    """Deploy and integrate Hydra and core dependencies."""
    model = juju.model
    core_model = juju.core_model

    logger.info(f"Switching Juju context to core model: {core_model}")
    juju.model = core_model

    logger.info("Deploying Traefik, Postgres DB, and CA to the core model")
    juju.deploy(
        TRAEFIK_CHARM,
        app=TRAEFIK_PUBLIC_APP,
        channel="latest/stable",
        trust=True,
    )
    juju.deploy(DB_APP, channel="14/stable", trust=True)
    juju.deploy(CA_APP, channel="1/stable", trust=True)
    integrate_core_dependencies(juju)

    # Expose the endpoints from the core model
    offer_core_endpoints(juju)

    juju.wait(
        ready=all_active(
            TRAEFIK_PUBLIC_APP,
            DB_APP,
            CA_APP,
        ),
        timeout=15 * 60,
    )

    logger.info(f"Switching Juju context to primary model: {model}")
    juju.model = model

    logger.info("Deploying Hydra and Login UI to primary model")
    juju.deploy(LOGIN_UI_APP, channel="latest/stable", trust=True)
    juju.deploy(HYDRA_APP, channel="latest/stable", trust=True)

    consume_core_offers(juju)

    logger.info("Integrating Hydra and Login UI")
    integrate_hydra_dependencies(juju)

    juju.wait(
        ready=all_active(
            HYDRA_APP,
            LOGIN_UI_APP,
        ),
        timeout=15 * 60,
    )


@pytest.mark.skip(reason="Valkey is currently only available in the edge channel and fails to start in GitHub CI")
@pytest.mark.setup
def test_deploy_valkey(juju: jubilant.Juju) -> None:
    """Deploy Valkey."""
    logger.info("Deploying Valkey")
    juju.deploy(
        VALKEY_APP,
        channel="9/edge",
        trust=True,
    )

    juju.wait(ready=is_active_and_idle(VALKEY_APP), timeout=10 * 60)


@pytest.mark.setup
def test_build_and_deploy(juju: jubilant.Juju, local_charm: Path, tmp_path: Path) -> None:
    """Deploy STS and integrate its dependencies."""
    logger.info("Fetching Secure Token Service image")
    gh_username = os.getenv("GH_USERNAME")
    gh_pat = os.getenv("GH_PAT")

    # Handle the image resource based on environment (GitHub CI/local)
    if gh_username and gh_pat:
        # Create the file inside the pytest temporary directory
        image_resource_path = tmp_path / "image.yaml"

        content = (
            f"registrypath: {STS_IMAGE}\n"
            f"username: {gh_username}\n"
            f"password: {gh_pat}\n"
        )
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

    integrate_sts_dependencies(juju)

    # TODO: Uncomment when valkey is stable
    # valkey_password = get_valkey_password(juju)

    # juju.config(
    #     STS_APP,
    #     {"cache_address": f"{VALKEY_APP}:6379", "cache_username": "charmed-operator", "cache_password": valkey_password}
    # )

    # juju.wait(
    #     ready=all_active(
    #         STS_APP,
    #         HYDRA_APP,
    #         VALKEY_APP,
    #     ),
    #     timeout=15 * 60,
    # )

    # STS is expected to block when cache config is missing
    juju.wait(
        ready=is_blocked(STS_APP),
        error=any_error(STS_APP),
        timeout=10 * 60,
    )


@pytest.mark.skip(reason="Missing Valkey config blocks STS from starting")
@pytest.mark.setup
def test_deploy_and_integrate_istio(juju: jubilant.Juju) -> None:
    """Deploy Istio and integrate it with STS through the ingress-route relation."""
    logger.info("Deploying Istio components")

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

    integrate_istio_dependencies(juju)

    juju.wait(
        ready=all_active(
            STS_APP,
            ISTIO_APP,
            ISTIO_INGRESS_APP,
        ),
        timeout=10 * 60,
    )


@pytest.mark.skip(reason="Missing Valkey config blocks STS from starting")
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
    assert response.status_code in (302, 303), f"Expected redirect, got {response.status_code}. Response body: {response.text}"


@pytest.mark.skip(reason="Missing Valkey config blocks STS from starting")
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


@pytest.mark.skip(reason="Missing Valkey config blocks STS from starting")
@pytest.mark.parametrize(
    "remote_app_name,integration_name,endpoint,is_status",
    [
        (DB_OFFER_NAME, DATABASE_INTEGRATION_NAME, "", is_blocked),
        (HYDRA_APP, OAUTH_INTEGRATION_NAME, "", is_blocked),
        (CA_OFFER_NAME, RECEIVE_CA_CERT_INTEGRATION_NAME, "", is_blocked),
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


@pytest.mark.skip(reason="Missing Valkey config blocks STS from starting")
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
