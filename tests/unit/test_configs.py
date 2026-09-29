# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

from configs import CharmConfig


class TestCharmConfig:
    @patch("ops.model.ConfigData", autospec=True)
    def test_to_env_vars(self, mocked_class: MagicMock) -> None:
        mocked_config = mocked_class.return_value

        mocked_charm_data = {
            "log_level": "info",
            "http_proxy": "http://squid.internal:3128",
            "https_proxy": "http://squid.internal:3128",
            "no_proxy": "localhost,127.0.0.1,.svc.cluster.local",
        }

        mocked_config.__getitem__.side_effect = lambda key: mocked_charm_data[key]
        charm_config = CharmConfig(mocked_config)

        result = charm_config.to_env_vars()

        assert result == {
            "LOG_LEVEL": "info",
            "HTTP_PROXY": "http://squid.internal:3128",
            "HTTPS_PROXY": "http://squid.internal:3128",
            "NO_PROXY": "localhost,127.0.0.1,.svc.cluster.local",
        }
