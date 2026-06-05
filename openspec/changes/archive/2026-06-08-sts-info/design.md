## Context

The STS charm currently has no way to advertise its endpoints and capabilities to other charms in the Juju model. Consumers (e.g., identity-aware proxies, API gateways, relying-party charms) need to discover the STS HTTP base URL, gRPC address, JWKS endpoint, and TLS status at runtime via a well-known Juju relation.

The existing codebase already has an `IstioIngressIntegration` class in `src/integrations.py` that exposes `external_url` and the underlying `requirer.tls_enabled` flag. The charm already handles `ingress_ready` events. The new library simply needs to plug into these existing hooks.

Reference: `lib/charms/kratos/v0/kratos_info.py` (same team, same pattern).

## Goals / Non-Goals

**Goals:**
- Implement `lib/charms/secure_token_service/v0/sts_info.py` with `StsInfoProvider` and `StsInfoRequirer`.
- Emit `sts_info_ready` on `relation_created`; expose `update_relations_app_data()` to write the databag.
- Default to the Kubernetes service address when no ingress is present; use the ingress external URL otherwise.
- Wire the provider into `src/charm.py` and add the `sts-info` provides entry to `charmcraft.yaml`.
- Requirement: use `pydantic` v2 for data validation in the library.

**Non-Goals:**
- Implementing a consuming charm (requirer side wiring belongs to downstream charms).
- Adding TLS certificate management to the library.
- Supporting multiple simultaneous ingress sources.

## Decisions

### D1 — Library placement: `lib/charms/secure_token_service/v0/sts_info.py`
The canonical charm library naming convention uses the *charm name* as the top-level package. `secure_token_service` matches the charmcraft name without hyphens.

### D2 — URL resolution: ingress-first, k8s-svc fallback
The provider's `update_relations_app_data()` accepts explicit `http_address` and `grpc_address` strings rather than resolving them internally. The charm passes values derived from `IstioIngressIntegration.external_url` (when available) or the k8s service address. This keeps URL resolution in the orchestration layer and the library free of charm-specific coupling.

**Alternative considered**: library resolves the URL itself by accepting an `IstioIngressIntegration` instance. Rejected because it couples the library to the charm's integration layer, making it harder to reuse.

### D3 — `tls_enabled` field in databag
Stored as a lowercase string `"true"`/`"false"` (same pattern as `kratos_info` for `mfa_enabled`). Requirer side parses it back to `bool` via a `field_validator` using `.casefold()` comparison.

### D4 — Leader-only writes
`update_relations_app_data()` returns early when `not self._charm.unit.is_leader()`. This matches `KratosInfoProvider` and avoids split-brain databag writes.

### D5 — Event name: `sts_info_ready`
Named to clearly signal that relation data is ready, following the `ready` convention of `KratosInfoProvider.on.ready`. The class-level event attribute is named `sts_info_ready` on `StsInfoProviderEvents`.

### D6 — `grpc_address` format
`<host>:<port>` (no scheme). gRPC clients typically parse the address separately; adding `grpc://` would break most gRPC dial strings.

### D7 — Pydantic v2 for databag data model
The library uses a `StsInfoData(pydantic.BaseModel)` with `http_address: str`, `grpc_address: str`, `jwks_url: str`, and `tls_enabled: StrictBool` fields. The provider serializes an instance to the databag (booleans stored as `"true"`/`"false"` strings via a `field_serializer`); the requirer deserializes using `StsInfoData.model_validate()` with a `field_validator(mode="before")` that accepts `str | bool`. This keeps databag field names and types as a single source of truth and provides automatic validation on the requirer side.

**Alternative considered**: raw dict read/write. Rejected because it scatters field names and type coercions across provider and requirer, making future changes error-prone.

### D8 — Method name: `update_relations_app_data`
Renamed from `send_info_relation_data` to `update_relations_app_data` to better reflect that the method updates the application relation databag (as opposed to unit databag), and to align with the naming convention used by similar methods in the identity platform libraries.

### D9 — Requirer custom event: `sts_info_relation_updated`
`StsInfoRequirer` observes `relation_changed` and emits `sts_info_relation_updated` (a bare `EventBase` subclass with no extra attributes). Consuming charms observe this event and call `get_sts_info()` to obtain current data. The bare-signal pattern avoids coupling the event to a snapshot of the data and keeps the API surface minimal.

### D10 — Requirer custom event: `sts_info_relation_broken`
`StsInfoRequirer` observes `relation_broken` and emits `sts_info_relation_broken` (bare signal). Consuming charms use this to react to the loss of the STS integration (e.g., enter a waiting/blocked state).

### D11 — `_on_sts_info_ready` delegates to `_holistic_handler`
Rather than calling `update_relations_app_data()` directly, `_on_sts_info_ready` delegates to `_holistic_handler()`, which calls `update_relations_app_data()` only when all prerequisites are satisfied and the workload is running. This ensures the databag is never populated when the charm is in a broken or waiting state.

### D12 — JWKS field name: `jwks_url`
Shortened from `jwks_set_url` to `jwks_url` for clarity. The term "set" was redundant — the field always holds a single URL pointing to the JWKS endpoint.

## Risks / Trade-offs

- **Ingress URL lag** → Mitigation: charm calls `update_relations_app_data()` (via holistic handler) both on `sts_info_ready` and on `ingress_ready`, so the databag is refreshed whenever the external URL changes.
- **Non-leader units cannot write** → by design; all units observe the event but only the leader writes. Non-leader units silently return.
- **Library LIBID is Charmhub-assigned** → the library has already been registered on Charmhub (`LIBID = "cb702f64e24d4f5f8448c49ed2eda26f"`, `LIBPATCH = 2`). The `LIBID` in the file **must not be changed** — it is set by Charmhub at registration time and is the stable identifier used by `charmcraft fetch-lib`. Increment only `LIBPATCH` (or `LIBAPI` for breaking changes) before each `charmcraft publish-lib` run.

## Migration Plan

1. Implement the library body in the already-registered file `lib/charms/secure_token_service/v0/sts_info.py`. Do **not** modify `LIBID`; increment `LIBPATCH` before publishing.
2. Add `provides: sts-info` to `charmcraft.yaml` and wire the charm — takes effect on next `juju refresh` or redeploy.
3. No data migration needed; the relation databag is written fresh on each `relation_created`.

## Open Questions

- None outstanding after user clarifications.
