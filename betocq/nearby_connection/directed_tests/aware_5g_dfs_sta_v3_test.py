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

"""This test is to test the Wifi AWARE R4 in a general case using V3 APIs with 5G DFS STA.


Test requirements:
  The device requirements:
    support 5G band
    support Wi-Fi Aware R4
  The AP requirements:
    Wi-Fi channel: 52 (5260) or 112 (5560) or other 5G DFS channels.

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Connect discoverer to a 5G DFS Wi-Fi network.
  2. Set up a connection with Wi-Fi Aware as upgrade medium.
  3. Transfer file.
  4. Tear down the connection.

Expected results:
  1. The medium was successfully upgraded to Wi-Fi Aware.
  2. The file transfer completes and throughput meets the target. The
     target is calculated according to the device capabilities.
  3. The Wi-Fi STA frequency is a 5G DFS frequency.
  4. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
     success rate of no less than `SUCCESS_RATE_TARGET`.
"""

from mobly import test_runner
from typing_extensions import override

from betocq import constants
from betocq import setup_utils
from betocq.nearby_connection.directed_tests import aware_sta_v3_test_base

_THROUGHPUT_LOW_TIP = (
    'This is 5G DFS Aware test case. Check with the wifi chip vendor if Aware'
    ' is supported correctly on DFS channels.'
)


class Aware5gDfsStaV3Test(aware_sta_v3_test_base.AwareStaV3TestBase):

  d2d_type: constants.WifiD2DType = constants.WifiD2DType.XCC_5G_STA
  throughput_low_tip: str = _THROUGHPUT_LOW_TIP

  @override
  def _assert_test_conditions(self):
    # Check WiFi AP.
    setup_utils.abort_if_dfs_5g_ap_not_ready(self.test_parameters)

  @setup_utils.betocq_repeat(
      count=aware_sta_v3_test_base.TEST_ITERATION_NUM,
      max_consecutive_error=aware_sta_v3_test_base.MAX_CONSECUTIVE_ERROR,
  )
  def test_aware_r4_5g_dfs_sta(self):
    self._run_aware_test()


if __name__ == '__main__':
  test_runner.main()
