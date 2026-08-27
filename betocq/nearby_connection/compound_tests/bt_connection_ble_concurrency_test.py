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

r"""This test is to test BLE connection performance with active Classic BT connection.

Test requirements:
  2 Android devices.

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Set up a prior Nearby Connection through Classic Bluetooth.
  2. Set up a second Nearby Connection through BLE.
  3. Transfer a small file over the BLE connection.
  4. Tear down both connections.

Expected results:
  1. BLE Connection is established successfully.
  2. File transfer over BLE completes.
  3. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
     success rate of no less than `SUCCESS_RATE_TARGET`.

Execution:
  SKYBUILD=1 blaze test //wireless/android/platform/testing/bettertogether/betocq/nearby_connection/compound_tests:bt_connection_ble_concurrency_test_local \
    --notest_loasd \
    --test_output=streamed \
    --test_timeout=50000 \
    --nofake_stamp_data \
    --test_arg=--mobly_testbed=Default
"""

from mobly import test_runner
from mobly import utils
from mobly.controllers import android_device
from typing_extensions import override

from betocq import constants
from betocq import setup_utils
from betocq.nearby_connection import nc_constants
from betocq.nearby_connection import nc_performance_test_base
from betocq.nearby_connection import utils as nc_utils

TEST_ITERATION_NUM = nc_constants.BT_BLE_CONCURRENCY_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = constants.SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = (
    nc_constants.BT_COEX_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
)
_FILE_TRANSFER_NUM = 1
_FILE_TRANSFER_SIZE_KB = constants.TRANSFER_FILE_SIZE_1KB
_FILE_TRANSFER_TIMEOUT = nc_constants.BT_1K_PAYLOAD_TRANSFER_TIMEOUT
_PAYLOAD_TYPE = constants.PayloadType.FILE
_COUNTRY_CODE = 'US'


_FILE_TRANSFER_FAILURE_TIP = (
    'The BLE connection might be broken, check related logs.'
)


class BtConnectionBleConcurrencyTest(
    nc_performance_test_base.NcPerformanceTestBase
):
  """Concurrency test with prior BT connection and new BLE connection."""

  test_runtime: constants.NcTestRuntime
  wifi_info: constants.WifiInfo

  @override
  def get_success_rate(self, scenario_name: str) -> float:
    del self, scenario_name
    return SUCCESS_RATE_TARGET

  def setup_class(self) -> None:
    super().setup_class()

    self.test_runtime = constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        connection_medium=constants.NearbyMedium.BLE_ONLY,
        upgrade_medium_under_test=constants.NearbyMedium.BLE_ONLY,
        country_code=_COUNTRY_CODE,
        wifi_info=None,
    )

    # Test specific device setup steps.
    utils.concurrent_exec(
        self._setup_android_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    # Disconnect wifi to avoid interference.
    utils.concurrent_exec(
        setup_utils.remove_current_connected_wifi_network,
        param_list=[[self.discoverer], [self.advertiser]],
        raise_on_exception=False,
    )

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    # Load two snippet instances: nearby and nearby2
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[
            nc_utils.get_nearby_snippet_config(self.user_params),
            nc_utils.get_nearby2_snippet_config(self.user_params),
        ],
        country_code=self.test_runtime.country_code,
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )

  @setup_utils.betocq_repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=_MAX_CONSECUTIVE_ERROR,
  )
  def test_ble_connection_with_prior_bt_connection(self) -> None:
    """Establishes BLE connection while Classic BT connection is active."""
    # Test Step: Set up a prior BT connection (Classic BT).
    prior_bt_snippet = nc_utils.start_prior_bt_nearby_connection(
        self.advertiser,
        self.discoverer,
        metrics=self.get_current_iteration_metrics(),
        test_parameters=self.test_parameters,
    )

    # Test Step: Set up BLE connection (main connection).
    active_snippet = nc_utils.start_main_nearby_connection(
        self.advertiser,
        self.discoverer,
        metrics=self.get_current_iteration_metrics(),
        connection_medium=constants.NearbyMedium.BLE_ONLY,
        upgrade_medium_under_test=constants.NearbyMedium.BLE_ONLY,
        connect_timeout=constants.DEFAULT_SECOND_CONNECTION_TIMEOUTS,
        test_parameters=self.test_parameters,
    )

    # Test Step: Transfer file on the established BLE connection.
    try:
      self.get_current_iteration_metrics().record(
          'file_transfer_throughput_kbps',
          active_snippet.transfer_file(
              file_size_kb=_FILE_TRANSFER_SIZE_KB,
              timeout=_FILE_TRANSFER_TIMEOUT,
              payload_type=_PAYLOAD_TYPE,
              num_files=_FILE_TRANSFER_NUM,
          ),
      )
    finally:
      nc_utils.handle_file_transfer_failure(
          active_snippet.test_failure_reason,
          self.get_current_iteration_metrics(),
          file_transfer_failure_tip=_FILE_TRANSFER_FAILURE_TIP,
      )

    try:
      active_snippet.disconnect_endpoint()
    finally:
      prior_bt_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
