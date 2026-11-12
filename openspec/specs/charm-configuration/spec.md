## Purpose

This capability governs how the charm validates operator-supplied configuration and maps it to the workload's environment variables. It covers the authentication provider selection (`oidc` vs Ubuntu One `openid`), the OpenID endpoint URL, and OpenID realm resolution — including derivation of the realm from the ingress integration and the blocked/waiting statuses reported when the configuration cannot produce a working provider setup.

## Requirements

### Requirement: Authentication provider config options are exposed with safe defaults
The charm SHALL expose `default_auth_provider`, `ubuntu_one_openid_url`, and `ubuntu_one_realm` as configuration options. `default_auth_provider` SHALL default to `oidc`, and `ubuntu_one_openid_url` SHALL default to `https://login.ubuntu.com/+openid`. `ubuntu_one_realm` SHALL be optional with an empty default.

These defaults preserve backward compatibility: an existing deployment that has not set any of the three options behaves exactly as before this capability was introduced.

#### Scenario: Default deployment is OIDC-only
- **WHEN** the operator has not set any of the three options
- **THEN** the workload runs with `DEFAULT_AUTH_PROVIDER=oidc` and `UBUNTU_ONE_OPENID_URL=https://login.ubuntu.com/+openid`, and no `UBUNTU_ONE_REALM` is set

### Requirement: default_auth_provider is validated against accepted values
The charm SHALL accept only `oidc` or `openid` as values for `default_auth_provider`. Any other value SHALL result in `BlockedStatus` naming the invalid value and the accepted set.

#### Scenario: Invalid provider value is rejected
- **WHEN** the operator sets `default_auth_provider` to an unlisted value (e.g., `"saml"`)
- **THEN** the unit enters `BlockedStatus` with a message stating the value must be `oidc` or `openid`

#### Scenario: Valid openid provider is accepted
- **WHEN** the operator sets `default_auth_provider` to `openid` and a realm is resolvable
- **THEN** the charm accepts the value and the workload runs with `DEFAULT_AUTH_PROVIDER=openid`

### Requirement: Config options are mapped to workload environment variables
The charm SHALL map `default_auth_provider` to `DEFAULT_AUTH_PROVIDER`, `ubuntu_one_openid_url` to `UBUNTU_ONE_OPENID_URL`, and the resolved realm to `UBUNTU_ONE_REALM` in the workload environment. `UBUNTU_ONE_REALM` SHALL be present only when a realm has been resolved.

#### Scenario: OpenID configuration reaches the workload
- **WHEN** the operator sets `default_auth_provider=openid` and `ubuntu_one_realm=https://sts.example.com`
- **THEN** the workload environment contains `DEFAULT_AUTH_PROVIDER=openid` and `UBUNTU_ONE_REALM=https://sts.example.com`

### Requirement: OpenID realm is derived from the ingress when not explicitly configured
When `default_auth_provider` is `openid` and `ubuntu_one_realm` is empty, the charm SHALL derive the realm from the ingress integration's external URL. An explicitly configured `ubuntu_one_realm` SHALL take precedence over the ingress-derived value.

#### Scenario: Realm derived from ingress external URL
- **WHEN** `default_auth_provider=openid`, `ubuntu_one_realm` is unset, and the ingress integration provides an external URL
- **THEN** the workload environment contains `UBUNTU_ONE_REALM` set to the ingress external URL

#### Scenario: Explicit realm takes precedence over ingress
- **WHEN** `ubuntu_one_realm=https://sts.example.com` is set and the ingress external URL is `https://other.example.com`
- **THEN** `UBUNTU_ONE_REALM=https://sts.example.com`

### Requirement: Unresolvable OpenID realm is surfaced to the operator
When `default_auth_provider` is `openid` and no realm can be resolved, the charm SHALL NOT start or reconfigure the workload with an empty realm. If no ingress integration exists, the unit SHALL enter `BlockedStatus` with a message explaining that `ubuntu_one_realm` or an ingress is required. If an ingress integration exists but has not yet published an external URL, the unit SHALL enter `WaitingStatus` until the URL is available.

#### Scenario: No realm and no ingress
- **WHEN** `default_auth_provider=openid`, `ubuntu_one_realm` is unset, and no `ingress` relation exists
- **THEN** the unit enters `BlockedStatus` explaining that `ubuntu_one_realm` or an ingress integration is required

#### Scenario: Ingress present but URL not yet published
- **WHEN** `default_auth_provider=openid`, `ubuntu_one_realm` is unset, the `ingress` relation exists, and no external URL has been published
- **THEN** the unit enters `WaitingStatus` and re-evaluates when the ingress publishes its external URL

### Requirement: OIDC provider never requires a realm
When `default_auth_provider` is `oidc`, the charm SHALL NOT require or derive a realm, regardless of whether `ubuntu_one_realm` or an ingress integration is present.

#### Scenario: Switching back to oidc without a realm
- **WHEN** the operator changes `default_auth_provider` from `openid` to `oidc` with `ubuntu_one_realm` unset and no ingress
- **THEN** the charm accepts the configuration and no realm validation applies
