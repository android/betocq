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

"""Group all function tests."""

import time
from mobly import asserts
from mobly import test_runner

from betocq import nc_base_test
from betocq import nc_constants
from betocq import setup_utils
from betocq.function_tests import bt_ble_function_test_actor
from betocq.function_tests import bt_multiplex_function_test_actor
from betocq.function_tests import fixed_wifi_medium_function_test_actor
from betocq.function_tests import function_test_actor_base


class BetoCqFunctionGroupTest(nc_base_test.NCBaseTestClass):
  """The test class to group all function tests in one mobly test."""

  def __init__(self, configs):
    super().__init__(configs)

    self._test_result_messages: dict[str, str] = {}

  def test_bt_ble_function(self):
    """Test the NC with the BT/BLE medium only."""
    self._current_test_actor = self.bt_ble_test_actor
    self.bt_ble_test_actor.test_bt_ble_connection()

  def test_wifilan_function(self):
    """Test the NC with upgrading to the Wifi LAN medium.

    step 1: connect to wifi
    step 2: set up a nearby connection with the WifiLAN medium and transfer a
    small file.
    """
    self._current_test_actor = self.fixed_wifi_medium_test_actor
    self.fixed_wifi_medium_test_actor.connect_to_wifi()
    # Let scan, DHCP and internet validation complete before NC.
    time.sleep(self.test_parameters.target_post_wifi_connection_idle_time_sec)
    self.fixed_wifi_medium_test_actor.run_fixed_wifi_medium_test(
        nc_constants.NearbyMedium.WIFILAN_ONLY, nc_constants.PayloadType.FILE)

  def test_d2d_hotspot_function(self):
    """Test the NC with upgrading to the HOTSPOT as upgrade medium.
    """
    self._current_test_actor = self.fixed_wifi_medium_test_actor
    self.fixed_wifi_medium_test_actor.run_fixed_wifi_medium_test(
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT,
        nc_constants.PayloadType.FILE,
    )
    self.fixed_wifi_medium_test_actor.run_fixed_wifi_medium_test(
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT,
        nc_constants.PayloadType.STREAM,
    )

  def test_wifi_direct_function(self):
    """Test the NC with upgrading to the WiFi Direct as upgrade medium.
    """
    self._current_test_actor = self.fixed_wifi_medium_test_actor
    self.fixed_wifi_medium_test_actor.run_fixed_wifi_medium_test(
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT,
        nc_constants.PayloadType.FILE,
    )
    self.fixed_wifi_medium_test_actor.run_fixed_wifi_medium_test(
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT,
        nc_constants.PayloadType.STREAM,
    )

  def test_wifi_aware_function(self):
    """Test the NC with upgrading to the WiFi Aware as upgrade medium.
    """
    if (
        not self.test_parameters.run_aware_test
        or not setup_utils.is_wifi_aware_available(self.advertiser)
        or not setup_utils.is_wifi_aware_available(self.discoverer)
    ):
      asserts.skip(
          'aware test is disabled or aware is not available in the device'
      )
      return
    self._current_test_actor = self.fixed_wifi_medium_test_actor
    self.fixed_wifi_medium_test_actor.run_fixed_wifi_medium_test(
        nc_constants.NearbyMedium.WIFIAWARE_ONLY,
        nc_constants.PayloadType.FILE,
    )
    self.fixed_wifi_medium_test_actor.run_fixed_wifi_medium_test(
        nc_constants.NearbyMedium.WIFIAWARE_ONLY,
        nc_constants.PayloadType.STREAM,
    )

  def test_bt_multiplex_connections(self):
    """Test the BT multiplex function of nearby connection.

    set up 2 Bluetooth connections with NearbyConnection APIs.
    """
    self._current_test_actor = self.bt_multiplex_test_actor
    self.bt_multiplex_test_actor.test_bt_multiplex_connections()

  def setup_class(self):
    super().setup_class()

    self.bt_ble_test_actor = bt_ble_function_test_actor.BtBleFunctionTestActor(
        self.test_parameters, self.discoverer, self.advertiser
    )
    self.fixed_wifi_medium_test_actor = (
        fixed_wifi_medium_function_test_actor.FixedWifiMediumFunctionTestActor(
            self.test_parameters, self.discoverer, self.advertiser
        )
    )
    self.bt_multiplex_test_actor = (
        bt_multiplex_function_test_actor.BtMultiplexFunctionTestActor(
            self.test_parameters, self.discoverer, self.advertiser
        )
    )
    self._current_test_actor: function_test_actor_base.FunctionTestActorBase = (
        None
    )

  def teardown_test(self) -> None:
    self._test_result_messages[self.current_test_info.name] = (
        self._current_test_actor.get_test_result_message()
    )
    self.record_data({
        'Test Name': self.current_test_info.name,
        'properties': {
            'result': self._current_test_actor.get_test_result_message(),
        },
    })
    super().teardown_test()

if __name__ == '__main__':
  test_runner.main()
