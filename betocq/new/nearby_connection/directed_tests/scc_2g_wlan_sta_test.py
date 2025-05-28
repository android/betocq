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

"""This test is to test that 2 devices connecting to the same 2G AP.

In this case, both the Wifi LAN and STA(internet AP) are using the 2G channel,
the Wifi LAN and STA should use the same channel.
Wifi LAN - The target device starts WFD GO as the role of AP, the source device
is connected to the AP.

Test requirements:
  The device requirements:
    supports_5g=False in config file
  The AP requirements:
    wifi channel: 6 (2437)

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Connect discoverer to a 2G Wi-Fi network.
  2. Set up a prior Nearby Connection through Bluetooth medium.
  3. Connect advertiser to the same Wi-Fi network.
  4. Set up a connection with WLAN as upgrade medium.
  5. Transfer file on the connection established in step 4.
  6. Tear down all Nearby Connections.

Expected results:
  1. The file transfer completes and throughput meets the target. The
     target is calculated according to the device capabilities.
  2. The Wi-Fi STA frequency is a 2G frequency.
  3. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
     success rate of no less than `SUCCESS_RATE_TARGET`.
"""

import time

from mobly import base_test
from mobly import test_runner
from mobly import utils
from mobly.controllers import android_device

from betocq.new import nc_constants
from betocq.new import nc_utils
from betocq.new import performance_test_base
from betocq.new import setup_utils
from betocq.new import test_result_utils


TEST_ITERATION_NUM = nc_constants.SCC_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = nc_constants.SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = nc_constants.SCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
_FILE_TRANSFER_NUM = 1
_FILE_TRANSFER_SIZE_KB = nc_constants.TRANSFER_FILE_SIZE_20MB
_FILE_TRANSFER_TIMEOUT = nc_constants.WIFI_2G_20M_PAYLOAD_TRANSFER_TIMEOUT
_PAYLOAD_TYPE = nc_constants.PayloadType.FILE
_COUNTRY_CODE = 'US'


_THROUGHPUT_LOW_TIP = (
    ' This is a SCC 2G test case with WLAN medium. Check with the wifi chip'
    ' vendor if TDLS is supported correctly. Also check if the AP has the'
    ' firewall which could block the mDNS traffic.'
)


_FILE_TRANSFER_FAILURE_TIP = (
    'The WLAN connection might be broken, check related logs.'
    f' {_THROUGHPUT_LOW_TIP}'
)


class Scc2gWlanStaTest(performance_test_base.PerformanceTestBase):
  """Test class for Wifi SCC with 2G WifiLAN and STA."""

  test_runtime: nc_constants.NcTestRuntime
  wifi_info: nc_constants.WifiInfo

  def setup_class(self):
    super().setup_class()

    self.setup_wifi_env(
        d2d_type=nc_constants.WifiD2DType.SCC_2G, country_code=_COUNTRY_CODE
    )
    self.wifi_info = nc_constants.WifiInfo.from_test_parameters(
        d2d_type=nc_constants.WifiD2DType.SCC_2G, params=self.test_parameters
    )
    self.test_runtime = nc_constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        upgrade_medium_under_test=nc_constants.NearbyMedium.WIFILAN_ONLY,
        country_code=_COUNTRY_CODE,
        wifi_info=self.wifi_info,
    )

    self.test_results.test_iterations_expected = TEST_ITERATION_NUM
    self.test_results.success_rate_target = SUCCESS_RATE_TARGET
    self.test_results.nc_test_runtime = self.test_runtime

    # Test specific device setup steps.
    utils.concurrent_exec(
        self._setup_android_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    self._assert_test_conditions()

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    # Load an extra snippet instance nearby2 for the prior BT connection.
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[self.nearby_snippet_config, self.nearby2_snippet_config],
        country_code=self.test_runtime.country_code,
        debug_output_dir=self.current_test_info.output_path,
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )

  def _assert_test_conditions(self):
    """Aborts the test class if any test condition is not met."""
    # Check WiFi AP.
    nc_utils.abort_if_2g_ap_not_ready(self.test_parameters)
    # Check device capabilities.
    nc_utils.abort_if_device_cap_not_match(
        [self.discoverer, self.advertiser], 'supports_5g', expected_value=False
    )

  def setup_test(self):
    super().setup_test()
    nc_utils.reset_nearby_connection(self.discoverer, self.advertiser)
    utils.concurrent_exec(
        setup_utils.remove_disconnect_wifi_network,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

  @base_test.repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=_MAX_CONSECUTIVE_ERROR,
  )
  def test_scc_2g_wifilan_sta(self):
    """Test the performance for Wifi SCC with 2G WifiLAN and STA."""
    # Test Step: Connect discoverer to wifi sta.
    nc_utils.connect_ad_to_wifi_sta(
        self.discoverer,
        self.wifi_info.discoverer_wifi_ssid,
        self.wifi_info.discoverer_wifi_password,
        self.current_test_result,
        is_discoverer=True,
    )

    # Test Step: Set up a prior BT connection.
    prior_bt_snippet = nc_utils.start_prior_bt_nearby_connection(
        self.advertiser, self.discoverer, self.current_test_result
    )

    # Test Step: Connect advertiser to wifi sta.
    nc_utils.connect_ad_to_wifi_sta(
        self.advertiser,
        self.wifi_info.advertiser_wifi_ssid,
        self.wifi_info.advertiser_wifi_password,
        self.current_test_result,
        is_discoverer=False,
    )
    # Let scan, DHCP and internet validation complete before NC.
    # This is important especially for the transfer speed or WLAN test.
    time.sleep(self.test_parameters.target_post_wifi_connection_idle_time_sec)

    # Test Step: Set up a NC connection for file transfer.
    active_snippet = nc_utils.start_main_nearby_connection(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        upgrade_medium_under_test=self.test_runtime.upgrade_medium_under_test,
        connect_timeout=nc_constants.DEFAULT_SECOND_CONNECTION_TIMEOUTS,
    )

    # Test Step: Transfer file on the established NC.
    try:
      self.current_test_result.file_transfer_throughput_kbps = (
          active_snippet.transfer_file(
              file_size_kb=_FILE_TRANSFER_SIZE_KB,
              timeout=_FILE_TRANSFER_TIMEOUT,
              payload_type=_PAYLOAD_TYPE,
              num_files=_FILE_TRANSFER_NUM,
          )
      )
    finally:
      nc_utils.handle_file_transfer_failure(
          active_snippet.test_failure_reason,
          self.current_test_result,
          file_transfer_failure_tip=_FILE_TRANSFER_FAILURE_TIP,
      )

      # Collect test metrics and check the transfer medium info regardless of
      # whether the transfer succeeded or not.
      test_result_utils.collect_nc_test_metrics(
          self.current_test_result, self.test_runtime
      )
      test_result_utils.assert_sta_frequency(
          self.current_test_result,
          expected_wifi_type=self.wifi_info.sta_type,
      )

    # Check the throughput and run iperf if needed.
    test_result_utils.assert_2g_wifi_throughput_and_run_iperf_if_needed(
        test_result=self.current_test_result,
        nc_test_runtime=self.test_runtime,
        low_throughput_tip=_THROUGHPUT_LOW_TIP,
    )

    prior_bt_snippet.disconnect_endpoint()
    active_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
