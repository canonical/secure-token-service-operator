## Design Decisions

### 1. Validation Location
**Decision:** Config validation will be performed in `_check_prerequisites()` method in `src/charm.py`.

**Rationale:** Consistent with existing pattern where integration readiness checks happen in `_check_prerequisites()`. Keeps `CharmConfig` focused on mapping config to env vars.

**Implementation:**
- Add validation for `default_auth_provider ∈ {"oidc", "openid"}`
- When provider=`openid` and `ubuntu_one_realm` empty: check ingress integration for `external_url`
- Return appropriate `BlockedStatus` or `WaitingStatus` with clear messages

### 2. Realm Derivation Logic
**Decision:** When `ubuntu_one_realm` is empty and `default_auth_provider="openid"`, derive realm from `istio_ingress.external_url` if available.

**Flow:**
```
default_auth_provider = "openid"
ubuntu_one_realm = ""
|
+--> Check ingress integration
     |
     +--> Has external_url? → Use as realm
     |
     +--> No external_url but relation exists? → WaitingStatus
     |
     +--> No ingress relation? → BlockedStatus
```

### 3. Env Var Generation
**Decision:** Modify `CharmConfig.to_env_vars()` to accept optional `realm` parameter.

**Implementation:**
```python
def to_env_vars(self, realm: str | None = None) -> EnvVars:
    env_vars = {
        # existing mappings...
        "DEFAULT_AUTH_PROVIDER": self._config["default_auth_provider"],
        "UBUNTU_ONE_OPENID_URL": self._config["ubuntu_one_openid_url"],
    }
    if realm:
        env_vars["UBUNTU_ONE_REALM"] = realm
    return env_vars
```

### 4. Status Messages
**Decision:** Specific status messages for each validation failure:

1. `BlockedStatus("default_auth_provider must be 'oidc' or 'openid', got '{value}'")`
2. `BlockedStatus("OpenID provider requires ubuntu_one_realm or an ingress integration")`
3. `WaitingStatus("Waiting for ingress integration to provide external URL")`

### 5. Backward Compatibility
**Decision:** Default values ensure zero-change for existing deployments:
- `default_auth_provider: "oidc"`
- `ubuntu_one_openid_url: "https://login.ubuntu.com/+openid"`
- `ubuntu_one_realm: ""`

### 6. Testing Strategy
**Unit Tests:**
- `test_configs.py`: Test `CharmConfig.to_env_vars()` with new configs
- `test_configs.py`: Test provider validation
- `test_charm.py`: Scenario tests for blocked/waiting statuses

**Integration Tests:**
- Deploy with `default_auth_provider=openid` and verify env vars
- Test realm derivation from ingress
- Test blocked status without realm or ingress

### 7. Documentation Updates
- Update `README.md` configuration table
- Update any `terraform/` variable docs if config options are exposed there

### 8. Edge Cases Handled
1. **Provider switching**: Validation runs on each config-changed event
2. **Ingress relation added/removed**: `_holistic_handler()` re-evaluates on every unit. The charm observes the `ingress` relation's `relation_changed`/`relation_broken` events directly, because the requirer's `ready` event is emitted on the leader unit only; route submission and OAuth client config updates stay leader-gated
3. **Config update order**: Provider changed before ingress ready → blocked
4. **Realm explicitly set**: Use provided realm even if ingress exists