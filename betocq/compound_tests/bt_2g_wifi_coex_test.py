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

"""This Test is to test the bluetooth and wifi 2G coex.

The AP requirements:
  wifi channel: 6 (2437)
"""

import datetime
import logging

from mobly  import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants


class Bt2gWifiCoexTest(d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for BT and 2G wifi coex with a complicated stress test."""

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    self.test_parameters.requires_bt_multiplex = True
    # we don't care speed so that there is no need to wait
    self.test_parameters.target_post_wifi_connection_idle_time_sec = 0
    super().setup_class()
    self.performance_test_iterations = getattr(
        self.test_bt_2g_wifi_coex, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.BT_COEX_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.BT_COEX_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_bt_2g_wifi_coex(self):
    """Test the BT and 2G wifi coex with a stress test."""
    self._test_connection_medium_performance(
        nc_constants.NearbyMedium.UPGRADE_TO_ALL_WIFI,
        wifi_ssid=self.test_parameters.wifi_2g_ssid,
        wifi_password=self.test_parameters.wifi_2g_password,
    )

  def _get_transfer_file_size(self) -> int:
    # For 2G wifi medium
    return nc_constants.TRANSFER_FILE_SIZE_20MB

  def _get_file_transfer_timeout(self) -> datetime.timedelta:
    return nc_constants.WIFI_2G_20M_PAYLOAD_TRANSFER_TIMEOUT

  def _get_file_transfer_failure_tip(self) -> str:
    return (
        'The Wifi Direct connection might be broken, check related log.'
    )

  # @typing.override
  def _get_throughput_benchmark(
      self, sta_frequency: int, sta_max_link_speed_mbps: int
  ) -> tuple[float, float]:
    # no requirement for throughput.
    return (0.0, 0.0)

  def _get_throughput_low_tip(self) -> str:
    return (
        f'{self._throughput_low_string}.'
        ' This should never happen, you may ignore this error, this is'
        ' not required for this case.'
    )

  def _is_wifi_ap_ready(self) -> bool:
    return True if self.test_parameters.wifi_2g_ssid else False


if __name__ == '__main__':
  test_runner.main()
