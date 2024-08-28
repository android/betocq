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

"""This test is to test the Aware MCC when STAs are connected to two 5G channels.


The device requirements:
  support 5G: true
The AP requirements:
  wifi channel: 36 (5180) and 52 (5260) in the same subnet
"""
import logging

from mobly  import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants
from betocq import setup_utils


class MccAwareStaTest(d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for Aware MCC with the STA connected to two 5G channels."""

  def _get_country_code(self) -> str:
    return 'US'

  def setup_class(self):
    super().setup_class()
    self._is_mcc = True
    self.performance_test_iterations = getattr(
        self.test_mcc_aware_sta, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.MCC_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.MCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_mcc_aware_sta(self):
    """Test the performance for Aware MCC."""
    self._test_connection_medium_performance(
        upgrade_medium_under_test=nc_constants.NearbyMedium.WIFIAWARE_ONLY,
        wifi_ssid=self.test_parameters.wifi_5g_ssid,
        wifi_password=self.test_parameters.wifi_5g_password,
        force_disable_bt_multiplex=True,
        connection_medium=nc_constants.NearbyMedium(
            self.test_parameters.connection_medium
        ),
        wifi_ssid2=self.test_parameters.wifi_dfs_5g_ssid,
    )

  def _get_file_transfer_failure_tip(self) -> str:
    return (
        'The Wifi Aware connection might be broken, check related logs, '
        f'{self._get_throughput_low_tip()}'
    )

  def _get_throughput_low_tip(self) -> str:
    return (
        f'{self._throughput_low_string}. This is a MCC 5G test case with Aware'
        ' and STA operating at different 5G channels. Check with the wifi chip'
        ' vendor about the possible firmware Tx/Rx issues in this mode.'
        ' Also check if the AP channel is set correctly and is supported by the'
        ' used wifi medium.'
    )

  def _is_wifi_ap_ready(self) -> bool:
    return (
        True
        if self.test_parameters.wifi_5g_ssid
        and self.test_parameters.wifi_dfs_5g_ssid
        else False
    )

  # @typing.override
  def _is_upgrade_medium_supported(self) -> bool:
    return setup_utils.is_wifi_aware_available(
        self.advertiser
    ) and setup_utils.is_wifi_aware_available(self.discoverer)

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
