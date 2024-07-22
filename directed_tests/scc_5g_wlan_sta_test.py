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

"""This Test is to test the Wifi SCC of LAN in a general case.

In this case, both the D2D_LAN and WLAN are using the 5G channel, the D2d_LAN
and WLAN should use the same channel.

The device requirements:
  support 5G: true
The AP requirements:
  wifi channel: 36 (5180)
"""

import logging

from mobly  import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants


class Scc5gWifiLanStaTest(d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for Wifi SCC with 5G WifiLAN and STA."""

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    super().setup_class()
    self.performance_test_iterations = getattr(
        self.test_scc_5g_wifilan_sta, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.SCC_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.SCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_scc_5g_wifilan_sta(self):
    """Test the performance for Wifi SCC with 5G WifiLAN and STA."""
    self._test_connection_medium_performance(
        nc_constants.NearbyMedium.WIFILAN_ONLY,
        wifi_ssid=self.test_parameters.wifi_5g_ssid,
        wifi_password=self.test_parameters.wifi_5g_password,
    )

  def _get_file_transfer_failure_tip(self) -> str:
    return (
        'The WLAN connection might be broken, check related logs, '
        f'{self._get_throughput_low_tip()}'
    )

  def _get_throughput_low_tip(self) -> str:
    return (
        f'{self._throughput_low_string}. This is 5G WLAN test case. Check with'
        ' the wifi chip vendor if TDLS is supported correctly. Also check if'
        ' the AP has the firewall which could block the mDNS traffic.'
    )

  def _is_wifi_ap_ready(self) -> bool:
    return True if self.test_parameters.wifi_5g_ssid else False

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
