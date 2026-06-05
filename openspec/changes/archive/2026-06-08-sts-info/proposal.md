## Why

Consumers of the Secure Token Service (e.g., identity-aware proxies, API gateways, or other charms in the identity platform) need a standardised Juju relation to discover STS endpoints at runtime. Without it, each consumer must hard-code or manually configure the STS service address, JWKS URL, and TLS settings.

## What Changes

- **New charm library** `lib/charms/secure_token_service/v0/sts_info.py` implementing the `sts_ready` interface.
- **New `StsInfoProvider`** class that emits a custom `sts_info_ready` event on `relation_created` and exposes an `update_relations_app_data()` method to populate the relation databag with:
  - `http_address` – base HTTP/REST URL (k8s svc by default; ingress URL when Istio ingress is present)
  - `grpc_address` – gRPC address (`<host>:9090`)
  - `jwks_url` – JWKS discovery URL (`<http_address>/.well-known/jwks.json`)
  - `tls_enabled` – stringified boolean derived from the Istio ingress requirer's `tls_enabled` property
- **New `StsInfoRequirer`** class with `get_sts_info()` (returns a Pydantic `StsInfoData` model), `is_ready()`, a `sts_info_relation_updated` custom event emitted on `relation_changed`, and a `sts_info_relation_broken` custom event emitted on `relation_broken` so consuming charms can react to provider updates and relation removal.
- **Charm wiring** in `src/charm.py`:
  - Instantiate `StsInfoProvider`; observe `sts_info_ready` → delegate to `_holistic_handler()`, which calls `update_relations_app_data()` when fully ready.
  - Re-publish on `ingress_ready` events so the URL stays current.
  - Only the leader unit writes to the relation databag.
- **`charmcraft.yaml`** updated with a new `provides: sts-info` entry using interface `sts_ready`.

## Capabilities

### New Capabilities

- `sts-info-lib`: Charm library (`charms.secure_token_service.v0.sts_info`) providing provider and requirer sides of the `sts_ready` interface, including the `sts_info_ready` custom event, `update_relations_app_data` method, `StsInfoRelationUpdatedEvent` and `StsInfoRelationBrokenEvent` for the requirer, and Pydantic v2 `StsInfoData` model.

### Modified Capabilities

- `charm-ingress-handling`: The charm's `_on_ingress_ready` handler is extended to refresh `sts-info` relation databags via `_holistic_handler()` so they are updated whenever the external URL changes.

## Impact

- **New file**: `lib/charms/secure_token_service/v0/sts_info.py`
- **Modified file**: `src/charm.py` (observe new events, call `update_relations_app_data` via holistic handler)
- **Modified file**: `charmcraft.yaml` (add `sts-info` provides relation)
- **No breaking changes** to existing integrations or the workload
- **Dependencies**: `ops`, `pydantic` (already in requirements)
