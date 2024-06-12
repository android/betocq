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
could be any mediums, such as WFD, HOTSPOT, STA; Once the WFD is failed, other
mediums will be tried. Also, though the WLAN is connected with 2G channel,
as the devices support DBS, which don't need to switch between 5G and 2G, it is
still a SCC case.

The device requirements:
  support 5G: true
  support DBS (target device): true
The AP requirements:
  wifi channel: 6 (2437)
"""

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


class Scc5gAllWifiDbs2gStaTest(
    d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for CUJ SCC with 5G D2D medium and 2G WLAN test.
  """

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    super().setup_class()
    self._is_dbs_mode = True
    self.performance_test_iterations = getattr(
        self.test_scc_5g_all_wifi_dbs_2g_sta, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.SCC_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.SCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_scc_5g_all_wifi_dbs_2g_sta(self):
    self._test_connection_medium_performance(
        upgrade_medium_under_test=nc_constants.NearbyMedium.UPGRADE_TO_ALL_WIFI,
        wifi_ssid=self.test_parameters.wifi_2g_ssid,
        wifi_password=self.test_parameters.wifi_2g_password,
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
        f'check the related log, Or {self._get_throughput_low_tip()}'
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
        f' {upgraded_medium_name}. This is a 5G SCC DBS case, In the'
        ' configuration file, DBS support is set to true on the target side.'
        ' Check if the device does support DBS with STA + WFD concurrency.'
    )

  def _is_wifi_ap_ready(self) -> bool:
    return True if self.test_parameters.wifi_2g_ssid else False

  @property
  def _devices_capabilities_definition(self) -> dict[str, dict[str, bool]]:
    return {
        'discoverer': {
            'supports_5g': True,
        },
        'advertiser': {
            'supports_5g': True,
            'supports_dbs_sta_wfd': True,
        },
    }


if __name__ == '__main__':
  test_runner.main()
