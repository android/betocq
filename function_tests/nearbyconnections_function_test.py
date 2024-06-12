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

"""Tests for Neaby Connection between two Android devices."""

from mobly import asserts
from mobly import test_runner
from mobly.snippet import errors

from betocq import nc_base_test
from betocq import nc_constants
from betocq import nearby_connection_wrapper
from betocq import setup_utils
from betocq import version


class NearbyConnectionsFunctionTest(nc_base_test.NCBaseTestClass):
  """Nearby Connection E2E tests."""

  def __init__(self, configs):
    super().__init__(configs)
    self._skipped: bool = False
    self._test_failure_reason: nc_constants.SingleTestFailureReason = (
        nc_constants.SingleTestFailureReason.UNINITIALIZED
    )

  def test_nearby_connections_3p_apis(self):
    """Test the capability of 3P APIs for Nearby Connections."""

    # Verify that from the 3P snippet, it fails to call 1P APIs
    with asserts.assert_raises(errors.ApiError):
      self.advertiser.nearby3p.getLocalEndpointId()
    with asserts.assert_raises(errors.ApiError):
      self.discoverer.nearby3p.getLocalEndpointId()

    self._test_result = nc_constants.SingleTestResult()
    # 1. discovery/advertising
    nearby_snippet_3p = nearby_connection_wrapper.NearbyConnectionWrapper(
        self.advertiser,
        self.discoverer,
        self.advertiser.nearby3p,
        self.discoverer.nearby3p,
        advertising_discovery_medium=nc_constants.NearbyMedium.AUTO,
        connection_medium=nc_constants.NearbyMedium.AUTO,
        upgrade_medium=nc_constants.NearbyMedium.AUTO,
    )

    # 2. create connection
    connection_setup_timeouts = nc_constants.ConnectionSetupTimeouts(
        nc_constants.FIRST_DISCOVERY_TIMEOUT,
        nc_constants.FIRST_CONNECTION_INIT_TIMEOUT,
        nc_constants.FIRST_CONNECTION_RESULT_TIMEOUT,
    )
    try:
      nearby_snippet_3p.start_nearby_connection(
          timeouts=connection_setup_timeouts,
          medium_upgrade_type=nc_constants.MediumUpgradeType.NON_DISRUPTIVE,
      )
    finally:
      self._test_failure_reason = nearby_snippet_3p.test_failure_reason
      self._test_result.file_transfer_nc_setup_quality_info = (
          nearby_snippet_3p.connection_quality_info
      )

    # 3. transfer file
    try:
      self._test_result.file_transfer_throughput_kbps = (
          nearby_snippet_3p.transfer_file(
              nc_constants.TRANSFER_FILE_SIZE_20MB,
              nc_constants.WIFI_2G_20M_PAYLOAD_TRANSFER_TIMEOUT,
              nc_constants.PayloadType.FILE,
          )
      )
    finally:
      self._test_failure_reason = nearby_snippet_3p.test_failure_reason

    # 4. disconnect
    nearby_snippet_3p.disconnect_endpoint()
    self._summary_test_results()

  def teardown_test(self) -> None:
    self._test_result_messages[self.current_test_info.name] = (
        self._get_test_result_message()
    )
    self.record_data({
        'Test Name': self.current_test_info.name,
        'sponge_properties': {
            'result': self._get_test_result_message(),
        },
    })
    super().teardown_test()

  def _summary_test_results(self):
    """Summarizes test results of all function tests."""

    self.record_data({
        'Test Class': self.TAG,
        'sponge_properties': {
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

  def _get_test_result_message(self) -> str:
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


if __name__ == '__main__':
  test_runner.main()