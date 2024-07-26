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

import sys

from mobly import suite_runner

from betocq import base_betocq_suite
from betocq import nc_constants
from betocq.compound_tests import bt_2g_wifi_coex_test
from betocq.compound_tests import mcc_5g_all_wifi_non_dbs_2g_sta_test
from betocq.compound_tests import scc_2g_all_wifi_sta_test
from betocq.compound_tests import scc_5g_all_wifi_dbs_2g_sta_test
from betocq.compound_tests import scc_5g_all_wifi_sta_test
from betocq.directed_tests import ble_performance_test
from betocq.directed_tests import bt_performance_test
from betocq.directed_tests import mcc_2g_wfd_indoor_5g_sta_test
from betocq.directed_tests import mcc_5g_hotspot_dfs_5g_sta_test
from betocq.directed_tests import mcc_5g_wfd_dfs_5g_sta_test
from betocq.directed_tests import mcc_5g_wfd_non_dbs_2g_sta_test
from betocq.directed_tests import mcc_aware_sta_test
from betocq.directed_tests import scc_2g_wfd_sta_test
from betocq.directed_tests import scc_2g_wlan_sta_test
from betocq.directed_tests import scc_5g_aware_sta_test
from betocq.directed_tests import scc_5g_wfd_dbs_2g_sta_test
from betocq.directed_tests import scc_5g_wfd_sta_test
from betocq.directed_tests import scc_5g_wlan_sta_test
from betocq.directed_tests import scc_dfs_5g_hotspot_sta_test
from betocq.directed_tests import scc_dfs_5g_wfd_sta_test
from betocq.directed_tests import scc_indoor_5g_wfd_sta_test
from betocq.function_tests import beto_cq_function_group_test
from betocq.function_tests import nearbyconnections_function_test


class BetoCqPerformanceTestSuite(base_betocq_suite.BaseBetocqSuite):
  """Add all BetoCQ tests to run in sequence."""

  # pylint: disable=line-too-long
  def __init__(self, runner, config):
    super().__init__(runner, config)
    self._enabled_test_classes = {}

  def enable_test_class(self, clazz, config=None):
    """Enable the test class within the suite.

    Once enabled, the test class will run if the user selects it explicitly from
    the command line, or by default if no user selection is made.

    Args:
      clazz: class, a Mobly test class.
      config: config_parser.TestRunConfig, the config to run the class with. If
        not specified, the loaded config file is used as is.
    """
    self._enabled_test_classes[clazz] = config

  def add_enabled_test_classes_from_selection(self):
    """Add enabled test classes to run, based on the user selection."""
    test_selector = suite_runner._parse_cli_args(None).tests
    selected_tests = suite_runner.compute_selected_tests(
        self._enabled_test_classes.keys(), test_selector
    )
    for test_class, tests in selected_tests.items():
      self.add_test_class( # DO_NOT_TRANSFORM
          test_class, config=self._enabled_test_classes[test_class], tests=tests
      )
  # pylint: enable=line-too-long

  def setup_suite(self, config):
    """Add all BetoCQ tests to the suite."""
    test_parameters = nc_constants.TestParameters.from_user_params(
        config.user_params
    )
    config = self._config.copy()
    config.user_params['wifi_channel'] = nc_constants.CHANNEL_2G

    if test_parameters.target_cuj_name == nc_constants.TARGET_CUJ_ESIM:
      self.enable_test_class(
          clazz=bt_performance_test.BtPerformanceTest,
          config=config,
      )
      return

    # add function tests if required
    if (
        test_parameters.run_function_tests_with_performance_tests
        or test_parameters.use_auto_controlled_wifi_ap
    ):
      self.enable_test_class(
          beto_cq_function_group_test.BetoCqFunctionGroupTest,
          config=config,
      )

    # add nearby connections function tests if required
    if test_parameters.run_nearby_connections_function_tests:
      self.enable_test_class(
          clazz=nearbyconnections_function_test.NearbyConnectionsFunctionTest,
          config=config,
      )

    if test_parameters.run_bt_coex_test:
      self.enable_test_class(
          clazz=bt_2g_wifi_coex_test.Bt2gWifiCoexTest,
          config=config,
      )

    # add bt and ble test
    if test_parameters.run_bt_performance_test:
      self.enable_test_class(
          clazz=bt_performance_test.BtPerformanceTest,
          config=config,
      )

    if test_parameters.run_ble_performance_test:
      self.enable_test_class(
          clazz=ble_performance_test.BlePerformanceTest,
          config=config,
      )

    # add directed/cuj tests which requires 2G wlan AP
    if (
        test_parameters.wifi_2g_ssid
        or test_parameters.use_auto_controlled_wifi_ap
    ):

      if test_parameters.run_directed_test:
        self.enable_test_class(
            clazz=mcc_5g_wfd_non_dbs_2g_sta_test.Mcc5gWfdNonDbs2gStaTest,
            config=config,
        )
        self.enable_test_class(
            clazz=scc_2g_wfd_sta_test.Scc2gWfdStaTest,
            config=config,
        )
        self.enable_test_class(
            clazz=scc_2g_wlan_sta_test.Scc2gWlanStaTest,
            config=config,
        )
        self.enable_test_class(
            clazz=scc_5g_wfd_dbs_2g_sta_test.Scc5gWfdDbs2gStaTest,
            config=config,
        )
      if test_parameters.run_compound_test:
        self.enable_test_class(
            clazz=mcc_5g_all_wifi_non_dbs_2g_sta_test.Mcc5gAllWifiNonDbs2gStaTest,
            config=config,
        )
        self.enable_test_class(
            clazz=scc_2g_all_wifi_sta_test.Scc2gAllWifiStaTest,
            config=config,
        )
        self.enable_test_class(
            clazz=scc_5g_all_wifi_dbs_2g_sta_test.Scc5gAllWifiDbs2gStaTest,
            config=config,
        )

    # add directed tests which requires 5G wlan AP
    if (
        test_parameters.wifi_5g_ssid
        or test_parameters.use_auto_controlled_wifi_ap
    ):
      config = self._config.copy()
      config.user_params['wifi_channel'] = nc_constants.CHANNEL_5G

      if test_parameters.run_directed_test:
        self.enable_test_class(
            clazz=mcc_2g_wfd_indoor_5g_sta_test.Mcc2gWfdIndoor5gStaTest,
            config=config,
        )
        self.enable_test_class(
            clazz=scc_5g_wfd_sta_test.Scc5gWfdStaTest,
            config=config,
        )
        if test_parameters.run_aware_test:
          self.enable_test_class(
              clazz=scc_5g_aware_sta_test.Scc5gAwareStaTest,
              config=config,
          )
          self.enable_test_class(
              clazz=mcc_aware_sta_test.MccAwareStaTest,
              config=config,
          )
        self.enable_test_class(
            clazz=scc_5g_wlan_sta_test.Scc5gWifiLanStaTest,
            config=config,
        )
        self.enable_test_class(
            clazz=scc_indoor_5g_wfd_sta_test.SccIndoor5gWfdStaTest,
            config=config,
        )
      if test_parameters.run_compound_test:
        self.enable_test_class(
            clazz=scc_5g_all_wifi_sta_test.Scc5gAllWifiStaTest,
            config=config,
        )

    # add directed/cuj tests which requires DFS 5G wlan AP
    if (
        test_parameters.wifi_dfs_5g_ssid
        or test_parameters.use_auto_controlled_wifi_ap
    ):
      config = self._config.copy()
      config.user_params['wifi_channel'] = nc_constants.CHANNEL_5G_DFS

      if test_parameters.run_directed_test:
        self.enable_test_class(
            clazz=mcc_5g_hotspot_dfs_5g_sta_test.Mcc5gHotspotDfs5gStaTest,
            config=config,
        )
        self.enable_test_class(
            clazz=mcc_5g_wfd_dfs_5g_sta_test.Mcc5gWfdDfs5gStaTest,
            config=config,
        )
        self.enable_test_class(
            clazz=scc_dfs_5g_hotspot_sta_test.SccDfs5gHotspotStaTest,
            config=config,
        )
        self.enable_test_class(
            clazz=scc_dfs_5g_wfd_sta_test.SccDfs5gWfdStaTest,
            config=config,
        )
    self.add_enabled_test_classes_from_selection()


def main() -> None:
  """Entry point for execution as pip installed script."""
  # Mobly's suite_runner searches for suite classes in the __main__ namespace,
  # which breaks when main() is called from a module import. Manually add the
  # suite class to the __main__ module namespace as a workaround.
  sys.modules['__main__'].__dict__[
      BetoCqPerformanceTestSuite.__name__] = BetoCqPerformanceTestSuite
  # Use suite_runner's `main`.
  suite_runner.run_suite_class()


if __name__ == '__main__':
  main()
