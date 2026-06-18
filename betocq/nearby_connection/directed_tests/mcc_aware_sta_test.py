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

"""Test for Aware MCC when STAs are connected to two 5G channels.

In this case, Wi-Fi STA on 2 devices are connected to different 5G channels.

Test requirements:
  The device requirements:
    support 5G band
    support Wi-Fi Aware
  The AP requirements:
    Wi-Fi channels: 
      * 5G Non-DFS channel: e.g. 36 (5180)
      * 5G DFS channel: e.g. 52 (5260) or 112 (5560)
    They should be in the same subnet.

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Connect discoverer to a 5G non-DFS Wi-Fi network.
  2. Connect advertiser to a 5G DFS Wi-Fi network.
  3. Set up a connection with Wi-Fi Aware as upgrade medium.
      * Nearby Connection will set up Wi-Fi Aware and upgrade to it.
  5. Transfer file.
  6. Tear down the connection.

Expected results:
  1. The file transfer completes and throughput meets the target. The
     target is calculated according to the device capabilities.
  2. The Wi-Fi STA frequency is a 5G non-DFS frequency.
  3. The Wi-Fi P2P frequency is the same as the STA frequency.
  4. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
     success rate of no less than `SUCCESS_RATE_TARGET`.
"""

import time

from mobly import test_runner
from mobly import utils
from mobly.controllers import android_device
from typing_extensions import override

from betocq import constants
from betocq import setup_utils
from betocq.nearby_connection import nc_constants
from betocq.nearby_connection import nc_performance_test_base
from betocq.nearby_connection import nc_test_result_utils
from betocq.nearby_connection import utils as nc_utils


TEST_ITERATION_NUM = nc_constants.MCC_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = constants.SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = nc_constants.MCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
_FILE_TRANSFER_NUM = 1
_FILE_TRANSFER_SIZE_KB = (
    nc_constants.NC_MCC_5G_D2D_5G_STA_TRANSFER_FILE_SIZE_KB
)
_FILE_TRANSFER_TIMEOUT = constants.WIFI_100M_PAYLOAD_TRANSFER_TIMEOUT
_PAYLOAD_TYPE = constants.PayloadType.FILE


_THROUGHPUT_LOW_TIP = (
    'This is a MCC 5G test case with Aware and STA operating in different 5G'
    ' channels. Check with the wifi chip vendor about the possible firmware'
    ' Tx/Rx issues in this mode.'
)


_FILE_TRANSFER_FAILURE_TIP = (
    'The Wifi Aware connection might be broken, check related logs.'
)


class MccAwareStaTest(nc_performance_test_base.NcPerformanceTestBase):
  """Test class for Aware MCC with the STAs connected to two 5G channels."""

  test_runtime: constants.NcTestRuntime
  wifi_info: constants.WifiInfo

  @override
  def get_success_rate(self, scenario_name: str) -> float:
    """Returns the expected success rate target."""
    del self, scenario_name  # Unused in this implementation.
    return SUCCESS_RATE_TARGET

  @override
  def setup_class(self):
    """Sets up the test class and test runtime environment."""
    super().setup_class()

    self.wifi_info = constants.WifiInfo(
        d2d_type=constants.WifiD2DType.MCC_5G_AND_5G_DFS_STA,
        advertiser_wifi_ssid=self.test_parameters.wifi_dfs_5g_ssid,
        advertiser_wifi_password=self.test_parameters.wifi_dfs_5g_password,
        discoverer_wifi_ssid=self.test_parameters.wifi_5g_ssid,
        discoverer_wifi_password=self.test_parameters.wifi_5g_password,
    )
    self.test_runtime = constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        upgrade_medium_under_test=constants.NearbyMedium.WIFIAWARE_ONLY,
        country_code='US',
        wifi_info=self.wifi_info,
    )

    # Test specific device setup steps.
    utils.concurrent_exec(
        self._setup_android_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    # Check device capabilities.
    setup_utils.abort_if_5g_band_not_supported(
        [self.discoverer, self.advertiser]
    )
    setup_utils.abort_if_wifi_aware_not_available(
        [self.discoverer, self.advertiser]
    )

    nc_utils.check_wifi_ap_status_in_setup_class(
        self, self.advertiser, self.test_parameters, supports_5g=True
    )

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    """Configures snippets and settings for an Android device."""
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[nc_utils.get_nearby_snippet_config(self.user_params)],
        country_code=self.test_runtime.country_code,
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )

  def _assert_test_conditions(self) -> None:
    """Aborts the test class if any test condition is not met."""
    # Check WiFi AP.
    setup_utils.abort_if_any_5g_or_dfs_aps_not_ready(self.test_parameters)

  @setup_utils.betocq_repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=_MAX_CONSECUTIVE_ERROR,
  )
  def test_mcc_aware_sta(self):
    """Test the performance for Aware MCC."""
    # Test Step: Connect discoverer to wifi sta.
    discoverer_connected = nc_utils.connect_ad_to_wifi_sta(
        self.discoverer,
        wifi_ssid=self.wifi_info.discoverer_wifi_ssid,
        wifi_password=self.wifi_info.discoverer_wifi_password,
        metrics=self.get_current_iteration_metrics(),
        is_discoverer=True,
    )

    # Test Step: Connect advertiser to wifi sta.
    advertiser_connected = nc_utils.connect_ad_to_wifi_sta(
        self.advertiser,
        wifi_ssid=self.wifi_info.advertiser_wifi_ssid,
        wifi_password=self.wifi_info.advertiser_wifi_password,
        metrics=self.get_current_iteration_metrics(),
        is_discoverer=False,
    )
    if discoverer_connected or advertiser_connected:
      # Let scan, DHCP and internet validation complete before NC.
      # This is important especially for the transfer speed or WLAN test.
      time.sleep(self.test_parameters.target_post_wifi_connection_idle_time_sec)

    # TODO: differentiate the discoverer and advertiser
    # STA frequency in the test result.
    nc_test_result_utils.set_and_assert_sta_frequency(
        self.discoverer,
        self.get_current_iteration_metrics(),
        constants.WifiType.FREQ_5G,
        prefix='discoverer_',
    )

    nc_test_result_utils.set_and_assert_sta_frequency(
        self.advertiser,
        self.get_current_iteration_metrics(),
        constants.WifiType.FREQ_5G_DFS,
        prefix='advertiser_',
    )

    # Test Step: Set up a NC connection for file transfer.
    active_snippet = nc_utils.start_main_nearby_connection(
        self.advertiser,
        self.discoverer,
        metrics=self.get_current_iteration_metrics(),
        upgrade_medium_under_test=self.test_runtime.upgrade_medium_under_test,
        connect_timeout=constants.DEFAULT_FIRST_CONNECTION_TIMEOUTS,
        test_parameters=self.test_parameters,
    )

    # Test Step: Transfer file on the established NC.
    try:
      self.get_current_iteration_metrics().record(
          'file_transfer_throughput_kbps',
          active_snippet.transfer_file(
              file_size_kb=_FILE_TRANSFER_SIZE_KB,
              timeout=_FILE_TRANSFER_TIMEOUT,
              payload_type=_PAYLOAD_TYPE,
              num_files=_FILE_TRANSFER_NUM,
          ),
      )
    finally:
      nc_utils.handle_file_transfer_failure(
          active_snippet.test_failure_reason,
          self.get_current_iteration_metrics(),
          file_transfer_failure_tip=_FILE_TRANSFER_FAILURE_TIP,
      )

    # Check the throughput and run iperf if needed.
    if not self.test_parameters.skip_throughput_assertion:
      nc_test_result_utils.assert_5g_wifi_throughput_and_run_iperf_if_needed(
          metrics=self.get_current_iteration_metrics(),
          nc_test_runtime=self.test_runtime,
          low_throughput_tip=_THROUGHPUT_LOW_TIP,
      )

    active_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
