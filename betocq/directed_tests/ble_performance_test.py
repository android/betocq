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

"""This Test is to test the BLE performance."""

import datetime
import logging

from mobly  import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants


class BlePerformanceTest(d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for the BLE connection performance."""

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    super().setup_class()
    self.performance_test_iterations = getattr(
        self.test_ble_performance, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.BT_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.BT_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_ble_performance(self):
    """Test the performance of the BLE."""
    self._test_connection_medium_performance(
        upgrade_medium_under_test=nc_constants.NearbyMedium.BLE_ONLY,
        force_disable_bt_multiplex=True,
        connection_medium=nc_constants.NearbyMedium.BLE_ONLY,
        keep_alive_timeout_ms=nc_constants.KEEP_ALIVE_TIMEOUT_BT_MS,
        keep_alive_interval_ms=nc_constants.KEEP_ALIVE_INTERVAL_BT_MS,
    )

  def _get_transfer_file_size(self) -> int:
    return nc_constants.TRANSFER_FILE_SIZE_20KB

  def _get_file_transfer_timeout(self) -> datetime.timedelta:
    return nc_constants.BLE_20K_PAYLOAD_TRANSFER_TIMEOUT

  def _get_success_rate_target(self) -> float:
    return nc_constants.BLE_PERFORMANCE_TEST_SUCCESS_RATE_TARGET

  # @typing.override
  def _get_throughput_benchmark(
      self, sta_frequency: int, sta_max_link_speed_mbps: int
  ) -> nc_constants.SpeedTarget:
    return nc_constants.SpeedTarget(
        nc_constants.BLE_MEDIUM_THROUGHPUT_BENCHMARK_MBPS,
        nc_constants.BLE_MEDIUM_THROUGHPUT_BENCHMARK_MBPS,
    )

  def _get_medium_upgrade_failure_tip(self) -> str:
    return 'Not Applied'  # No medium upgrade required for BLE.

  def _get_file_transfer_failure_tip(self) -> str:
    return (
        'The BLE connection might be broken, check the related logs, '
        f'{self._get_throughput_low_tip()}'
    )

  def _get_throughput_low_tip(self) -> str:
    return (
        f'{self._throughput_low_string}. Check with the chip vendor if there is'
        ' any BT firmware issue.'
    )

  def _is_wifi_ap_ready(self) -> bool:
    # don't require wifi STA.
    return True


if __name__ == '__main__':
  test_runner.main()
