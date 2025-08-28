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

"""This test is to test the bluetooth and wifi 2G coex.

Test requirements:
  The device requirements:
    2 Android devices.
  The AP requirements:
    wifi channel: 6 (2437)

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Connect discoverer to a 2G Wi-Fi network.
  2. Set up a prior Nearby Connection through Bluetooth medium.
  3. Connect advertiser to the same Wi-Fi network.
  4. Set up a connection and upgrade to any available Wi-Fi medium.
      * The expected wifi medium is WFD, but other mediums will be tried if
        WFD is failed.
  5. Transfer file on the connection established in step 4.
  6. Tear down all Nearby Connections.

Expected results:
  1. File transfer completes.
  2. The Wi-Fi STA frequency is a 2g frequency.
  3. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
     success rate of no less than `SUCCESS_RATE_TARGET`.
"""

from mobly import base_test
from mobly import test_runner
from mobly import utils
from mobly.controllers import android_device

from betocq import nc_constants
from betocq import nc_utils
from betocq import performance_test_base
from betocq import setup_utils
from betocq import test_result_utils


TEST_ITERATION_NUM = nc_constants.BT_COEX_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = nc_constants.SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = (
    nc_constants.BT_COEX_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
)
_FILE_TRANSFER_NUM = 1
_FILE_TRANSFER_SIZE_KB = nc_constants.TRANSFER_FILE_SIZE_20MB
_FILE_TRANSFER_TIMEOUT = nc_constants.WIFI_2G_20M_PAYLOAD_TRANSFER_TIMEOUT
_PAYLOAD_TYPE = nc_constants.PayloadType.FILE
_COUNTRY_CODE = 'US'


_FILE_TRANSFER_FAILURE_TIP = (
    'The Wifi medium connection might be broken, check related log.'
)


class Bt2gWifiCoexTest(performance_test_base.PerformanceTestBase):
  """Stress test with BT and 2G wifi coex."""

  test_runtime: nc_constants.NcTestRuntime
  wifi_info: nc_constants.WifiInfo

  def setup_class(self):
    super().setup_class()

    self.setup_wifi_env(
        d2d_type=nc_constants.WifiD2DType.ANY_WFD_2G_STA,
        country_code=_COUNTRY_CODE,
    )
    self.wifi_info = nc_constants.WifiInfo.from_test_parameters(
        d2d_type=nc_constants.WifiD2DType.ANY_WFD_2G_STA,
        params=self.test_parameters,
    )
    self.test_runtime = nc_constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        upgrade_medium_under_test=nc_constants.NearbyMedium.UPGRADE_TO_ALL_WIFI,
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
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )

  def _assert_test_conditions(self):
    """Aborts the test class if any test condition is not met."""
    # Check WiFi AP.
    nc_utils.abort_if_2g_ap_not_ready(self.test_parameters)

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
  def test_bt_2g_wifi_coex(self):
    """Stress test with BT and 2G wifi coex."""
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
    # Other test cases wait a while after Wi-Fi connection to let scan, DHCP
    # and internet validation complete. But we don't need to wait in this test
    # case as we don't care speed.

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

    prior_bt_snippet.disconnect_endpoint()
    active_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
