# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the sts_info charm library."""

from typing import Any

import pytest
from charms.secure_token_service.v0.sts_info import (
    RELATION_NAME,
    StsInfoData,
    StsInfoProvider,
    StsInfoRelationBrokenEvent,
    StsInfoRelationDataMissingError,
    StsInfoRelationMissingError,
    StsInfoRelationUpdatedEvent,
    StsInfoRequirer,
)
from ops import CharmBase, testing

PROVIDER_META: dict[str, Any] = {
    "name": "provider-charm",
    "provides": {RELATION_NAME: {"interface": "sts_info"}},
}
REQUIRER_META: dict[str, Any] = {
    "name": "requirer-charm",
    "requires": {RELATION_NAME: {"interface": "sts_info"}},
}

HTTP_ADDRESS = "https://sts.example.com"
GRPC_ADDRESS = "sts.testing.svc.cluster.local:9090"


class _ProviderCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.sts_info = StsInfoProvider(self)


class _RequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.sts_info = StsInfoRequirer(self)
        self.framework.observe(
            self.sts_info.on.sts_info_relation_updated,
            self._on_sts_info_relation_updated,
        )
        self.framework.observe(
            self.sts_info.on.sts_info_relation_broken,
            self._on_sts_info_relation_broken,
        )

    def _on_sts_info_relation_updated(self, event: StsInfoRelationUpdatedEvent) -> None:
        pass

    def _on_sts_info_relation_broken(self, event: StsInfoRelationBrokenEvent) -> None:
        pass


class TestStsInfoProvider:
    def test_sts_info_ready_emitted_on_relation_created(self) -> None:
        ctx = testing.Context(_ProviderCharm, meta=PROVIDER_META)
        relation = testing.Relation(endpoint=RELATION_NAME)
        state_in = testing.State(relations=[relation], leader=True)

        ctx.run(ctx.on.relation_created(relation), state_in)

        events_fired = [type(e).__name__ for e in ctx.emitted_events]
        assert "StsInfoRelationReadyEvent" in events_fired

    def test_leader_writes_all_fields_to_databag(self) -> None:
        ctx = testing.Context(_ProviderCharm, meta=PROVIDER_META)
        relation = testing.Relation(endpoint=RELATION_NAME)
        state_in = testing.State(relations=[relation], leader=True)

        def handler(charm: _ProviderCharm) -> None:
            charm.sts_info.update_relations_app_data(
                http_address=HTTP_ADDRESS,
                grpc_address=GRPC_ADDRESS,
                tls_enabled=True,
            )

        with ctx(ctx.on.relation_created(relation), state_in) as mgr:
            handler(mgr.charm)
            state_out = mgr.run()

        rel_out = state_out.get_relation(relation.id)
        assert rel_out.local_app_data["http_address"] == HTTP_ADDRESS
        assert rel_out.local_app_data["grpc_address"] == GRPC_ADDRESS
        assert rel_out.local_app_data["jwks_url"] == f"{HTTP_ADDRESS}/.well-known/jwks.json"
        assert rel_out.local_app_data["tls_enabled"] == "true"

    def test_non_leader_does_not_write_to_databag(self) -> None:
        ctx = testing.Context(_ProviderCharm, meta=PROVIDER_META)
        relation = testing.Relation(endpoint=RELATION_NAME)
        state_in = testing.State(relations=[relation], leader=False)

        with ctx(ctx.on.relation_created(relation), state_in) as mgr:
            mgr.charm.sts_info.update_relations_app_data(
                http_address=HTTP_ADDRESS,
                grpc_address=GRPC_ADDRESS,
                tls_enabled=False,
            )
            state_out = mgr.run()

        rel_out = state_out.get_relation(relation.id)
        assert rel_out.local_app_data == {}

    def test_jwks_url_strips_trailing_slash(self) -> None:
        ctx = testing.Context(_ProviderCharm, meta=PROVIDER_META)
        relation = testing.Relation(endpoint=RELATION_NAME)
        state_in = testing.State(relations=[relation], leader=True)

        with ctx(ctx.on.relation_created(relation), state_in) as mgr:
            mgr.charm.sts_info.update_relations_app_data(
                http_address="https://sts.example.com/",
                grpc_address=GRPC_ADDRESS,
                tls_enabled=False,
            )
            state_out = mgr.run()

        rel_out = state_out.get_relation(relation.id)
        assert (
            rel_out.local_app_data["jwks_url"] == "https://sts.example.com/.well-known/jwks.json"
        )

    def test_tls_enabled_false_stored_as_string(self) -> None:
        ctx = testing.Context(_ProviderCharm, meta=PROVIDER_META)
        relation = testing.Relation(endpoint=RELATION_NAME)
        state_in = testing.State(relations=[relation], leader=True)

        with ctx(ctx.on.relation_created(relation), state_in) as mgr:
            mgr.charm.sts_info.update_relations_app_data(
                http_address=HTTP_ADDRESS,
                grpc_address=GRPC_ADDRESS,
                tls_enabled=False,
            )
            state_out = mgr.run()

        rel_out = state_out.get_relation(relation.id)
        assert rel_out.local_app_data["tls_enabled"] == "false"

    def test_writes_to_multiple_relations(self) -> None:
        ctx = testing.Context(_ProviderCharm, meta=PROVIDER_META)
        rel1 = testing.Relation(endpoint=RELATION_NAME, id=1)
        rel2 = testing.Relation(endpoint=RELATION_NAME, id=2)
        state_in = testing.State(relations=[rel1, rel2], leader=True)

        with ctx(ctx.on.relation_created(rel1), state_in) as mgr:
            mgr.charm.sts_info.update_relations_app_data(
                http_address=HTTP_ADDRESS,
                grpc_address=GRPC_ADDRESS,
                tls_enabled=False,
            )
            state_out = mgr.run()

        for rel in [rel1, rel2]:
            rel_out = state_out.get_relation(rel.id)
            assert rel_out.local_app_data["http_address"] == HTTP_ADDRESS


class TestStsInfoRequirer:
    def _populated_databag(self) -> dict[str, str]:
        return {
            "http_address": HTTP_ADDRESS,
            "grpc_address": GRPC_ADDRESS,
            "jwks_url": f"{HTTP_ADDRESS}/.well-known/jwks.json",
            "tls_enabled": "true",
        }

    def test_get_sts_info_returns_data_when_populated(self) -> None:
        ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
        relation = testing.Relation(
            endpoint=RELATION_NAME,
            remote_app_data=self._populated_databag(),
        )
        state_in = testing.State(relations=[relation], leader=True)

        with ctx(ctx.on.relation_changed(relation), state_in) as mgr:
            data = mgr.charm.sts_info.get_sts_info()

        assert isinstance(data, StsInfoData)
        assert data.http_address == HTTP_ADDRESS
        assert data.grpc_address == GRPC_ADDRESS
        assert data.jwks_url == f"{HTTP_ADDRESS}/.well-known/jwks.json"
        assert data.tls_enabled is True

    def test_get_sts_info_raises_when_no_relation(self) -> None:
        ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
        state_in = testing.State(leader=True)

        with ctx(ctx.on.config_changed(), state_in) as mgr:
            with pytest.raises(StsInfoRelationMissingError):
                mgr.charm.sts_info.get_sts_info()

    def test_get_sts_info_raises_when_databag_empty(self) -> None:
        ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
        relation = testing.Relation(endpoint=RELATION_NAME, remote_app_data={})
        state_in = testing.State(relations=[relation], leader=True)

        with ctx(ctx.on.relation_changed(relation), state_in) as mgr:
            with pytest.raises(StsInfoRelationDataMissingError):
                mgr.charm.sts_info.get_sts_info()

    def test_get_sts_info_raises_when_databag_incomplete(self) -> None:
        ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
        relation = testing.Relation(
            endpoint=RELATION_NAME,
            remote_app_data={"http_address": HTTP_ADDRESS},
        )
        state_in = testing.State(relations=[relation], leader=True)

        with ctx(ctx.on.relation_changed(relation), state_in) as mgr:
            with pytest.raises(StsInfoRelationDataMissingError):
                mgr.charm.sts_info.get_sts_info()

    def test_sts_info_relation_updated_emitted_on_relation_changed(self) -> None:
        ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
        relation = testing.Relation(
            endpoint=RELATION_NAME,
            remote_app_data=self._populated_databag(),
        )
        state_in = testing.State(relations=[relation], leader=True)

        ctx.run(ctx.on.relation_changed(relation), state_in)

        events_fired = [type(e).__name__ for e in ctx.emitted_events]
        assert "StsInfoRelationUpdatedEvent" in events_fired

    def test_sts_info_relation_broken_emitted_on_relation_broken(self) -> None:
        ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
        relation = testing.Relation(
            endpoint=RELATION_NAME,
            remote_app_data=self._populated_databag(),
        )
        state_in = testing.State(relations=[relation], leader=True)

        ctx.run(ctx.on.relation_broken(relation), state_in)

        events_fired = [type(e).__name__ for e in ctx.emitted_events]
        assert "StsInfoRelationBrokenEvent" in events_fired

    def test_is_ready_returns_true_when_data_present(self) -> None:
        ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
        relation = testing.Relation(
            endpoint=RELATION_NAME,
            remote_app_data=self._populated_databag(),
        )
        state_in = testing.State(relations=[relation], leader=True)

        with ctx(ctx.on.relation_changed(relation), state_in) as mgr:
            assert mgr.charm.sts_info.is_ready() is True

    def test_is_ready_returns_false_when_no_relation(self) -> None:
        ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
        state_in = testing.State(leader=True)

        with ctx(ctx.on.config_changed(), state_in) as mgr:
            assert mgr.charm.sts_info.is_ready() is False

    def test_is_ready_returns_false_when_databag_incomplete(self) -> None:
        ctx = testing.Context(_RequirerCharm, meta=REQUIRER_META)
        relation = testing.Relation(
            endpoint=RELATION_NAME,
            remote_app_data={"http_address": HTTP_ADDRESS},
        )
        state_in = testing.State(relations=[relation], leader=True)

        with ctx(ctx.on.relation_changed(relation), state_in) as mgr:
            assert mgr.charm.sts_info.is_ready() is False
