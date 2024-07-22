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

"""This Test is to test the Wifi MCC in a general case.

In this case, even though the STA is connected to a 2G channel, and the WFD is
using the 5G channel, as both devices support DBS, which can handle the 5G and
2G at the same time, this is still a SCC case.

The device requirements:
  support 5G: true
  support DBS(target): true
The AP requirements:
  wifi channel: 6 (2437)
"""

import logging
from mobly  import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants


class Scc5gWfdDbs2gStaTest(d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for SCC with 5G WFD and 2G STA."""

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    super().setup_class()
    self._is_dbs_mode = True
    self.performance_test_iterations = getattr(
        self.test_scc_5g_wfd_dbs_2g_sta, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.SCC_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.SCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_scc_5g_wfd_dbs_2g_sta(self):
    """Test the performance for wifi SCC with 5G WFD and 2G STA."""
    self._test_connection_medium_performance(
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT,
        wifi_ssid=self.test_parameters.wifi_2g_ssid,
        wifi_password=self.test_parameters.wifi_2g_password,
    )

  def _get_file_transfer_failure_tip(self) -> str:
    return (
        'The Wifi Direct connection might be broken, check related logs, '
        f'{self._get_throughput_low_tip()}'
    )

  def _get_throughput_low_tip(self) -> str:
    return (
        f'{self._throughput_low_string}. This is a SCC 5G test case with WFD'
        ' medium operating at 5G and STA operating at 2G. In the configuration'
        ' file, DBS support is set to true. Check if thedevice does support'
        ' DBS with STA + WFD concurrency. Check with the wifi chipvendor about'
        ' the possible firmware Tx/Rx issues in this mode.'
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
