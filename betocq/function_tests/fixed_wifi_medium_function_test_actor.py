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

"""Base class for all fixed wifi medium function test actors."""
import logging
from mobly import asserts

from betocq import nc_constants
from betocq import nearby_connection_wrapper
from betocq import setup_utils
from betocq.function_tests import function_test_actor_base


class FixedWifiMediumFunctionTestActor(
    function_test_actor_base.FunctionTestActorBase):
  """The base of actors for running the specified fixed wifi D2D medium."""

  def run_fixed_wifi_medium_test(
      self, wifi_medium: nc_constants.NearbyMedium) -> None:
    """upgrade the medium from BT to the specified medium and transfer a sample data."""
    self._wifi_medium_under_test = wifi_medium
    self._test_result = nc_constants.SingleTestResult()

    # 1. set up BT and WiFi connection
    advertising_discovery_medium = nc_constants.NearbyMedium(
        self.test_parameters.advertising_discovery_medium
    )
    nearby_snippet = nearby_connection_wrapper.NearbyConnectionWrapper(
        self.advertiser,
        self.discoverer,
        self.advertiser.nearby,
        self.discoverer.nearby,
        advertising_discovery_medium=advertising_discovery_medium,
        connection_medium=nc_constants.NearbyMedium.BT_ONLY,
        upgrade_medium=self._wifi_medium_under_test,
    )

    connection_setup_timeouts = nc_constants.ConnectionSetupTimeouts(
        nc_constants.FIRST_DISCOVERY_TIMEOUT,
        nc_constants.FIRST_CONNECTION_INIT_TIMEOUT,
        nc_constants.FIRST_CONNECTION_RESULT_TIMEOUT)

    try:
      nearby_snippet.start_nearby_connection(
          timeouts=connection_setup_timeouts,
          medium_upgrade_type=nc_constants.MediumUpgradeType.NON_DISRUPTIVE)
    finally:
      self._test_failure_reason = nearby_snippet.test_failure_reason
      self._test_result.quality_info = (
          nearby_snippet.connection_quality_info
      )

    # 2. transfer file through WiFi
    try:
      self._test_result.file_transfer_throughput_kbps = (
          nearby_snippet.transfer_file(
              nc_constants.TRANSFER_FILE_SIZE_FUNC_TEST_KB,
              nc_constants.TRANSFER_TIMEOUT_FUNC_TEST_SEC,
              nc_constants.PayloadType.FILE,
              nc_constants.TRANSFER_FILE_NUM_FUNC_TEST))
    finally:
      self._test_failure_reason = nearby_snippet.test_failure_reason

    # 3. disconnect
    nearby_snippet.disconnect_endpoint()

  def connect_to_wifi(self):
    if self.test_parameters.toggle_airplane_mode_target_side:
      setup_utils.toggle_airplane_mode(self.advertiser)

    wifi_ssid, wifi_password = self._get_wifi_ssid_password()

    if not wifi_ssid:
      self._test_failure_reason = (
          nc_constants.SingleTestFailureReason.AP_IS_NOT_CONFIGURED
      )
      asserts.fail('Wifi AP must be specified.')

    logging.info('connect to wifi: %s', wifi_ssid)

    # source device
    self._test_failure_reason = (
        nc_constants.SingleTestFailureReason.SOURCE_WIFI_CONNECTION
    )
    discoverer_wifi_latency = setup_utils.connect_to_wifi_sta_till_success(
        self.discoverer, wifi_ssid, wifi_password
    )
    self.discoverer.log.info(
        'connecting to wifi in '
        f'{round(discoverer_wifi_latency.total_seconds())} s'
    )
    # target device
    self._test_failure_reason = (
        nc_constants.SingleTestFailureReason.TARGET_WIFI_CONNECTION
    )
    advertiser_wlan_latency = setup_utils.connect_to_wifi_sta_till_success(
        self.advertiser, wifi_ssid, wifi_password)
    self.advertiser.log.info(
        'connecting to wifi in '
        f'{round(advertiser_wlan_latency.total_seconds())} s')
    self.advertiser.log.info(
        self.advertiser.nearby.wifiGetConnectionInfo().get('mFrequency')
    )
    self._test_failure_reason = (
        nc_constants.SingleTestFailureReason.SUCCESS
    )

  def get_test_result_message(self) -> str:
    if (
        self._test_failure_reason
        == nc_constants.SingleTestFailureReason.SUCCESS
    ):
      return 'PASS'
    if (
        self._test_failure_reason
        == nc_constants.SingleTestFailureReason.WIFI_MEDIUM_UPGRADE
    ):
      return ''.join([
          f'{self._test_failure_reason.name} - ',
          self._get_medium_upgrade_failure_tip()
      ])
    if (
        self._test_failure_reason
        == nc_constants.SingleTestFailureReason.FILE_TRANSFER_FAIL
    ):
      return ''.join([
          f'{self._test_failure_reason.name} - ',
          self._get_file_transfer_failure_tip()
      ])
    return ''.join([
        f'{self._test_failure_reason.name} - ',
        nc_constants.COMMON_TRIAGE_TIP.get(self._test_failure_reason),
    ])

  def _get_medium_upgrade_failure_tip(self) -> str:
    return nc_constants.MEDIUM_UPGRADE_FAIL_TRIAGE_TIPS.get(
        self._wifi_medium_under_test, ' unsupported test medium')

  def _get_file_transfer_failure_tip(self) -> str:
    if self._wifi_medium_under_test is not None:
      return (
          f'{self._wifi_medium_under_test.name}: the transfer times out. Check'
          ' if medium is still connected and review logcats for more details.'
      )
    asserts.fail('unexpected calling of _get_file_transfer_failure_tip')
