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

"""Bluetooth nearby connection functional test actor."""

from mobly import asserts

from betocq import nc_constants
from betocq import nearby_connection_wrapper
from betocq.function_tests import function_test_actor_base


class BtMultiplexFunctionTestActor(
    function_test_actor_base.FunctionTestActorBase):
  """The actor for running BT/BlE multiplex function test.

  It allows to setup multiple BT connections.
  """

  def test_bt_multiplex_connections(self):
    """Test the capability of setting up two BT connections (multiplex).

    This is only required for specific CUJ: quick start
    step 1: set up 2 BT connections
    step 2: transfer a small file with the 2nd BT connection
    """
    if (
        self.test_parameters.target_cuj_name
        != nc_constants.TARGET_CUJ_QUICK_START
        and not self.test_parameters.requires_bt_multiplex
    ):
      self._skipped = True
      asserts.skip(
          'BT multiplex is not required for this CUJ -'
          f' {self.test_parameters.target_cuj_name}'
      )

    # 1. set up 1st BT connection
    advertising_discovery_medium = nc_constants.NearbyMedium.BLE_ONLY
    nearby_snippet_2 = nearby_connection_wrapper.NearbyConnectionWrapper(
        self.advertiser,
        self.discoverer,
        self.advertiser.nearby2,
        self.discoverer.nearby2,
        advertising_discovery_medium=advertising_discovery_medium,
        connection_medium=nc_constants.NearbyMedium.BT_ONLY,
        upgrade_medium=nc_constants.NearbyMedium.BT_ONLY,
    )
    connection_setup_timeouts = nc_constants.ConnectionSetupTimeouts(
        nc_constants.FIRST_DISCOVERY_TIMEOUT,
        nc_constants.FIRST_CONNECTION_INIT_TIMEOUT,
        nc_constants.FIRST_CONNECTION_RESULT_TIMEOUT)

    try:
      nearby_snippet_2.start_nearby_connection(
          timeouts=connection_setup_timeouts,
          medium_upgrade_type=nc_constants.MediumUpgradeType.NON_DISRUPTIVE)
    finally:
      self._test_failure_reason = nearby_snippet_2.test_failure_reason
      self._test_result.quality_info = (
          nearby_snippet_2.connection_quality_info
      )
    # 2nd bt connection
    nearby_snippet = nearby_connection_wrapper.NearbyConnectionWrapper(
        self.advertiser,
        self.discoverer,
        self.advertiser.nearby,
        self.discoverer.nearby,
        advertising_discovery_medium=advertising_discovery_medium,
        connection_medium=nc_constants.NearbyMedium.BT_ONLY,
        upgrade_medium=nc_constants.NearbyMedium.BT_ONLY,
    )

    second_connection_setup_timeouts = nc_constants.ConnectionSetupTimeouts(
        nc_constants.SECOND_DISCOVERY_TIMEOUT,
        nc_constants.SECOND_CONNECTION_INIT_TIMEOUT,
        nc_constants.SECOND_CONNECTION_RESULT_TIMEOUT)
    try:
      nearby_snippet.start_nearby_connection(
          timeouts=second_connection_setup_timeouts,
          medium_upgrade_type=nc_constants.MediumUpgradeType.NON_DISRUPTIVE)
    finally:
      self._test_failure_reason = nearby_snippet.test_failure_reason
      self._test_result.prior_nc_quality_info = (
          nearby_snippet.connection_quality_info
      )

    # 2. transfer file through bluetooth
    try:
      self._test_result.file_transfer_throughput_kbps = (
          nearby_snippet.transfer_file(
              nc_constants.TRANSFER_FILE_SIZE_1KB,
              nc_constants.BT_1K_PAYLOAD_TRANSFER_TIMEOUT,
              nc_constants.PayloadType.FILE))
    finally:
      self._test_failure_reason = nearby_snippet.test_failure_reason

    # 3. disconnect
    nearby_snippet_2.disconnect_endpoint()
    nearby_snippet.disconnect_endpoint()

  def get_test_result_message(self) -> str:
    if self._skipped:
      return (
          'SKIPPED - not required for the target CUJ: '
          f'{self.test_parameters.target_cuj_name}'
      )
    if (
        self._test_failure_reason
        == nc_constants.SingleTestFailureReason.SUCCESS
    ):
      return 'PASS'
    if (
        self._test_failure_reason
        is nc_constants.SingleTestFailureReason.FILE_TRANSFER_FAIL
    ):
      return 'The Bluetooth performance is really bad.'
    else:
      return ''.join([
          f'FAIL: due to {self._test_failure_reason.name} - ',
          f'{nc_constants.COMMON_TRIAGE_TIP.get(self._test_failure_reason)}'
          ])
