## Tasks

### Implementation

- [x] **Task 1: Add OpenID config options to `charmcraft.yaml`** — Add `default_auth_provider` (string, default `"oidc"`), `ubuntu_one_openid_url` (string, default `"https://login.ubuntu.com/+openid"`), and `ubuntu_one_realm` (string, default `""`) under `config.options` with descriptions covering the realm/ingress requirement.
- [x] **Task 2: Map provider config to workload env vars in `src/configs.py`** — Extend `CharmConfig.to_env_vars()` to emit `DEFAULT_AUTH_PROVIDER` and `UBUNTU_ONE_OPENID_URL` unconditionally, and `UBUNTU_ONE_REALM` only when a realm resolves (explicit config value wins; otherwise ingress external URL when provider is `openid`). Add a `provider` property. Inject the ingress external URL lookup via the constructor so `CharmConfig` stays free of `ops.model` relation access.
- [x] **Task 3: Validate provider and realm in `src/charm.py`** — In `_check_prerequisites()`: block on `default_auth_provider` outside `{oidc, openid}` with a message naming the accepted values; when provider is `openid` with no `ubuntu_one_realm`, block if no `ingress` relation exists (actionable message), wait if the relation exists but has not published an external URL. OIDC never requires a realm.
- [x] **Task 4: Unit tests in `tests/unit/test_configs.py`** — Cover env var mapping: defaults (OIDC, no realm), explicit realm, ingress-derived realm for `openid`, and no realm emitted for `oidc`.
- [x] **Task 5: Unit tests in `tests/unit/test_charm.py`** — Scenario tests via `ops.testing`: invalid provider → `BlockedStatus`; `openid` without realm or ingress → `BlockedStatus`; `openid` with ingress lacking external URL → `WaitingStatus`; `openid` with realm derived from ingress → `ActiveStatus` and `UBUNTU_ONE_REALM` in the layer env; `openid` with explicit realm and no ingress → `ActiveStatus`; `oidc` with ingress, no realm → no `UBUNTU_ONE_REALM` in env. Update the expected pebble plan contract test with the two new always-on env keys.
- [x] **Task 6: Integration test in `tests/integration/test_charm.py`** — Configure `default_auth_provider=openid` with an explicit `ubuntu_one_realm` on the deployed charm and assert `DEFAULT_AUTH_PROVIDER` and `UBUNTU_ONE_REALM` land in the workload container environment.

### Verification suite

- [x] **Task 7: Run `tox -e fmt`, `tox -e lint`, and `tox -e unit`** — All must pass.

### Documentation & rollout

- [x] **Task 8: Update `README.md`** — Add the three options to the configuration table and document the realm/ingress requirement for OpenID.
- [x] **Task 9: Terraform module check** — The module surfaces charm config via the generic `config` map variable; no per-option variables are needed. Confirm and record here.

## Implementation Notes

- Terraform module (`terraform/variables.tf`) already accepts arbitrary charm config through `variable "config"` (map, default `{}`); the new options need no module change.
