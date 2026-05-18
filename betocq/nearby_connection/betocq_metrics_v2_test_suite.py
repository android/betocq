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

"""Test suite for metrics v2 validation."""

from mobly import base_suite
from mobly import suite_runner

from betocq.nearby_connection.directed_tests import ble_performance_test
from betocq.nearby_connection.directed_tests import bt_performance_test
from betocq.nearby_connection.directed_tests import local_only_hotspot_test
from betocq.nearby_connection.directed_tests import mcc_2g_wfd_ww_5g_sta_test
from betocq.nearby_connection.directed_tests import mcc_5g_hotspot_dfs_5g_sta_test
from betocq.nearby_connection.directed_tests import mcc_5g_wfd_dfs_5g_sta_test
from betocq.nearby_connection.directed_tests import mcc_5g_wfd_non_dbs_2g_sta_test
from betocq.nearby_connection.directed_tests import mcc_aware_sta_test


class BetocqMetricsV2TestSuite(base_suite.BaseSuite):
  """BetoCQ V2 metrics tests to run in sequence."""

  def setup_suite(self, config):
    """Add tests to the suite."""
    self.add_test_class(
        ble_performance_test.BlePerformanceTest,
        name_suffix='nc',
    )
    self.add_test_class(
        bt_performance_test.BtPerformanceTest,
        name_suffix='nc',
    )
    self.add_test_class(
        local_only_hotspot_test.LocalOnlyHotspotTest,
        name_suffix='nc',
    )
    self.add_test_class(
        mcc_aware_sta_test.MccAwareStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        mcc_5g_hotspot_dfs_5g_sta_test.Mcc5gHotspotDfs5gStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        mcc_5g_wfd_dfs_5g_sta_test.Mcc5gWfdDfs5gStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        mcc_5g_wfd_non_dbs_2g_sta_test.Mcc5gWfdNonDbs2gStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        mcc_2g_wfd_ww_5g_sta_test.Mcc2gWfdWw5gStaTest,
        name_suffix='nc',
    )


def main() -> None:
  suite_runner.run_suite_class()


if __name__ == '__main__':
  main()
