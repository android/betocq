#  Copyright 2024 Google LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""This test suite batches all tests to run in sequence.

This requires 3 APs to be ready and configured in testbed.
2G AP (wifi_2g_ssid): channel 6 (2437) or other 2G channels.
5G AP (wifi_5g_ssid): channel 36 (5180) or other 5G Non-DFS channels.
5G DFS AP (wifi_dfs_5g_ssid): channel 52 (5260) or 112 (5560) or other DFS
channels.
"""

from mobly import asserts
from mobly import base_suite
from mobly import suite_runner

from betocq import constants
from betocq.nearby_connection.compound_tests import bt_2g_wifi_coex_test
from betocq.nearby_connection.directed_tests import bt_performance_test
from betocq.nearby_connection.directed_tests import scc_2g_wlan_sta_test
from betocq.nearby_connection.directed_tests import scc_5g_wfd_sta_test
from betocq.nearby_connection.directed_tests import scc_5g_wlan_sta_test
from betocq.nearby_connection.directed_tests import xcc_2g_wfd_sta_test
from betocq.nearby_connection.directed_tests import xcc_hotspot_dfs_5g_sta_test
from betocq.nearby_connection.directed_tests import xcc_wfd_dbs_2g_sta_test
from betocq.nearby_connection.directed_tests import xcc_wfd_dfs_5g_sta_test
from betocq.nearby_connection.directed_tests import xcc_wfd_ww_5g_sta_test
from betocq.nearby_connection.function_tests import beto_cq_function_group_test


_SUITE_NAME = 'AQT'
# increment this version number when adding new tests or changing the config
# parameters of existing tests.
# LINT.IfChange(suite_version)
_SUITE_VERSION = '9'
# LINT.ThenChange()


# Test for GTS AQT.
# LINT.IfChange
class BetoCqAqtTestSuite(base_suite.BaseSuite):
  """Add all BetoCQ tests to run in sequence."""

  def _assert_config_parameters(self, config):
    """Assert that the config parameters are set correctly."""
    if config is None or not hasattr(config, 'user_params'):
      return
    test_params = constants.TestParameters.from_user_params(
        config.user_params
    )
    if (not test_params.target_cuj_name
        or test_params.target_cuj_name == constants.TARGET_CUJ_UNSET):
      return
    asserts.abort_all_if(
        test_params.target_cuj_name
        != constants.TARGET_CUJ_AQT,
        'target_cuj_name is not aqt',
    )
    if not test_params.use_programmable_ap:
      asserts.abort_all_if(
          not test_params.wifi_2g_ssid, 'wifi_2g_ssid is not set'
      )
      asserts.abort_all_if(
          not test_params.wifi_5g_ssid, 'wifi_5g_ssid is not set'
      )
      asserts.abort_all_if(
          not test_params.wifi_dfs_5g_ssid, 'wifi_dfs_5g_ssid is not set'
      )

    asserts.abort_all_if(
        test_params.skip_default_flag_override,
        'do not change testbed parameters, skip_default_flag_override is'
        ' expected to be False',
    )

  def setup_suite(self, config):
    """Add all BetoCQ tests to the suite."""
    self.user_params['suite_name'] = _SUITE_NAME
    self.user_params['suite_version'] = _SUITE_VERSION

    # Function tests cases.
    self.add_test_class(beto_cq_function_group_test.BetoCqFunctionGroupTest)
    # Directed test cases:
    self.add_test_class(bt_performance_test.BtPerformanceTest)
    # 5G STA
    self.add_test_class(scc_5g_wfd_sta_test.Scc5gWfdStaTest)
    self.add_test_class(scc_5g_wlan_sta_test.Scc5gWifiLanStaTest)
    # 5G DFS STA
    self.add_test_class(xcc_wfd_dfs_5g_sta_test.XccWfdDfs5gStaTest)
    # 2G STA
    self.add_test_class(scc_2g_wlan_sta_test.Scc2gWlanStaTest)
    self.add_test_class(xcc_wfd_dbs_2g_sta_test.XccWfdDbs2gStaTest)
    # Compound test cases:
    self.add_test_class(bt_2g_wifi_coex_test.Bt2gWifiCoexTest)

    self._assert_config_parameters(config)
# LINT.ThenChange(:suite_version)


def main() -> None:
  """Entry point for execution as pip installed script."""
  suite_runner.run_suite_class()


if __name__ == '__main__':
  main()
