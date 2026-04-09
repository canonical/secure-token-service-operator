# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops.pebble import Error, ExecError

from cli import CommandLine
from exceptions import MigrationError


class TestCommandLine:
    @pytest.fixture
    def command_line(self, mocked_container: MagicMock) -> CommandLine:
        return CommandLine(mocked_container)

    def test_get_service_version(self, command_line: CommandLine) -> None:
        expected = "v0.2.1"
        cmd_output = "Secure Token Service version v0.2.1"

        with patch.object(
            command_line,
            "_run_cmd",
            return_value=(cmd_output, ""),
        ) as run_cmd:
            actual = command_line.get_service_version()

            assert actual == expected
            run_cmd.assert_called_with(["/usr/bin/app", "version"])

    def test_get_service_version_error(self, command_line: CommandLine) -> None:
        with patch.object(
            command_line,
            "_run_cmd",
            side_effect=Error("Pebble connection failed"),
        ):
            actual = command_line.get_service_version()
            assert actual is None

    def test_check_migrations_success(self, command_line: CommandLine) -> None:
        dsn = "postgres://user:password@pg.internal/db"
        env = {"SOME_VAR": "value"}

        with patch.object(command_line, "_run_cmd") as run_cmd:
            result = command_line.check_migrations(dsn, timeout=30, environment=env)

        expected_cmd = [
            "/usr/bin/app",
            "migrate",
            "check",
            "--database-url",
            dsn,
        ]
        run_cmd.assert_called_once_with(expected_cmd, timeout=30, environment=env)

        assert result is False

    def test_check_migrations_pending(self, command_line: CommandLine) -> None:
        dsn = "postgres://user:password@pg.internal/db"

        with patch.object(
            command_line,
            "_run_cmd",
            side_effect=ExecError(command=["/usr/bin/app"], exit_code=1, stdout="", stderr="migrations pending")
        ):
            result = command_line.check_migrations(dsn)

        assert result is True

    def test_check_migrations_pebble_error(self, command_line: CommandLine) -> None:
        dsn = "postgres://user:password@pg.internal/db"

        with patch.object(
            command_line,
            "_run_cmd",
            side_effect=Error("Pebble connection lost")
        ):
            result = command_line.check_migrations(dsn)

        assert result is True

    def test_migrate_success(self, command_line: CommandLine) -> None:
        dsn = "postgres://user:password@pg.internal/db"
        env = {"SOME_VAR": "value"}

        with patch.object(command_line, "_run_cmd") as run_cmd:
            command_line.migrate(dsn, timeout=120, environment=env)

        expected_cmd = [
            "/usr/bin/app",
            "migrate",
            "up",
            "--database-url",
            dsn,
        ]
        run_cmd.assert_called_once_with(expected_cmd, timeout=120, environment=env)

    def test_migrate_failure(self, command_line: CommandLine) -> None:
        dsn = "postgres://user:password@pg.internal/db"

        with patch.object(
            command_line,
            "_run_cmd",
            side_effect=ExecError(command=["/usr/bin/app"], exit_code=1, stdout="", stderr="db connection failed")
        ):
            with pytest.raises(MigrationError):
                command_line.migrate(dsn)

    def test_run_cmd(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd, expected = ["cmd"], ("stdout", "")

        mocked_process = MagicMock(wait_output=MagicMock(return_value=expected))
        mocked_container.exec.return_value = mocked_process

        actual = command_line._run_cmd(cmd)

        assert actual == expected
        mocked_container.exec.assert_called_once_with(cmd, timeout=20, environment=None)

    def test_run_cmd_failed(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd = ["cmd"]

        mocked_process = MagicMock(wait_output=MagicMock(side_effect=ExecError(cmd, 1, "", "Command not found")))
        mocked_container.exec.return_value = mocked_process

        with pytest.raises(ExecError):
            command_line._run_cmd(cmd)
