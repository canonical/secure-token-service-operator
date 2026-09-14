## Purpose

This spec defines the `charms.secure_token_service.v0.sts_info` Juju charm library, which implements the `sts_ready` interface. The library enables STS charm deployments to advertise their HTTP/gRPC endpoints, JWKS URL, and TLS state to consuming charms via a Juju relation, and enables consuming charms to observe changes and read that data using Pydantic-validated models.

## Requirements

### Requirement: Library uses Pydantic v2 for data validation
The library SHALL define a `StsInfoData(pydantic.BaseModel)` model containing `http_address`, `grpc_address`, `jwks_url`, and `tls_enabled` fields. The provider SHALL use this model to serialize data before writing to the relation databag; the requirer SHALL use it to parse and validate data read from the databag.

#### Scenario: Invalid databag data raises validation error
- **WHEN** the `sts-info` relation databag contains data that fails Pydantic validation
- **THEN** `get_sts_info()` SHALL raise `StsInfoRelationDataMissingError`

### Requirement: Library provides StsInfoProvider class
The library SHALL expose a `StsInfoProvider` class that can be instantiated by the STS charm to advertise its endpoints over the `sts_ready` Juju interface on relation name `sts-info`.

#### Scenario: Provider emits sts_info_ready on relation created
- **WHEN** a new `sts-info` relation is created
- **THEN** `StsInfoProvider` SHALL emit the `sts_info_ready` custom event

#### Scenario: Only leader writes to databag
- **WHEN** `update_relations_app_data()` is called on a non-leader unit
- **THEN** the method SHALL return without writing to the relation databag

#### Scenario: Leader writes all fields to databag
- **WHEN** `update_relations_app_data()` is called on the leader unit with valid addresses
- **THEN** the relation databag SHALL contain `http_address`, `grpc_address`, `jwks_url`, and `tls_enabled` for every active `sts-info` relation

### Requirement: jwks_url is derived from http_address
The library SHALL set `jwks_url` to `<http_address>/.well-known/jwks.json`.

#### Scenario: jwks_url composed correctly
- **WHEN** `http_address` is `https://sts.example.com`
- **THEN** `jwks_url` SHALL be `https://sts.example.com/.well-known/jwks.json`

### Requirement: tls_enabled is a stringified boolean
The library SHALL store `tls_enabled` as the lowercase string `"true"` or `"false"` in the relation databag.

#### Scenario: tls_enabled reflects TLS state
- **WHEN** TLS is active (`tls_enabled=True` passed to `update_relations_app_data`)
- **THEN** the databag field `tls_enabled` SHALL be `"true"`

#### Scenario: tls_enabled defaults to false
- **WHEN** TLS is not active (`tls_enabled=False`)
- **THEN** the databag field `tls_enabled` SHALL be `"false"`

### Requirement: Library provides StsInfoRequirer class
The library SHALL expose a `StsInfoRequirer` class with an `is_ready()` method, a `get_sts_info()` method, a custom `sts_info_relation_updated` event for consuming charms to react to relation data changes, and a custom `sts_info_relation_broken` event emitted when the relation is removed.

#### Scenario: StsInfoRelationUpdatedEvent emitted on relation changed
- **WHEN** the `sts-info` relation databag is updated by the provider
- **THEN** `StsInfoRequirer` SHALL emit the `sts_info_relation_updated` custom event

#### Scenario: sts_info_relation_updated is a bare signal
- **WHEN** `sts_info_relation_updated` fires
- **THEN** it SHALL carry no additional data; consuming charms call `get_sts_info()` to obtain the current values

#### Scenario: StsInfoRelationBrokenEvent emitted on relation broken
- **WHEN** the `sts-info` relation is removed
- **THEN** `StsInfoRequirer` SHALL emit the `sts_info_relation_broken` custom event

#### Scenario: sts_info_relation_broken is a bare signal
- **WHEN** `sts_info_relation_broken` fires
- **THEN** it SHALL carry no additional data; consuming charms use it to react to loss of the STS integration

#### Scenario: get_sts_info returns data when relation is populated
- **WHEN** the `sts-info` relation databag contains all four fields
- **THEN** `get_sts_info()` SHALL return a `StsInfoData` instance with `http_address`, `grpc_address`, `jwks_url`, and `tls_enabled`

#### Scenario: get_sts_info raises on missing relation
- **WHEN** no `sts-info` relation exists
- **THEN** `get_sts_info()` SHALL raise `StsInfoRelationMissingError`

#### Scenario: get_sts_info raises on empty databag
- **WHEN** the relation exists but the databag is empty
- **THEN** `get_sts_info()` SHALL raise `StsInfoRelationDataMissingError`

### Requirement: is_ready returns correct readiness
The `StsInfoRequirer` SHALL expose an `is_ready()` boolean method.

#### Scenario: is_ready returns True when data is present
- **WHEN** the relation exists and the databag is populated
- **THEN** `is_ready()` SHALL return `True`

#### Scenario: is_ready returns False when data is absent
- **WHEN** no relation or empty databag
- **THEN** `is_ready()` SHALL return `False`
