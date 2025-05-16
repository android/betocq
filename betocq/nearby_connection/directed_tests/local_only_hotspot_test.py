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

"""This test is to test the local only hotspot case.

Test requirements:
  The device requirements:
    supports_5g=True in config file

Test preparations:
  1. Set country code to US on Android devices.
  2. Set the flag use_wifi_direct_hotspot to false.

Test steps:
  1. Set up a connection with Wi-Fi Hotspot as upgrade medium.
  2. Transfer file.
  3. Tear down the connection.

Expected results:
  1. The file transfer completes and throughput meets the target. The
     target is calculated according to the device capabilities.
  2. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
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


TEST_ITERATION_NUM = nc_constants.LOHS_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = nc_constants.SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = (
    nc_constants.LOHS_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
)
_FILE_TRANSFER_NUM = 1
_FILE_TRANSFER_SIZE_KB = nc_constants.TRANSFER_FILE_SIZE_500MB
_FILE_TRANSFER_TIMEOUT = nc_constants.WIFI_500M_PAYLOAD_TRANSFER_TIMEOUT
_PAYLOAD_TYPE = nc_constants.PayloadType.FILE
_COUNTRY_CODE = 'US'


_THROUGHPUT_LOW_TIP = (
    'This is local only hotspot test case. Check if the local only hotspot'
    ' enabled 5G channel properly.'
)


_FILE_TRANSFER_FAILURE_TIP = (
    'The Wifi Hotspot connection might be broken, check related logs.'
    f' {_THROUGHPUT_LOW_TIP}'
)


class LocalOnlyHotspotTest(performance_test_base.PerformanceTestBase):
  """Test class for the local only Hotspot."""

  test_runtime: nc_constants.NcTestRuntime
  wifi_info: nc_constants.WifiInfo

  def setup_class(self):
    super().setup_class()

    self.wifi_info = nc_constants.WifiInfo(
        d2d_type=nc_constants.WifiD2DType.LOCAL_ONLY_HOTSPOT,
        advertiser_wifi_ssid='',
        advertiser_wifi_password='',
        discoverer_wifi_ssid='',
        discoverer_wifi_password='',
    )
    self.test_runtime = nc_constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        upgrade_medium_under_test=(
            nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT
        ),
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
    setup_utils.set_flag_wifi_direct_hotspot_off(
        self.advertiser, self.current_test_info.output_path
    )

    self._assert_test_conditions()

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[self.nearby_snippet_config],
        country_code=self.test_runtime.country_code,
        debug_output_dir=self.current_test_info.output_path,
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )

  def _assert_test_conditions(self):
    """Aborts the test class if any test condition is not met."""
    # Check device capabilities.
    nc_utils.abort_if_device_cap_not_match(
        [self.discoverer, self.advertiser], 'supports_5g', expected_value=True
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
  def test_local_only_hotspot(self):
    """Test the performance for local only Hotspot."""
    # Test Step: Set up a NC connection for file transfer.
    active_snippet = nc_utils.start_main_nearby_connection(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        upgrade_medium_under_test=self.test_runtime.upgrade_medium_under_test,
        connect_timeout=nc_constants.DEFAULT_FIRST_CONNECTION_TIMEOUTS,
    )

    # Test Step: Transfer file on the established connection.
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

    # Check the throughput and run iperf if needed.
    test_result_utils.assert_5g_wifi_throughput_and_run_iperf_if_needed(
        test_result=self.current_test_result,
        nc_test_runtime=self.test_runtime,
        low_throughput_tip=_THROUGHPUT_LOW_TIP,
    )

    active_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
