# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
STS_APP = METADATA["name"]
STS_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]

HYDRA_APP = "hydra"
DB_APP = "postgresql-k8s"
DB_OFFER_NAME = "database"
CA_APP = "self-signed-certificates"
CA_OFFER_NAME = "send-ca-cert"
VALKEY_APP = "valkey"
ISTIO_APP = "istio-k8s"
ISTIO_INGRESS_APP = "istio-ingress-k8s"

HYDRA_PUBLIC_ROUTE_INTEGRATION_NAME = "public-route"
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_PUBLIC_APP = "traefik-public"
TRAEFIK_OFFER_NAME = "traefik-route"
LOGIN_UI_APP = "identity-platform-login-ui-operator"
LOGIN_UI_INTEGRATION_NAME = "ui-endpoint-info"
