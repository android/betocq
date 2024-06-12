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

"""This Test is to test the classic Bluetooth performance."""

import datetime
import logging
import os
import sys

# Allows local imports to be resolved via relative path, so the test can be run
# without building.
_betocq_dir = os.path.dirname(os.path.dirname(__file__))
if _betocq_dir not in sys.path:
  sys.path.append(_betocq_dir)

from mobly  import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants


class BtPerformanceTest(d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for the classic Bluetooth connection performance."""

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    super().setup_class()
    self.performance_test_iterations = getattr(
        self.test_classic_bt_performance, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.BT_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.BT_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_classic_bt_performance(self):
    """Test the performance of the classic BT connetion."""
    self._test_connection_medium_performance(
        upgrade_medium_under_test=nc_constants.NearbyMedium.BT_ONLY,
        force_disable_bt_multiplex=True
    )

  def _get_transfer_file_size(self) -> int:
    return nc_constants.TRANSFER_FILE_SIZE_500KB

  def _get_file_transfer_timeout(self) -> datetime.timedelta:
    return nc_constants.BT_500K_PAYLOAD_TRANSFER_TIMEOUT

  # @typing.override
  def _get_throughput_benchmark(
      self, sta_frequency: int, sta_max_link_speed_mbps: int
  ) -> tuple[float, float]:
    return (
        nc_constants.CLASSIC_BT_MEDIUM_THROUGHPUT_BENCHMARK_MBPS,
        nc_constants.CLASSIC_BT_MEDIUM_THROUGHPUT_BENCHMARK_MBPS,
    )

  def _get_medium_upgrade_failure_tip(self) -> str:
    return 'Not Applied'  # No medium upgrade required for BT.

  def _get_file_transfer_failure_tip(self) -> str:
    return (
        'The classic Bluetooth connection might be broken, check related log, '
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
