# Tasks

## 1. Dependencies & Manifest Updates

- [x] 1.1 Add `dpcharmlibs-interfaces==1.2.2` to runtime dependencies in `pyproject.toml` and update `uv.lock` via `uv lock`.
- [x] 1.2 Declare the `cache` relation requirement with interface `valkey_client`, `optional: false`, and `limit: 1` in `charmcraft.yaml`.
- [x] 1.3 Remove manual cache configuration options (`cache_address`, `cache_username`, `cache_password`, `cache_db`) from `charmcraft.yaml`.
- [x] 1.4 Add `CACHE_INTEGRATION_NAME = "cache"` constant in `src/constants.py`.
- [x] 1.5 Remove cache environment variable mappings from `CharmConfig.to_env_vars()` in `src/configs.py`.
- [x] 1.6 Update unit tests in `tests/unit/test_configs.py` to verify `CharmConfig` without cache configuration fields.

## 2. Integration Data Layer

- [x] 2.1 Implement `CacheConfig` dataclass in `src/integrations.py` with `load(requirer)` extracting credentials and endpoints from `ResourceRequirerEventHandler` / `ValkeyResponseModel`, wrapping resource queries and model building in try-except blocks (`DataInterfacesError`, `ValidationError`, `SecretError`, `SecretsUnavailableError`, `ModelError`, `ValueError`), and `to_env_vars()` generating `CACHE_ADDR`, `CACHE_USERNAME`, and `CACHE_PASSWORD` when present.
- [x] 2.2 Add unit tests for `CacheConfig` in `tests/unit/test_integrations.py` validating data extraction, missing relation handling (returning empty/None), exception handling on data interface/secret errors, and environment dictionary generation.
- [x] 2.3 Implement `cache_integration_exists` helper in `src/utils.py`.

## 3. Charm Orchestration & Lifecycle Events

- [x] 3.1 Instantiate `ResourceRequirerEventHandler` from `dpcharmlibs.interfaces` with `relation_name=CACHE_INTEGRATION_NAME`, `requests=[RequirerCommonModel(resource="*")]`, and `response_model=ValkeyResponseModel` in `src/charm.py`.
- [x] 3.2 Register event observers for `self.valkey_interface.on` (including `resource_created`, `endpoints_changed`, `read_only_endpoints_changed`, `authentication_updated`, `status_raised`, `status_resolved`) and `self.on[CACHE_INTEGRATION_NAME].relation_broken` in `src/charm.py` routing to `_holistic_handler()`.
- [x] 3.3 Update `_pebble_layer` property in `src/charm.py` to conditionally include `CacheConfig.load(self.valkey_interface)` if `cache_integration_exists(self)`.
- [x] 3.4 Update `_check_prerequisites()` in `src/charm.py` to require cache and inspect relation statuses: if `not cache_integration_exists(self)`, return `BlockedStatus("Missing cache integration")`; inspect `self.valkey_interface.get_statuses(rel.id)` and return `BlockedStatus("Cache error: ...")` for fatal statuses or `WaitingStatus("Cache: ...")` for transitory statuses; if `not cache_config.endpoint`, return `WaitingStatus("Waiting for cache creation")`.
- [x] 3.5 Update unit test scenarios in `tests/unit/test_charm.py` to cover:
  - Blocked status when `cache` relation is absent.
  - Waiting status when `cache` relation is present but credentials not yet available.
  - Blocked status with error message when `cache` relation has a fatal status (`is_fatal=True`).
  - Waiting status with condition message when `cache` relation has a transitory status (`is_transitory=True`).
  - Event observation for `status_raised` and `status_resolved` triggering holistic reconciliation.
  - Active status with cache environment variables injected when all integrations including `cache` are ready.
  - Reconciliation to blocked status when `cache` relation is broken.

## 4. Integration Test Suite Updates

- [x] 4.1 Update `integrate_sts_dependencies()` in `tests/integration/conftest.py` to relate `secure-token-service:cache` with `valkey:valkey-client` and remove manual secret extraction helpers.
- [x] 4.2 Update `tests/integration/test_charm.py` to verify mandatory relation establishment, status transitions, and removing/re-adding cache in `test_remove_integration`.

## 5. Verification Suite

- [x] 5.1 Run code style, formatting, and linting suite (`tox -e fmt`, `tox -e lint`).
- [x] 5.2 Run unit test and coverage suite (`tox -e unit`).

## 6. Documentation & Rollout

- [x] 6.1 Update `README.md` integration and deployment guides to reflect the mandatory `cache` relation with `valkey-operator`.
- [x] 6.2 Update any deployment Terraform modules or bundle examples with the mandatory `cache` relation.

## Implementation Notes

- Updated Valkey (`cache`) integration from optional to mandatory: `optional: false` in `charmcraft.yaml`, `BlockedStatus("Missing cache integration")` when relation is absent, and included in `test_remove_integration` matrix.
- Added provider relation status evaluation (`get_statuses()`, `status_raised`, `status_resolved`) reflecting fatal errors (`BlockedStatus("Cache error: ...")`) and transitory conditions (`WaitingStatus("Cache: ...")`).
- Added robust error handling in `CacheConfig.load()` catching data interface errors, validation errors, secret errors, and model errors.
- Evaluated CA certificate requirements and determined cache CA cert path is not needed or supported since upstream `canonical/secure-token-service` Go binary only connects using `CACHE_ADDR`, `CACHE_USERNAME`, `CACHE_PASSWORD`, and `CACHE_DB` with no TLS/CA certificate options.
