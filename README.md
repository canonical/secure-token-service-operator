# Charmed Secure Token Service (STS)

[![CharmHub Badge](https://charmhub.io/sts/badge.svg)](https://charmhub.io/secure-token-service)
[![Juju](https://img.shields.io/badge/Juju%20-3.0+-%23E95420)](https://github.com/juju/juju)
[![License](https://img.shields.io/github/license/canonical/secure-token-service-operator?label=License)](https://github.com/canonical/secure-token-service-operator/blob/main/LICENSE)

[![Continuous Integration Status](https://github.com/canonical/secure-token-service-operator/actions/workflows/on_push.yaml/badge.svg?branch=main)](https://github.com/canonical/secure-token-service-operator/actions?query=branch%3Amain)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196.svg)](https://conventionalcommits.org)

## Description

This repository hosts the Kubernetes Python Operator for the Secure Token Service (STS) - Janus.
It is a Policy Enforcement Point (PEP) and Security Token Service (STS) that sits between external clients and internal microservices.
Refer to the [STS documentation](https://github.com/canonical/secure-token-service) for more details and architectural overview.

## Usage

Once published the Secure Token Service Operator may be deployed using the Juju commandline as follows:

```shell
juju deploy secure-token-service --channel=latest/edge --trust
```

### Interacting with STS API

Once the service is deployed and accessible, you can interact with the STS API as documented [here](https://github.com/canonical/secure-token-service?tab=readme-ov-file#api-reference).

## Configuration

<!-- TBD -->

## Integrations

<!-- TBD -->

## Actions

<!-- TBD -->

## OCI Images

<!-- TBD -->

## Security

<!-- Please see [SECURITY.md](https://github.com/canonical/secure-token-service-operator/blob/main/SECURITY.md) for guidelines on reporting security issues. -->

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this charm following best practice guidelines, and [CONTRIBUTING.md](https://github.com/canonical/secure-token-service-operator/blob/main/CONTRIBUTING.md) for developer guidance.

## License

The Charmed Secure Token Service Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](https://github.com/canonical/secure-token-service-operator/blob/main/LICENSE) for more information.
