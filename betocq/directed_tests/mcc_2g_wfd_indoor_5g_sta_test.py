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

"""This Test is to test the Wifi MCC with the indoor channels case.

This is about the feature - using indoor channels for WFD, for details, refer to
https://docs.google.com/presentation/d/18Fl0fY4piq_sfXfo3rCr2Ca55AJHEOvB7rC-rV3SQ9E/edit?usp=sharing
and config_wifiEnableStaIndoorChannelForPeerNetwork -
https://cs.android.com/android/platform/superproject/main/+/main:packages/modules/Wifi/service/ServiceWifiResources/res/values/config.xml;l=1147
In this case, the feature is disable for the device; The WFD will be started on
a 2G channel, but the STA is using the 5G channel.

The device requirements:
  support 5G: true
  using indoor channels for peer network: false
The AP requirements:
  wifi channel: 36 (5180)
"""

import datetime
import logging

from mobly import base_test
from mobly import test_runner

from betocq import d2d_performance_test_base
from betocq import nc_constants
from betocq import setup_utils


class Mcc2gWfdIndoor5gStaTest(d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for wifi MCC with 2G WFD and indoor 5G STA."""

  def _get_country_code(self) -> str:
    return 'JP'

  def setup_class(self):
    super().setup_class()
    self._is_mcc = True
    self._is_2g_d2d_wifi_medium = True
    self.performance_test_iterations = getattr(
        self.test_mcc_2g_wfd_indoor_5g_sta, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.SCC_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.SCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_mcc_2g_wfd_indoor_5g_sta(self):
    """Test the performance for wifi MCC with 2G WFD and indoor 5G STA."""
    self._test_connection_medium_performance(
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT,
        wifi_ssid=self.test_parameters.wifi_5g_ssid,
        wifi_password=self.test_parameters.wifi_5g_password,
    )

  def _get_transfer_file_size(self) -> int:
    # For 2G wifi medium
    return nc_constants.TRANSFER_FILE_SIZE_20MB

  def _get_file_transfer_timeout(self) -> datetime.timedelta:
    return nc_constants.WIFI_2G_20M_PAYLOAD_TRANSFER_TIMEOUT

  def _get_file_transfer_failure_tip(self) -> str:
    return (
        'The Wifi Direct connection might be broken, check related logs, '
        f'{self._get_throughput_low_tip()}'
    )

  def _get_throughput_low_tip(self) -> str:
    return (
        f'{self._throughput_low_string}. This is a MCC test case where WFD uses'
        ' a 2G channel and the STA uses a 5G indoor channel. Check with the'
        ' wifi chip vendor about the possible firmware Tx/Rx issues in MCC'
        ' mode.'
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
            'enable_sta_indoor_channel_for_peer_network': False,
        },
    }


if __name__ == '__main__':
  test_runner.main()
