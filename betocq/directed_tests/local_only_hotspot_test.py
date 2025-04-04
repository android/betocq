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

"""This Test is to test the local only hotspot case.

The device requirements:
  support 5G: true
"""

import logging

from mobly import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants
from betocq import setup_utils


class LocalOnlyHotspotTest(d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for the local only Hotspot."""

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    super().setup_class()
    self.performance_test_iterations = getattr(
        self.test_local_only_hotspot, base_test.ATTR_REPEAT_CNT
    )
    # Disable wifi direct hotspot on the target device. Instead use local only
    # hotspot.
    setup_utils.set_flag_wifi_direct_hotspot_off(
        self.advertiser, self.current_test_info.output_path
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.LOHS_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.LOHS_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_local_only_hotspot(self):
    """Test the performance for local only Hotspot."""
    self._test_connection_medium_performance(
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT,
    )

  def _get_file_transfer_failure_tip(self) -> str:
    return (
        'The Wifi Hotspot connection might be broken, check related logs, '
        f'{self._get_throughput_low_tip()}'
    )

  def _get_throughput_low_tip(self) -> str:
    return (
        f'{self._throughput_low_string}. This is local only hotspot test case.'
        ' Check if the local only hotspot enabled 5G channel properly.'
    )

  # @typing.override
  def _is_wifi_ap_ready(self) -> bool:
    # No need to set up wifi ap for this test.
    return True

  @property
  def _devices_capabilities_definition(self) -> dict[str, dict[str, bool]]:
    return {
        'discoverer': {
            'supports_5g': True,
        },
        'advertiser': {
            'supports_5g': True,
        },
    }


if __name__ == '__main__':
  test_runner.main()
