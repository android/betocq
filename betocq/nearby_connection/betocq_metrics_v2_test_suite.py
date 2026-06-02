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

from betocq.nearby_connection.directed_tests import scc_2g_wfd_sta_test
from betocq.nearby_connection.directed_tests import scc_2g_wlan_sta_test
from betocq.nearby_connection.directed_tests import scc_5g_aware_sta_test
from betocq.nearby_connection.directed_tests import scc_5g_wfd_dbs_2g_sta_test
from betocq.nearby_connection.directed_tests import scc_5g_wfd_sta_test
from betocq.nearby_connection.directed_tests import scc_5g_wlan_sta_test
from betocq.nearby_connection.directed_tests import scc_dfs_5g_hotspot_sta_test
from betocq.nearby_connection.directed_tests import scc_dfs_5g_wfd_sta_test
from betocq.nearby_connection.directed_tests import scc_indoor_5g_wfd_sta_test


class BetocqMetricsV2TestSuite(base_suite.BaseSuite):
  """BetoCQ V2 metrics tests to run in sequence."""

  def setup_suite(self, config):
    """Add tests to the suite."""
    self.add_test_class(
        scc_2g_wfd_sta_test.Scc2gWfdStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        scc_2g_wlan_sta_test.Scc2gWlanStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        scc_5g_aware_sta_test.Scc5gAwareStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        scc_5g_wfd_dbs_2g_sta_test.Scc5gWfdDbs2gStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        scc_5g_wfd_sta_test.Scc5gWfdStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        scc_5g_wlan_sta_test.Scc5gWifiLanStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        scc_dfs_5g_hotspot_sta_test.SccDfs5gHotspotStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        scc_dfs_5g_wfd_sta_test.SccDfs5gWfdStaTest,
        name_suffix='nc',
    )
    self.add_test_class(
        scc_indoor_5g_wfd_sta_test.SccIndoor5gWfdStaTest,
        name_suffix='nc',
    )


def main() -> None:
  suite_runner.run_suite_class()


if __name__ == '__main__':
  main()
