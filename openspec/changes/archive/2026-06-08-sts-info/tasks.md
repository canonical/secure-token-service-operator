# Tasks

## Milestone 1: Library implementation

- [x] 1.1 Create `lib/charms/secure_token_service/v0/sts_info.py` with `LIBID`, `LIBAPI = 0`, `LIBPATCH = 2`
- [x] 1.2 Implement `StsInfoData(pydantic.BaseModel)` with fields `http_address`, `grpc_address`, `jwks_url`, `tls_enabled: StrictBool`, a `field_validator(mode="before")` for `tls_enabled` (accepts `str | bool`, casefold comparison), and a `field_serializer` that writes `"true"`/`"false"`
- [x] 1.3 Implement `StsInfoProviderEvents` with `sts_info_ready: EventBase`
- [x] 1.4 Implement `StsInfoProvider` with `__init__`, leader-only guard, and `update_relations_app_data(http_address, grpc_address, jwks_url, tls_enabled)` that writes `StsInfoData` to all app relation databags
- [x] 1.5 Emit `sts_info_ready` on `relation_created` in `StsInfoProvider`
- [x] 1.6 Implement `StsInfoRequirerEvents` with `sts_info_relation_updated: EventBase` and `sts_info_relation_broken: EventBase`
- [x] 1.7 Implement `StsInfoRequirer` with `get_sts_info()` returning `StsInfoData | None`, `is_ready()` returning `bool`, and observer for `relation_changed` emitting `sts_info_relation_updated`
- [x] 1.8 Observe `relation_broken` in `StsInfoRequirer` and emit `sts_info_relation_broken`
- [x] 1.9 Write unit tests for `StsInfoData` serialization roundtrip and both provider and requirer sides (including `sts_info_relation_updated` and `sts_info_relation_broken` events)

## Milestone 2: Charm wiring

- [x] 2.1 Add `provides: sts-info` with interface `sts_ready` to `charmcraft.yaml`
- [x] 2.2 Instantiate `StsInfoProvider` in `SecureTokenServiceOperatorCharm.__init__`
- [x] 2.3 Observe `sts_info_ready` → `_on_sts_info_ready` in `charm.py`
- [x] 2.4 Implement `_on_sts_info_ready` to delegate to `_holistic_handler`
- [x] 2.5 Implement `_send_sts_info_rel_data()` to resolve HTTP address (ingress URL or k8s svc default), build `grpc_address` and `jwks_url`, and call `provider.update_relations_app_data()`
- [x] 2.6 Call `_send_sts_info_rel_data()` inside `_holistic_handler` before setting `ActiveStatus`
- [x] 2.7 Ensure `_on_ingress_ready` triggers `_holistic_handler` (so databag refreshes on URL changes)
- [x] 2.8 Only leader unit writes to databag (enforced in library)
- [x] 2.9 Write charm state tests for `TestStsInfoIntegration` covering: leader writes correct databag, non-leader skips writes, ingress URL update refreshes databag

## Milestone 3: Spec and artifact updates

- [x] 3.1 Write `openspec/specs/sts-info-lib/spec.md` covering `StsInfoProvider`, `StsInfoRequirer`, `StsInfoData`, both custom events, and all requirements
- [x] 3.2 Update `openspec/specs/charm-ingress-handling/spec.md` to reference `jwks_url` and `update_relations_app_data`
- [x] 3.3 Ensure `proposal.md`, `design.md`, and `tasks.md` are complete and accurate in the archive
