## Problem

The `secure-token-service` workload gained Ubuntu One OpenID 2.0 support in https://github.com/canonical/secure-token-service/pull/43 (merged). The charm currently has no way to configure the new provider options, so a deployed unit always runs with the workload defaults and cannot enable or tune OpenID logins.

## Solution

Add three new charm config options that map to the workload's environment variables:

1. `default_auth_provider` (string, default `"oidc"`, validated to `"oidc"|"openid"`) → `DEFAULT_AUTH_PROVIDER`
2. `ubuntu_one_openid_url` (string, default `"https://login.ubuntu.com/+openid"`) → `UBUNTU_ONE_OPENID_URL`
3. `ubuntu_one_realm` (string, optional) → `UBUNTU_ONE_REALM`

When `default_auth_provider` is set to `"openid"` and `ubuntu_one_realm` is unset, the charm will attempt to derive the realm from the ingress integration's external URL. If no realm can be resolved, the unit enters blocked status with a clear message.

## Non-goals

- Changes to the `secure-token-service` workload itself (already merged upstream)
- Terraform module changes, unless the charm config is surfaced through them
- Cookie/security behavior — handled entirely by the workload

## Environmental updates

| Source | Destination | Purpose |
|--------|-------------|---------|
| charm config `default_auth_provider` | workload env `DEFAULT_AUTH_PROVIDER` | Sets default authentication provider |
| charm config `ubuntu_one_openid_url` | workload env `UBUNTU_ONE_OPENID_URL` | Ubuntu One OpenID endpoint |
| charm config `ubuntu_one_realm` (or derived from ingress) | workload env `UBUNTU_ONE_REALM` | OpenID realm/return_to base URL |

## Acceptance criteria

- `juju config secure-token-service default_auth_provider=openid` results in the workload running with `DEFAULT_AUTH_PROVIDER=openid`
- A unit configured for OpenID without a resolvable realm enters blocked status with an actionable message
- OIDC-only deployments (default config) are byte-identical in behavior to today
- All new code covered by unit tests; CI passes