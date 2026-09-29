## Why

Currently, operators must manually extract credentials from Valkey's internal Juju secrets and configure `cache_address`, `cache_username`, `cache_password`, and `cache_db` in Secure Token Service (STS). Adopting the modern `valkey_client` (v1) relation interface via `dpcharmlibs-interfaces==1.2.2` automates endpoint discovery, credential management, and lifecycle events between Valkey and STS as a mandatory integration.

## What Changes

- **Dependency**: Add `dpcharmlibs-interfaces==1.2.2` to runtime dependencies in `pyproject.toml`.
- **New Integration**: Declare mandatory `cache` relation endpoint in `charmcraft.yaml` (`interface: valkey_client`, `optional: false`).
- **Valkey Client Requirer**: Adopt `ResourceRequirerEventHandler` with `ValkeyResponseModel` and `RequirerCommonModel(resource="*")` from `dpcharmlibs.interfaces` to handle relation events and retrieve connection endpoints and credentials when related.
- **Mandatory Prerequisite Handling**: The cache integration is mandatory; STS enters `BlockedStatus("Missing cache integration")` when unrelated, and waits (`WaitingStatus("Waiting for cache creation")`) when related but endpoints/credentials are still provisioning.
- **Configuration Cleanup**: Remove manual `cache_address`, `cache_username`, and `cache_password` Juju config options (**BREAKING** for deployments relying on manual config).
- **Workload Environment Mapping**: Pass Valkey connection parameters dynamically to the STS Pebble service environment when the relation is present.

## Non-goals

- Supporting multiple concurrent cache backends or active-active failover orchestration within STS.
- Implementing custom Redis/Valkey sentinel protocol parsing inside the Go workload binary directly.

## Success Metrics

- 100% automated cache credential exchange and endpoint discovery via `juju integrate secure-token-service valkey`.
- STS starts cleanly in `ActiveStatus` when related to Valkey and all required dependencies.
- Zero manual secret extraction needed during deployment and operation.
- Immediate workload reconciliation on Valkey credential rotation, relation addition, or relation removal.

## Capabilities

### New Capabilities

- `valkey-client-integration`: Provides automated discovery, credential acquisition, and lifecycle management for the mandatory Valkey cache backend using the `valkey_client` (v1) relation interface via `dpcharmlibs.interfaces`.

### Modified Capabilities

None.

## Workload Data Provenance

| Relation Field | STS Environment Variable | Description |
| :--- | :--- | :--- |
| `endpoints` | `CACHE_ADDR` | Primary write endpoint (`host:port`) |
| `username` | `CACHE_USERNAME` | Auto-generated ACL username |
| `password` | `CACHE_PASSWORD` | Auto-generated ACL password |

## Impact

- **Dependencies**: `pyproject.toml` (add `dpcharmlibs-interfaces==1.2.2`).
- **Manifest**: `charmcraft.yaml` (add mandatory `requires: cache`, remove manual cache config options).
- **Source Code**: `src/charm.py`, `src/integrations.py`, `src/configs.py`, `src/constants.py`, `src/utils.py`.
- **Tests**: Add unit and integration tests for mandatory Valkey relation lifecycle and environment variable rendering.
