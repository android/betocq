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

"""This Test is to test the Wifi MCC with the DFS channels case.

This is about the feature - using DFS channels for Hotspot, for details, refer
to
https://docs.google.com/presentation/d/18Fl0fY4piq_sfXfo3rCr2Ca55AJHEOvB7rC-rV3SQ9E/edit?usp=sharing
andconfig_wifiEnableStaDfsChannelForPeerNetwork -
https://cs.android.com/android/platform/superproject/main/+/main:packages/modules/Wifi/service/ServiceWifiResources/res/values/config.xml;l=1151
In this case, the feature is disable for the device; The WLAN is using the DFS
5G channel, but the hotspot will be started on another non DFS 5G channel.

The device requirements:
  support 5G: true
  using DFS channels for peer network (target device): false
The AP requirements:
  wifi channel: 52 (5260)
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


class Mcc5gHotspotDfs5gStaTest(
    d2d_performance_test_base.D2dPerformanceTestBase):
  """Test class for MCC with 5G HOTSPOT and DFS 5G STA."""

  def _get_country_code(self) -> str:
    return 'GB'

  def setup_class(self):
    super().setup_class()
    self._is_mcc = True
    self.performance_test_iterations = getattr(
        self.test_mcc_5g_hotspot_dfs_5g_sta, base_test.ATTR_REPEAT_CNT
    )
    logging.info(
        'performance test iterations: %s', self.performance_test_iterations
    )

  @base_test.repeat(
      count=nc_constants.MCC_PERFORMANCE_TEST_COUNT,
      max_consecutive_error=nc_constants.MCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR,
  )
  def test_mcc_5g_hotspot_dfs_5g_sta(self):
    """Test the performance for wifi MCC with 5G HOTSPOT and DFS 5G STA."""
    self._test_connection_medium_performance(
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT,
        wifi_ssid=self.test_parameters.wifi_dfs_5g_ssid,
        wifi_password=self.test_parameters.wifi_dfs_5g_password,
    )

  def _get_file_transfer_failure_tip(self) -> str:
    return (
        'The hotspot connection might be broken, check the related log, '
        f'{self._get_throughput_low_tip()}'
    )

  def _get_throughput_low_tip(self) -> str:
    return (
        f'{self._throughput_low_string}. This is a MCC test case where hotspot'
        ' uses a 5G non-DFS channel and STA uses a5G DFS channel. Note that in'
        ' hotspot mode, the target acts as a WFD GOwhile the source device'
        ' acts as the legcy STA. Check with the wifi chip vendorabout the'
        ' possible firmware Tx/Rx issues in MCC mode.'
    )

  def _is_wifi_ap_ready(self) -> bool:
    return True if self.test_parameters.wifi_dfs_5g_ssid else False

  @property
  def _devices_capabilities_definition(self) -> dict[str, dict[str, bool]]:
    return {
        'discoverer': {
            'supports_5g': True,
        },
        'advertiser': {
            'supports_5g': True,
            'enable_sta_dfs_channel_for_peer_network': False,
        },
    }


if __name__ == '__main__':
  test_runner.main()
