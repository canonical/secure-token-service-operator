## Purpose

This spec defines how the STS charm determines its publicly accessible HTTP address and how it keeps the `sts-info` relation databags current. The charm prefers the external URL from an active Istio ingress relation and falls back to the Kubernetes service address. Whenever the ingress configuration changes the charm refreshes all active `sts-info` relations by calling `update_relations_app_data()`.

## Requirements

### Requirement: Charm wires StsInfoProvider and handles sts_info_ready
The STS charm SHALL instantiate `StsInfoProvider` and observe `sts_info_ready` to call `update_relations_app_data()`.

#### Scenario: update_relations_app_data called on sts_info_ready
- **WHEN** a new `sts-info` relation is created and `sts_info_ready` fires
- **THEN** the charm SHALL call `update_relations_app_data()` with the current HTTP address, gRPC address, and TLS state

### Requirement: Charm uses k8s svc address when no ingress is present
The charm SHALL derive the default HTTP address as `http://<app-name>.<model-name>.svc.cluster.local:<STS_HTTP_PORT>` when no Istio ingress relation provides an external URL.

#### Scenario: Default address used without ingress
- **WHEN** no `ingress` relation is active
- **THEN** `http_address` SHALL be the k8s service URL and `tls_enabled` SHALL be `False`

### Requirement: Charm uses ingress external URL when ingress is present
The charm SHALL use `IstioIngressIntegration.external_url` as the `http_address` when an ingress relation is active and the external host is set.

#### Scenario: Ingress URL used when available
- **WHEN** an `ingress` relation is active and `external_url` is set
- **THEN** `http_address` SHALL be the ingress URL and `tls_enabled` SHALL reflect `requirer.tls_enabled`

### Requirement: Charm refreshes relation databag on ingress_ready
The charm's `_on_ingress_ready` handler SHALL call `update_relations_app_data()` so that any existing `sts-info` relations are updated when the external URL changes.

#### Scenario: Databag refreshed when ingress URL changes
- **WHEN** the `ingress_ready` event fires with a new external URL
- **THEN** all active `sts-info` relation databags SHALL be updated with the new `http_address` and `jwks_url`

### Requirement: grpc_address is always the k8s svc address at port 9090
The gRPC address SHALL always be `<app-name>.<model-name>.svc.cluster.local:9090` regardless of ingress configuration.

#### Scenario: grpc_address is k8s svc
- **WHEN** `update_relations_app_data()` is called with or without ingress
- **THEN** `grpc_address` SHALL be `<app-name>.<model-name>.svc.cluster.local:9090`
