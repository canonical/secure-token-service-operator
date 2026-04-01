# Charmed Secure Token Service (STS)

[![CharmHub Badge](https://charmhub.io/sts/badge.svg)](https://charmhub.io/secure-token-service)
[![Juju](https://img.shields.io/badge/Juju%20-3.0+-%23E95420)](https://github.com/juju/juju)
[![License](https://img.shields.io/github/license/canonical/secure-token-service-operator?label=License)](https://github.com/canonical/secure-token-service-operator/blob/main/LICENSE)

[![Continuous Integration Status](https://github.com/canonical/secure-token-service-operator/actions/workflows/on_push.yaml/badge.svg?branch=main)](https://github.com/canonical/secure-token-service-operator/actions?query=branch%3Amain)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196.svg)](https://conventionalcommits.org)

## Description

This repository hosts the Kubernetes Python Operator for the Secure Token Service (STS) - Janus.
It is a Policy Enforcement Point (PEP) and Security Token Service (STS) that sits between external clients and internal microservices.
Refer to the [STS documentation](https://github.com/canonical/secure-token-service) for more details and architectural overview.

## Usage

Once published the Secure Token Service Operator may be deployed using the Juju commandline as follows:

```shell
juju deploy secure-token-service --channel=latest/edge --trust
```

STS requires several dependencies to reach an active state. You can deploy and integrate them as follows:
```
# Deploy dependencies
juju deploy postgresql-k8s --channel 14/stable --trust
juju deploy hydra-k8s --channel latest/stable --trust
juju deploy self-signed-certificates --channel 1/stable --trust
juju deploy valkey-k8s --channel 9/edge --trust

# Integrate with Database (PostgreSQL)
juju integrate secure-token-service:pg-database postgresql-k8s:database

# Integrate with OAuth Provider (Hydra)
juju integrate secure-token-service:oauth hydra-k8s:oauth

# Integrate with CA Provider (e.g. self-signed-certificates or lego)
juju integrate secure-token-service:receive-ca-cert self-signed-certificates
```

**NOTE:** To connect Secure Token Service to cache, you need to retrieve the auto-generated operator credentials from Valkey
and pass them to STS via juju config:

1. **Retrieve the Valkey password:** Find the Juju secret that manages Valkey's internal users
and reveal it to get the password for the `charmed-operator` user.

   ```bash
   # List secrets to find the Valkey secret (with `valkey-peers.valkey.app.internal_users_secret` label)
   juju secrets

   # Reveal the secret to get the `charmed-operator-password`
   juju show-secret <secret-uri> --reveal
2. Configure Cache (Valkey):

    ```
    juju config secure-token-service cache_address=<address> cache_password=<password> cache_username=<username>
    ```

### Interacting with STS API

Once the service is deployed and accessible, you can interact with the STS API as documented [here](https://github.com/canonical/secure-token-service?tab=readme-ov-file#api-reference).

## Configuration

| Key                | Type | Default | Description                                                                                      |
|:-------------------| :--- | :--- |:-------------------------------------------------------------------------------------------------|
| **http_proxy**     | string | | URL of the HTTP proxy (e.g., `http://proxy.internal:6666`). Sets `HTTP_PROXY` in the workload.   |
| **https_proxy**    | string | | URL of the HTTPS proxy (e.g., `http://proxy.internal:6666`). Sets `HTTPS_PROXY` in the workload. |
| **no_proxy**       | string | | Comma-separated list of domains to exclude from proxying (e.g., `test.com,test.co.uk`).          |
| **log_level**      | string | `info` | Verbosity of logs. Available: `panic`, `fatal`, `error`, `warn`, `info`, `debug`, and `trace`.   |
| **cpu**            | string | | K8s CPU resource limit (e.g., `1` or `500m`). Sets the "limits" for the container.               |
| **memory**         | string | | K8s memory resource limit (e.g., `1Gi`). Sets the "limits" for the container.                    |
| **cache_address**  | string | | Address of the Redis/Valkey service (e.g., `127.0.0.1:6379`) for session data storage.           |
| **cache_password** | string | | Password for the Redis/Valkey service.                                                           |
| **cache_username** | string | | Username for the Redis/Valkey service.                                                           |
| **cache_db**       | int | `0` | Database number for the Redis/Valkey service.                                                    |
## Integrations

| Name                | Interface | Role | Description |
|:--------------------| :--- | :--- | :--- |
| **pg-database**     | `postgresql_client` | Requirer | Provides persistent storage for sessions and policies. |
| **oauth**           | `oauth` | Requirer | Integrates with an OIDC provider (e.g., Hydra) for client authentication. |
| **ingress**         | `istio_ingress_route` | Requirer | Configures external access and OIDC callback routes via Istio. |
| **service-mesh**    | `service_mesh` | Requirer | Provides service mesh integration for internal traffic management. |
| **receive-ca-cert** | `certificate_transfer` | Requirer | Receives trusted CA certificates to verify external OIDC providers. |

## Actions

### `run-migration`

This action performs the database schema migration. This is **mandatory** during the initial deployment or after an upgrade if the unit status is "Waiting for migration to run".

**Parameters:**
* `timeout`: (Optional) The time in seconds to wait for the migration to complete. Default is 120.

**Usage:**
```shell
juju run secure-token-service/leader run-migration timeout=300
```

## OCI Images

The [image](https://ghcr.io/canonical/secure-token-service) used by this charm is hosted on GitHub Container Registry (GHCR).

## Security

<!-- Please see [SECURITY.md](https://github.com/canonical/secure-token-service-operator/blob/main/SECURITY.md) for guidelines on reporting security issues. -->

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/secure-token-service-operator/blob/main/CONTRIBUTING.md) for developer guidance.

## License

The Charmed Secure Token Service Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](https://github.com/canonical/secure-token-service-operator/blob/main/LICENSE) for more information.
