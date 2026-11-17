## 1. Configuration Manifest & Workload Mapping

- [x] 1.1 Add `oidc_scopes` configuration option (type `string`, default `"openid email profile offline_access"`) to `charmcraft.yaml` under `config.options` with a description explaining that it is a non-empty space-separated list that configures both the OIDC scopes requested at login (`OIDC_SCOPES`, comma-separated) and the scopes registered on the `oauth` relation.
- [x] 1.2 Update `CharmConfig` in `src/configs.py` to expose an `oidc_scopes` property (`str(self._config["oidc_scopes"]).split()`) and include `"OIDC_SCOPES": ",".join(self.oidc_scopes)` in `CharmConfig.to_env_vars()`.
- [x] 1.3 Add unit tests in `tests/unit/test_configs.py` covering the default `oidc_scopes` property (`list[str]`) and `OIDC_SCOPES` environment variable mapping (comma-separated), as well as custom `oidc_scopes` overrides and empty/whitespace input.

## 2. Charm Validation & OAuth Relation Synchronization

- [x] 2.1 Update `src/constants.py` and `src/charm.py`: remove the hardcoded `OAUTH_SCOPES` constant from `src/constants.py`, return `None` from `SecureTokenServiceCharm._oauth_client_config` when `self.charm_config.oidc_scopes` is empty and otherwise use `" ".join(scopes)`, validate in `_check_prerequisites()` that `self.charm_config.oidc_scopes` is non-empty (returning `BlockedStatus("Invalid oidc_scopes: must be a non-empty space-separated list of scopes")` if empty), and update the `oauth` client config via `_update_oauth_client_config()` on `_on_config_changed` and `_on_ingress_ready` when `self.unit.is_leader()` and `_oauth_client_config` is non-`None`.
- [x] 2.2 Add unit tests in `tests/unit/test_charm.py`: update the expected Pebble plan in `test_on_pebble_ready_correct_plan_with_cache` to include `"OIDC_SCOPES": "openid,email,profile,offline_access"`, and add scenario tests covering empty/whitespace `oidc_scopes` (`BlockedStatus`), custom `oidc_scopes` propagating to `OIDC_SCOPES` (comma-separated) in the Pebble layer and `scope` (space-separated) in the `oauth` relation databag, `_on_config_changed` and `_on_ingress_ready` gating `oauth.update_client_config` on leader status and non-empty `oidc_scopes`, and `oauth` `relation_created` populating default scopes only when `oidc_scopes` is valid.
- [x] 2.3 Update integration tests in `tests/integration/test_charm.py` to verify that configuring `oidc_scopes` propagates `OIDC_SCOPES` to the deployed workload's Pebble plan and updates the `oauth` relation databag.

## 3. Verification Suite

- [x] 3.1 Run `tox -e fmt`, `tox -e lint`, and `tox -e unit` to verify code formatting, static analysis, and unit test suite pass with zero errors.

## 4. Documentation & Rollout

- [x] 4.1 Update `README.md` to document the `oidc_scopes` option (type `string`, default `openid email profile offline_access`) in the Configuration table.
- [x] 4.2 Verify `terraform/` module compatibility (confirm generic `config` map variable passes `oidc_scopes` without requiring module schema changes) and record any findings in Implementation Notes.

## Implementation Notes

- Terraform module (`terraform/variables.tf`) exposes a generic `variable "config"` (`map(string)`, default `{}`), which passes `oidc_scopes` through to the charm without requiring any Terraform schema changes.
