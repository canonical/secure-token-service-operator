# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
import re
from typing import Optional

from ops.model import Container
from ops.pebble import Error, ExecError

from exceptions import MigrationError

logger = logging.getLogger(__name__)

VERSION_REGEX = re.compile(r"(v?\d+\.\d+\.\d+)")


class CommandLine:
    """A helper object for interacting with the Secure Token Service command line."""

    def __init__(self, container: Container) -> None:
        self.container = container

    def get_service_version(self) -> Optional[str]:
        """Get Secure Token Service application version."""
        cmd = ["/usr/bin/app", "version"]

        try:
            stdout, stderr = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to fetch the Secure Token Service version: %s", err)
            return None

        matched = VERSION_REGEX.search(stdout)
        return matched[0] if matched else None

    def check_migrations(self, dsn: str, timeout: float = 20, environment: Optional[dict] = None) -> bool:
        """Check if Secure Token Service database migrations are needed."""
        cmd = [
            "/usr/bin/app",
            "migrate",
            "check",
            "--database-url",
            dsn,
        ]

        try:
            self._run_cmd(cmd, timeout=timeout, environment=environment)
            logger.debug("Migration check passed. No migrations required.")
            return False
        except ExecError as err:
            logger.info("Migrations are pending (exit code %d).", err.exit_code)
            return True
        except Error as err:
            logger.error("Failed to execute migration check: %s", err)
            return True

    def migrate(self, dsn: str, timeout: float = 60, environment: Optional[dict] = None) -> None:
        """Apply Secure Token Service database migration.

        More info: https://github.com/canonical/secure-token-service/blob/main/README.md#step-3-run-database-migrations
        """
        cmd = [
            "/usr/bin/app",
            "migrate",
            "up",
            "--database-url",
            dsn,
        ]

        try:
            self._run_cmd(cmd, timeout=timeout, environment=environment)
        except Error as err:
            logger.error("Failed to migrate Secure Token Service: %s", err)
            raise MigrationError from err

    def _run_cmd(
        self,
        cmd: list[str],
        timeout: float = 20,
        environment: Optional[dict] = None,
    ) -> tuple[str, str]:
        logger.debug(f"Running command: {cmd}")
        process = self.container.exec(cmd, environment=environment, timeout=timeout)
        try:
            stdout, stderr = process.wait_output()
        except ExecError as err:
            logger.error("Exited with code: %d. Error: %s", err.exit_code, err.stderr)
            raise

        return (
            stdout.decode() if isinstance(stdout, bytes) else stdout,
            stderr.decode() if isinstance(stderr, bytes) else stderr,
        )
