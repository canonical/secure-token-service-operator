# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from conftest import create_state
from ops import testing

from charm import SecureTokenServiceCharm
from exceptions import MigrationError


class TestRunMigrationAction:
    def test_when_not_leader_unit(
        self,
        peer_integration: testing.PeerRelation,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=False,
            relations=[peer_integration],
            leader=False,
        )

        with pytest.raises(
            testing.ActionFailed, match="Only the leader unit can run the database migration"
        ):
            ctx.run(ctx.on.action(name="run-migration"), state_in)

    def test_when_container_not_connected(
        self,
        peer_integration: testing.PeerRelation,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=False,
            relations=[peer_integration],
            leader=True,
        )

        with pytest.raises(testing.ActionFailed, match="Container is not connected yet"):
            ctx.run(ctx.on.action(name="run-migration"), state_in)

    def test_when_no_peer_integration(self) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(can_connect=True, leader=True)

        with pytest.raises(testing.ActionFailed, match="Peer integration is not ready"):
            ctx.run(ctx.on.action(name="run-migration"), state_in)

    @patch("charm.CommandLine.migrate", side_effect=MigrationError("simulated error"))
    def test_when_commandline_failed(
        self,
        mocked_cli: MagicMock,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[peer_integration, database_integration],
            leader=True,
        )

        with pytest.raises(testing.ActionFailed, match="Database migration failed: simulated error"):
            ctx.run(ctx.on.action(name="run-migration", params={"timeout": 120}), state_in)

        dsn = "postgres://sts_user:sts_password@pg.internal:5432/testing_secure-token-service"
        mocked_cli.assert_called_once_with(dsn=dsn, timeout=120.0)

    @patch("charm.CommandLine.migrate")
    def test_when_action_succeeds(
        self,
        mocked_cli: MagicMock,
        peer_integration: testing.PeerRelation,
        database_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(SecureTokenServiceCharm)
        state_in = create_state(
            can_connect=True,
            relations=[peer_integration, database_integration],
            leader=True,
        )

        ctx.run(ctx.on.action(name="run-migration"), state_in)

        assert "Started migrating the database" in ctx.action_logs
        assert "Successfully migrated the database" in ctx.action_logs

        dsn = "postgres://sts_user:sts_password@pg.internal:5432/testing_secure-token-service"
        mocked_cli.assert_called_once_with(dsn=dsn, timeout=120)
