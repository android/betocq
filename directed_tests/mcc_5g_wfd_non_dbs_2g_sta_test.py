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

In this case, the WFD is using the 5G channel, but STA is connected to 2G
channel, as the device(don't support DBS) can not handle the 5G and 2G at
the same time, there is concurrent contention for the 5G channel and 2G
channel handling in firmware, the firmware needs to switch 5G and 2G from time
to time.

The device requirements:
  support 5G: true
  support DBS(Target Device): False
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

from mobly import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants


class Mcc5gWfdNonDbs2gStaTest(d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for MCC case with 5G WFD and 2G STA."""

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    super().setup_class()
    self._is_mcc = True
    self.performance_test_iterations = getattr(
        self.test_mcc_5g_wfd_non_dbs_2g_sta, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.MCC_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.MCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_mcc_5g_wfd_non_dbs_2g_sta(self):
    """Test the performance for wifi MCC with 5G WFD and 2G STA."""
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
        f'{self._throughput_low_string}.'
        ' This is a MCC test case where WFD uses a 5G channel and STA uses a'
        ' 2G channel. Check with the wifi chip vendor'
        ' about the possible firmware Tx/Rx issues in MCC mode.'
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
            'supports_dbs_sta_wfd': False,
        },
    }


if __name__ == '__main__':
  test_runner.main()
