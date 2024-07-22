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

In this case, even though the expected wifi medium is the WFD, but the wifi D2D
could be any wifi mediums, such as WFD, HOTSPOT, WifiLan; Once the WFD is
failed, other meidums will be tried. As DBS is not supported by both devices,
and the STA is coonected with 2G channel, D2D medium is using a 5G channel,
this cause the MCC case.

The device requirements:
  support 5G: true
  support DBS (target device): false
The AP requirements:
  wifi channel: 6 (2437)
"""

import logging

from mobly  import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants


class Mcc5gAllWifiNonDbs2gStaTest(
    d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for CUJ MCC with 5G D2D medium and 2G WLAN test."""

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    super().setup_class()
    self._is_mcc = True
    self.performance_test_iterations = getattr(
        self.test_mcc_5g_all_wifi_non_dbs_2g_sta, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.MCC_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.MCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_mcc_5g_all_wifi_non_dbs_2g_sta(self):
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
        f' {upgraded_medium_name} Check with the wifi chip vendor for any FW'
        ' issue in MCC mode'
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
