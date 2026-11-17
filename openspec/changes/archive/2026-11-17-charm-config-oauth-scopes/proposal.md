## Why

The `secure-token-service` charm currently hardcodes `OAUTH_SCOPES = "openid email profile offline_access"` in `src/constants.py` for OAuth client registration and does not expose a way for operators to customize the requested OIDC scopes. Introducing an `oidc_scopes` charm configuration option (matching the upstream service's `OIDC_SCOPES` configuration) allows operators to configure the scopes requested both during OAuth2 client registration (via the `oauth` relation) and at runtime by the workload (`OIDC_SCOPES` environment variable), while preserving the default `"openid email profile offline_access"`.

## What Changes

- Add `oidc_scopes` configuration option (type `string`, default `"openid email profile offline_access"`, space-separated) in `charmcraft.yaml`.
- Expose `oidc_scopes` on `CharmConfig` (`src/configs.py`) as a `list[str]` parsed via `.split()` and map it to the `OIDC_SCOPES` workload environment variable as a comma-separated string (`",".join(self.oidc_scopes)`).
- Validate in `_check_prerequisites()` (`src/charm.py`) that `oidc_scopes` is a non-empty list of scopes (not empty or whitespace-only), putting the unit into `BlockedStatus` if empty.
- Pass the configured `oidc_scopes` joined by spaces (`" ".join(scopes)`) to `OauthClientConfig(scope=...)` and update the `oauth` relation client config on leader units when configuration changes.
- Remove the hardcoded `OAUTH_SCOPES` constant from `src/constants.py`.

## Non-goals

- Reading or deriving requested scopes from the `oauth` provider relation databag (provider-advertised scopes do not include `offline_access` by default and represent server capabilities rather than client requirements).
- Granular per-scope semantic validation beyond requiring a non-empty space-separated list.
- Changes to the upstream `secure-token-service` workload binary.

## Environmental updates

| Source | Destination | Purpose |
|--------|-------------|---------|
| charm config `oidc_scopes` (space-separated) | workload env `OIDC_SCOPES` (comma-separated) | OIDC scopes requested by STS during user login (parsed by Go `envconfig` `[]string`) |
| charm config `oidc_scopes` (space-separated) | `oauth` relation `scope` (`OauthClientConfig`, space-separated) | Scopes registered for the OAuth2 client in Hydra |

## Success Metrics

- Operators can customize OIDC scopes via `juju config secure-token-service oidc_scopes="..."`, updating both the workload environment (`OIDC_SCOPES`) and the `oauth` relation databag (`scope`).
- Setting `oidc_scopes=""` or whitespace-only transitions the unit to `BlockedStatus` with a clear, actionable message.
- Existing deployments using default configuration retain `"openid email profile offline_access"` with zero breaking changes.

## Capabilities

### New Capabilities

### Modified Capabilities
- `charm-configuration`: Add `oidc_scopes` configuration option, non-empty validation, `OIDC_SCOPES` workload environment variable mapping, and `oauth` relation client configuration synchronization.

## Impact

- `charmcraft.yaml`: New `oidc_scopes` config option.
- `src/constants.py`: Remove unused hardcoded `OAUTH_SCOPES` constant.
- `src/configs.py`: Expose `oidc_scopes` on `CharmConfig` and emit `OIDC_SCOPES` in `to_env_vars()`.
- `src/charm.py`: Validate `oidc_scopes` in `_check_prerequisites()`, use `self.charm_config.oidc_scopes` in `_oauth_client_config`, and call `self.oauth.update_client_config()` on config changes when leader.
- `tests/unit/` & `tests/integration/`: Update existing pebble plan expectations and add unit/integration test coverage for `oidc_scopes`.
- `README.md`: Document `oidc_scopes` in the configuration table.
