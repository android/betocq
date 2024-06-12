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

import os
import sys

# Allows local imports to be resolved via relative path, so the test can be run
# without building.
_betocq_dir = os.path.dirname(os.path.dirname(__file__))
if _betocq_dir not in sys.path:
  sys.path.append(_betocq_dir)

from mobly import test_runner

from betocq import nc_base_test
from betocq import nc_constants
from betocq import setup_utils
from betocq import version
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
    self.fixed_wifi_medium_test_actor.run_fixed_wifi_medium_test(
        nc_constants.NearbyMedium.WIFILAN_ONLY)

  def test_d2d_hotspot_function(self):
    """Test the NC with upgrading to the HOTSPOT as connection medium.
    """
    self._current_test_actor = self.fixed_wifi_medium_test_actor
    self.fixed_wifi_medium_test_actor.run_fixed_wifi_medium_test(
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT)

  def test_wifi_direct_function(self):
    """Test the NC with upgrading to the WiFi Direct as connection medium.
    """
    self._current_test_actor = self.fixed_wifi_medium_test_actor
    self.fixed_wifi_medium_test_actor.run_fixed_wifi_medium_test(
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT)

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

  # @typing.override
  def _summary_test_results(self):
    """Summarizes test results of all function tests."""

    self.record_data({
        'Test Class': self.TAG,
        'properties': {
            '00_test_script_verion': version.TEST_SCRIPT_VERSION,
            '01_source_device_serial': self.discoverer.serial,
            '02_target_device_serial': self.advertiser.serial,
            '03_source_GMS_version': setup_utils.dump_gms_version(
                self.discoverer
            ),
            '04_target_GMS_version': setup_utils.dump_gms_version(
                self.advertiser
            ),
            '05_test_result': self._test_result_messages,
        },
    })


if __name__ == '__main__':
  test_runner.main()
