## Purpose

This specification defines the functional requirements and behavior for integrating the Secure Token Service (STS) Operator with the Charmed Valkey Operator (or compatible Redis/Valkey providers) via the `valkey_client` (v1) interface using `dpcharmlibs-interfaces==1.2.2`. It replaces manual Juju configuration with automated, mandatory endpoint discovery, access control provisioning, and secure credential handling.

## Requirements

### Requirement: Mandatory cache relation endpoint declaration
The charm SHALL declare a mandatory client requirement endpoint named `cache` with interface `valkey_client`, `optional: false`, and `limit: 1` in `charmcraft.yaml`.

#### Scenario: Inspecting charm metadata
- **WHEN** the charm metadata is inspected
- **THEN** the `cache` relation requirement is present with interface `valkey_client`, `optional: false`, and a maximum limit of 1

### Requirement: Automated cache credential and endpoint discovery via dpcharmlibs-interfaces
The charm SHALL request global keyspace access (`resource="*"`) from the Valkey provider using `dpcharmlibs-interfaces==1.2.2` (`ResourceRequirerEventHandler`, `RequirerCommonModel`, `ValkeyResponseModel`) when related and dynamically retrieve connection endpoints and credentials through relation data and Juju secrets.

#### Scenario: Successful integration with Valkey operator
- **WHEN** the `cache` relation is established with a Valkey provider charm and credentials are ready
- **THEN** the charm extracts the primary write endpoint, username, and password from the relation

#### Scenario: Waiting for cache credentials
- **WHEN** the `cache` relation is established but credentials or endpoints have not been published by the provider
- **THEN** the charm enters `WaitingStatus("Waiting for cache creation")`

### Requirement: Workload environment variable provisioning
The charm SHALL map the discovered Valkey credentials and primary endpoint to the container environment variables `CACHE_ADDR`, `CACHE_USERNAME`, and `CACHE_PASSWORD` when the `cache` relation is active and populated, relying on the workload's internal default ("0") for database index selection.

#### Scenario: Pebble layer configuration with cache parameters
- **WHEN** valid Valkey relation data is available during Pebble layer rendering
- **THEN** `CACHE_ADDR` is set to the primary write endpoint, `CACHE_USERNAME` to the relation username, and `CACHE_PASSWORD` to the relation password

### Requirement: Mandatory relation prerequisite validation
The charm SHALL require the `cache` integration and enter `BlockedStatus` when missing, and SHALL guard against incomplete credentials when the relation exists.

#### Scenario: Missing cache integration
- **WHEN** no relation is established on the `cache` endpoint
- **THEN** the charm enters `BlockedStatus("Missing cache integration")`

#### Scenario: Cache relation is broken or removed
- **WHEN** an established `cache` relation is removed or broken
- **THEN** the charm enters `BlockedStatus("Missing cache integration")`

### Requirement: Dynamic credential rotation and endpoint updates
The charm SHALL react to endpoint updates and credential rotation events by re-rendering the Pebble layer and updating the running workload.

#### Scenario: Valkey updates endpoints or credentials
- **WHEN** the Valkey provider emits relation updated or secret changed events with updated connection details
- **THEN** the charm triggers reconciliation, updates the Pebble configuration, and replans the workload service

### Requirement: Cache relation status inspection and propagation
The charm SHALL inspect provider relation statuses via `get_statuses()` on the Valkey interface and propagate fatal errors as `BlockedStatus` and transitory conditions as `WaitingStatus`, and SHALL observe `status_raised` and `status_resolved` events to trigger reconciliation.

#### Scenario: Fatal provider status
- **WHEN** the Valkey provider publishes a fatal status (`rel_status.is_fatal`)
- **THEN** the charm enters `BlockedStatus(f"Cache error: {rel_status.message}")`

#### Scenario: Transitory provider status
- **WHEN** the Valkey provider publishes a transitory status (`rel_status.is_transitory`)
- **THEN** the charm enters `WaitingStatus(f"Cache: {rel_status.message}")`

#### Scenario: Status event handling
- **WHEN** the Valkey provider raises or resolves a relation status
- **THEN** the charm triggers holistic reconciliation to re-evaluate prerequisites and update unit status
