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

"""This test is to test the BLE performance.

Test requirements:
  The device requirements:
    support BLE
  The AP requirements:
    None

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Set up a connection with BLE as advertising and connection medium.
  2. Transfer payload.
  3. Tear down the connection.

Expected results:
  1. The file transfer completes and throughput meets the target.
  2. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
     success rate of no less than `SUCCESS_RATE_TARGET`.
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

TEST_ITERATION_NUM = nc_constants.BT_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = constants.BLE_PERFORMANCE_TEST_SUCCESS_RATE_TARGET
MAX_CONSECUTIVE_ERROR = nc_constants.BT_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
_PAYLOAD_TRANSFER_NUM = 1
_PAYLOAD_TRANSFER_SIZE_KB = constants.TRANSFER_FILE_SIZE_1KB
_PAYLOAD_TRANSFER_TIMEOUT = constants.BLE_20K_PAYLOAD_TRANSFER_TIMEOUT
_SUPPORTED_SERVICES = nc_constants.SupportedServicesEnum.SETTINGS_ESIM
_PAYLOAD_TYPE = constants.PayloadType.BYTES
_V3_ON_OVERRIDES = (
    '//wireless/android/platform/testing/bettertogether/betocq:nc_v3_on_overrides'
)



_THROUGHPUT_LOW_TIP = (
    'Check with the chip vendor if there is any BT firmware issue.'
)


_PAYLOAD_TRANSFER_FAILURE_TIP = (
    'The BLE connection might be broken, check related logs.'
    f' {_THROUGHPUT_LOW_TIP}'
)


class BlePerformanceV3Test(nc_performance_test_base.NcPerformanceTestBase):

  test_runtime: constants.NcTestRuntime
  wifi_info: constants.WifiInfo

  @override
  def setup_class(self) -> None:
    super().setup_class()
    self.test_runtime = constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        connection_medium=constants.NearbyMedium.BLE_ONLY,
        upgrade_medium_under_test=constants.NearbyMedium.BLE_ONLY,
        is_dbs_mode=False,
        wifi_info=None,
        is_discoverer_network_owner=True,
    )

    # Test specific device setup steps.
    utils.concurrent_exec(
        self._setup_android_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[nc_utils.get_nearby_snippet_config(self.user_params)],
        country_code=self.test_runtime.country_code,
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )
    setup_utils.install_overrides(
        ad, self.current_test_info.output_path, _V3_ON_OVERRIDES, False
    )

  @setup_utils.betocq_repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=MAX_CONSECUTIVE_ERROR,
  )
  def test_ble_performance(self):
    active_snippet = nc_utils.start_main_nearby_connection_v3(
        self.advertiser,
        self.discoverer,
        metrics=self.get_current_iteration_metrics(),
        connection_medium=self.test_runtime.connection_medium,
        upgrade_medium_under_test=self.test_runtime.upgrade_medium_under_test,
        connect_timeout=constants.DEFAULT_FIRST_CONNECTION_TIMEOUTS,
        supported_services=_SUPPORTED_SERVICES.value,
    )

    # Test Step: Transfer payload on the established NC.
    try:
      throughput = active_snippet.transfer_file(
          payload_size_kb=_PAYLOAD_TRANSFER_SIZE_KB,
          timeout=_PAYLOAD_TRANSFER_TIMEOUT,
          payload_type=_PAYLOAD_TYPE,
          num_files=_PAYLOAD_TRANSFER_NUM,
      )
      self.get_current_iteration_metrics().record(
          'file_transfer_throughput_kbps', throughput
      )
    finally:
      nc_utils.handle_file_transfer_failure(
          active_snippet.test_failure_reason,
          self.get_current_iteration_metrics(),
          file_transfer_failure_tip=_PAYLOAD_TRANSFER_FAILURE_TIP,
      )

    active_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
