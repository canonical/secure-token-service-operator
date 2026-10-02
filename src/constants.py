# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path
from string import Template

# Application constants
WORKLOAD_CONTAINER = "secure-token-service"
WORKLOAD_SERVICE = "secure-token-service"
STS_HTTP_PORT = 8080
STS_GRPC_PORT = 9090

HTTP_PROXY = "JUJU_CHARM_HTTP_PROXY"
HTTPS_PROXY = "JUJU_CHARM_HTTPS_PROXY"
NO_PROXY = "JUJU_CHARM_NO_PROXY"

# Integration constants
PEER_INTEGRATION_NAME = "peer"
COOKIE_SECRET_KEY = "cookies_key"

DATABASE_INTEGRATION_NAME = "pg-database"
POSTGRESQL_DSN_TEMPLATE = Template("postgres://$username:$password@$endpoint/$database")

INGRESS_HTTP_PORT = 80
ISTIO_INGRESS_INTEGRATION_NAME = "ingress"
STS_INFO_INTEGRATION_NAME = "sts-info"

OAUTH_INTEGRATION_NAME = "oauth"
OAUTH_SCOPES = "openid email profile offline_access"
OAUTH_GRANT_TYPES = ["authorization_code", "refresh_token"]

RECEIVE_CA_CERT_INTEGRATION_NAME = "receive-ca-cert"
CERTIFICATES_PATH = Path("/etc/ssl/certs")
CERTIFICATES_FILE = Path(CERTIFICATES_PATH / "ca-certificates.crt")
LOCAL_CA_BUNDLE_PATH = Path("/usr/local/share/ca-certificates/ca-certificates.crt")

CACHE_INTEGRATION_NAME = "cache"
