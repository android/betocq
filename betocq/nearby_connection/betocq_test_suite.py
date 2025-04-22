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
2G AP (wifi_2g_ssid): channel 6 (2437)
5G AP (wifi_5g_ssid): channel 36 (5180)
DFS 5G AP(wifi_dfs_5g_ssid): channel 52 (5260)
"""

from mobly import base_suite
from mobly import suite_runner

from betocq import nc_constants
from betocq.nearby_connection.compound_tests import bt_2g_wifi_coex_test
from betocq.nearby_connection.compound_tests import mcc_5g_all_wifi_non_dbs_2g_sta_test
from betocq.nearby_connection.compound_tests import scc_2g_all_wifi_sta_test
from betocq.nearby_connection.compound_tests import scc_5g_all_wifi_dbs_2g_sta_test
from betocq.nearby_connection.compound_tests import scc_5g_all_wifi_sta_test
from betocq.nearby_connection.directed_tests import ble_performance_test
from betocq.nearby_connection.directed_tests import bt_performance_test
from betocq.nearby_connection.directed_tests import mcc_2g_wfd_indoor_5g_sta_test
from betocq.nearby_connection.directed_tests import mcc_5g_hotspot_dfs_5g_sta_test
from betocq.nearby_connection.directed_tests import mcc_5g_wfd_dfs_5g_sta_test
from betocq.nearby_connection.directed_tests import mcc_5g_wfd_non_dbs_2g_sta_test
from betocq.nearby_connection.directed_tests import mcc_aware_sta_test
from betocq.nearby_connection.directed_tests import scc_2g_wfd_sta_test
from betocq.nearby_connection.directed_tests import scc_2g_wlan_sta_test
from betocq.nearby_connection.directed_tests import scc_5g_aware_sta_test
from betocq.nearby_connection.directed_tests import scc_5g_wfd_dbs_2g_sta_test
from betocq.nearby_connection.directed_tests import scc_5g_wfd_sta_test
from betocq.nearby_connection.directed_tests import scc_5g_wlan_sta_test
from betocq.nearby_connection.directed_tests import scc_dfs_5g_hotspot_sta_test
from betocq.nearby_connection.directed_tests import scc_dfs_5g_wfd_sta_test
from betocq.nearby_connection.directed_tests import scc_indoor_5g_wfd_sta_test
from betocq.nearby_connection.function_tests import beto_cq_function_group_test


class BetoCqPerformanceTestSuite(base_suite.BaseSuite):
  """Add all BetoCQ tests to run in sequence."""

  def setup_suite(self, config):
    """Add all BetoCQ tests to the suite."""
    test_parameters = nc_constants.TestParameters.from_user_params(
        config.user_params
    )

    # Function tests cases.
    self.add_test_class(beto_cq_function_group_test.BetoCqFunctionGroupTest)

    # Directed test cases:
    self.add_test_class(bt_performance_test.BtPerformanceTest)
    self.add_test_class(mcc_2g_wfd_indoor_5g_sta_test.Mcc2gWfdIndoor5gStaTest)
    self.add_test_class(mcc_5g_hotspot_dfs_5g_sta_test.Mcc5gHotspotDfs5gStaTest)
    self.add_test_class(mcc_5g_wfd_dfs_5g_sta_test.Mcc5gWfdDfs5gStaTest)
    self.add_test_class(mcc_5g_wfd_non_dbs_2g_sta_test.Mcc5gWfdNonDbs2gStaTest)
    self.add_test_class(scc_2g_wfd_sta_test.Scc2gWfdStaTest)
    self.add_test_class(scc_2g_wlan_sta_test.Scc2gWlanStaTest)
    self.add_test_class(scc_5g_wfd_dbs_2g_sta_test.Scc5gWfdDbs2gStaTest)
    self.add_test_class(scc_5g_wfd_sta_test.Scc5gWfdStaTest)
    self.add_test_class(scc_5g_wlan_sta_test.Scc5gWifiLanStaTest)
    self.add_test_class(scc_dfs_5g_hotspot_sta_test.SccDfs5gHotspotStaTest)
    self.add_test_class(scc_dfs_5g_wfd_sta_test.SccDfs5gWfdStaTest)
    self.add_test_class(scc_indoor_5g_wfd_sta_test.SccIndoor5gWfdStaTest)
    # Optional Aware test cases that will be run only when explicitly selected:
    if test_parameters.run_aware_test:
      self.add_test_class(scc_5g_aware_sta_test.Scc5gAwareStaTest)
      self.add_test_class(mcc_aware_sta_test.MccAwareStaTest)

    # Optional BLE test cases that will be run only when explicitly selected:
    if test_parameters.run_ble_performance_test:
      self.add_test_class(ble_performance_test.BlePerformanceTest)

    # Compound test cases:
    self.add_test_class(bt_2g_wifi_coex_test.Bt2gWifiCoexTest)
    self.add_test_class(
        mcc_5g_all_wifi_non_dbs_2g_sta_test.Mcc5gAllWifiNonDbs2gStaTest
    )
    self.add_test_class(scc_2g_all_wifi_sta_test.Scc2gAllWifiStaTest)
    self.add_test_class(
        scc_5g_all_wifi_dbs_2g_sta_test.Scc5gAllWifiDbs2gStaTest
    )
    self.add_test_class(scc_5g_all_wifi_sta_test.Scc5gAllWifiStaTest)


if __name__ == '__main__':
  suite_runner.run_suite_class()
