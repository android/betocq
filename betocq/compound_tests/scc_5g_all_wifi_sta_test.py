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

"""This Test is to test the Wifi SCC in a general case.

In this case, even though the expected wifi medium is the WFD, but the wifi D2D
could be any technologies, such as WFD, HOTSPOT, STA; Once the WFD is failed,
other meidums will be tried. Both the D2D medium and STA are using the same 5G
channel.

The device requirements:
  support 5G: true
  country code: US
The AP requirements:
  wifi channel: 36 (5180)
"""

import logging

from mobly  import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants
from betocq import setup_utils


class Scc5gAllWifiStaTest(d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for Wifi SCC 5G test associated with a specified CUJ."""

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    super().setup_class()
    self.performance_test_iterations = getattr(
        self.test_scc_5g_all_wifi_sta_test, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.SCC_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.SCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_scc_5g_all_wifi_sta_test(self):
    self._test_connection_medium_performance(
        upgrade_medium_under_test=nc_constants.NearbyMedium.UPGRADE_TO_ALL_WIFI,
        wifi_ssid=self.test_parameters.wifi_5g_ssid,
        wifi_password=self.test_parameters.wifi_5g_password,
    )

  def _get_file_transfer_failure_tip(self) -> str:
    upgraded_medium_name = None
    if (self._current_test_result.quality_info.upgrade_medium
        is not None):
      upgraded_medium_name = (
          self._current_test_result.quality_info.upgrade_medium.name
      )
    return (
        f'The upgraded wifi medium {upgraded_medium_name} might be broken, '
        f'check the related logs; Or {self._get_throughput_low_tip()}'
    )

  def _get_throughput_low_tip(self) -> str:
    upgraded_medium_name = None
    if (self._current_test_result.quality_info.upgrade_medium
        is not None):
      upgraded_medium_name = (
          self._current_test_result.quality_info.upgrade_medium.name
      )
    return (
        f'{self._throughput_low_string}. The upgraded medium is'
        f' {upgraded_medium_name}.'
        ' This is a 5G SCC case. Check with the wifi'
        ' chip vendor for any possible FW issue.'
    )

  def _is_wifi_ap_ready(self) -> bool:
    return True if self.test_parameters.wifi_5g_ssid else False

  # @typing.override
  def _is_upgrade_medium_supported(self) -> bool:
    return setup_utils.is_wifi_direct_supported(
        self.advertiser
    ) and setup_utils.is_wifi_direct_supported(self.discoverer)

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
