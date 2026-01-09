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

"""This test is to test the classic Bluetooth performance.

Test requirements:
  2 Android devices.

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Set up a connection with Bluetooth as connection medium.
  2. Transfer file.
  3. Tear down the connection.

Expected results:
  1. The file transfer completes and throughput meets the target
     `THROUGHPUT_TARGET`.
  2. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
     success rate of no less than `SUCCESS_RATE_TARGET`.
"""

import logging

from mobly import base_test
from mobly import test_runner
from mobly import utils
from mobly.controllers import android_device

from betocq import nc_constants
from betocq import performance_test_base
from betocq import setup_utils
from betocq import test_result_utils
from betocq.nearby_connection import utils as nc_utils


THROUGHPUT_TARGET = nc_constants.CLASSIC_BT_MEDIUM_THROUGHPUT_BENCHMARK_MBPS
TEST_ITERATION_NUM = nc_constants.BT_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = nc_constants.SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = nc_constants.BT_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
_FILE_TRANSFER_NUM = 1
_FILE_TRANSFER_SIZE_KB = nc_constants.TRANSFER_FILE_SIZE_500KB
_FILE_TRANSFER_TIMEOUT = nc_constants.BT_500K_PAYLOAD_TRANSFER_TIMEOUT
_PAYLOAD_TYPE = nc_constants.PayloadType.FILE


_THROUGHPUT_LOW_TIP = (
    'Check with the chip vendor if there is any BT firmware issue.'
)


_FILE_TRANSFER_FAILURE_TIP = (
    'The classic Bluetooth connection might be broken, check related logs.'
    f' {_THROUGHPUT_LOW_TIP}'
)


class BtPerformanceTest(performance_test_base.PerformanceTestBase):
  """Test class for the classic Bluetooth connection performance."""

  test_runtime: nc_constants.NcTestRuntime
  wifi_info: nc_constants.WifiInfo

  def setup_class(self):
    super().setup_class()

    self.test_runtime = nc_constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        connection_medium=nc_constants.NearbyMedium.BT_ONLY,
        upgrade_medium_under_test=nc_constants.NearbyMedium.BT_ONLY,
        country_code='US',
        wifi_info=None,
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

    # try to disconnect the wifi sta if it is connected.
    # This is to avoid the wifi sta connection interfering the BLE connection
    # in the middle of the test.
    utils.concurrent_exec(
        setup_utils.remove_current_connected_wifi_network,
        param_list=[[self.discoverer], [self.advertiser]],
        raise_on_exception=False,
    )

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[self.nearby_snippet_config],
        country_code=self.test_runtime.country_code,
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )

  @base_test.repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=_MAX_CONSECUTIVE_ERROR,
  )
  def test_classic_bt_performance(self):
    """Test the performance of the classic BT connetion."""
    # Test Step: Set up a NC connection for file transfer.
    active_snippet = nc_utils.start_main_nearby_connection(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        connection_medium=self.test_runtime.connection_medium,
        upgrade_medium_under_test=self.test_runtime.upgrade_medium_under_test,
        connect_timeout=nc_constants.DEFAULT_FIRST_CONNECTION_TIMEOUTS,
        keep_alive_timeout_ms=nc_constants.KEEP_ALIVE_TIMEOUT_BT_MS,
        keep_alive_interval_ms=nc_constants.KEEP_ALIVE_INTERVAL_BT_MS,
        test_parameters=self.test_parameters,
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

    logging.info('NC speed target: %s', THROUGHPUT_TARGET)
    test_result_utils.assert_nc_throughput_meets_target(
        test_result=self.current_test_result,
        nc_speed_min_mbps=THROUGHPUT_TARGET,
        low_throughput_tip=_THROUGHPUT_LOW_TIP,
    )

    active_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
