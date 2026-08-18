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

"""This test is to test the Wifi AWARE R4 in a general case using V3 APIs.


Test requirements:
  The device requirements:
    support 5G band
    support Wi-Fi Aware R4
  The AP requirements:
    Wi-Fi channel: 36 (5180) or other 5G Non-DFS channels.

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Connect discoverer to a 5G non-DFS Wi-Fi network.
  2. Set up a connection with Wi-Fi Aware as upgrade medium.
      * Wi-Fi Aware will be set up by Nearby Connection in the channel of
        5180MHz.
  3. Transfer file.
  4. Tear down the connection.

Expected results:
  1. The medium was successfully upgraded to Wi-Fi Aware.
  2. The file transfer completes and throughput meets the target. The
     target is calculated according to the device capabilities.
  3. The Wi-Fi STA frequency is a 5G non-DFS frequency.
  4. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
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
from betocq.nearby_connection import nc_test_result_utils
from betocq.nearby_connection import utils as nc_utils

TEST_ITERATION_NUM = constants.WIFI_AWARE_SCC_PERFORMANCE_TEST_COUNT
_MAX_CONSECUTIVE_ERROR = constants.SCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
_PAYLOAD_REQUEST_SIZE_KB = constants.TRANSFER_FILE_SIZE_10KB
_PAYLOAD_FILES_RESPONSE_SIZE_KB = constants.TRANSFER_FILE_SIZE_500MB
_PAYLOAD_TRANSFER_TIMEOUT = constants.WIFI_500M_PAYLOAD_TRANSFER_TIMEOUT
_V3_PAYLOAD_TYPE = nc_constants.V3PayloadType.REQUEST
_COUNTRY_CODE = 'US'
_SUPPORTED_SERVICES = nc_constants.SupportedServicesEnum.DATA_MIGRATION
_MIN_GMS_VERSION = 262600000
_V3_AWARE_ON_OVERRIDES = (
    '//wireless/android/platform/testing/bettertogether/betocq:nc_v3_aware_on_overrides'
)

_THROUGHPUT_LOW_TIP = (
    'This is 5G Aware test case. Check with the wifi chip vendor if Aware is'
    ' supported correctly.'
)


_PAYLOAD_TRANSFER_FAILURE_TIP = (
    'The Wifi Aware connection might be broken, check related logs. '
)


class Aware5gStaV3Test(nc_performance_test_base.NcPerformanceTestBase):

  test_runtime: constants.NcTestRuntime
  wifi_info: constants.WifiInfo

  @override
  def setup_class(self) -> None:
    super().setup_class()

    self.setup_wifi_env(
        d2d_type=constants.WifiD2DType.SCC_5G, country_code=_COUNTRY_CODE
    )
    # Test configurations.
    self.wifi_info = constants.WifiInfo.from_test_parameters(
        d2d_type=constants.WifiD2DType.SCC_5G, params=self.test_parameters
    )
    self.test_runtime = constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        connection_medium=constants.NearbyMedium.BLE_ONLY,
        upgrade_medium_under_test=constants.NearbyMedium.WIFIAWARE_ONLY,
        country_code=_COUNTRY_CODE,
        is_dbs_mode=False,
        wifi_info=self.wifi_info,
        is_discoverer_network_owner=True,
    )

    # Test specific device setup steps.
    utils.concurrent_exec(
        self._setup_android_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    # Check device capabilities.
    setup_utils.abort_if_gms_version_less_than(self.ads, _MIN_GMS_VERSION)
    setup_utils.abort_if_extension_less_than(self.ads, 's', 17)
    setup_utils.abort_if_5g_band_not_supported(
        [self.discoverer, self.advertiser]
    )
    setup_utils.abort_if_wifi_aware_pairing_not_supported(
        [self.discoverer, self.advertiser]
    )
    nc_utils.check_wifi_ap_status_in_setup_class(
        self, self.advertiser, self.test_parameters, supports_5g=True
    )

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[nc_utils.get_nearby_snippet_config(self.user_params)],
        country_code=self.test_runtime.country_code,
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )
    setup_utils.install_overrides(
        ad, self.current_test_info.output_path, _V3_AWARE_ON_OVERRIDES, False
    )

  def _assert_test_conditions(self):
    # Check WiFi AP.
    setup_utils.abort_if_5g_ap_not_ready(self.test_parameters)

  @setup_utils.betocq_repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=_MAX_CONSECUTIVE_ERROR,
  )
  def test_aware_r4_5g_sta(self):

    # only connect discoverer to wifi as advertiser will connect to wifi
    # during wifi credentials transfer.
    nc_utils.connect_ad_to_wifi_sta(
        self.discoverer,
        wifi_ssid=self.wifi_info.discoverer_wifi_ssid,
        wifi_password=self.wifi_info.discoverer_wifi_password,
        metrics=self.get_current_iteration_metrics(),
        is_discoverer=True,
    )
    nc_test_result_utils.set_and_assert_sta_frequency(
        self.discoverer,
        metrics=self.get_current_iteration_metrics(),
        expected_wifi_type=self.wifi_info.sta_type,
        prefix='discoverer_',
    )

    # Test Step: Set up a NC connection for file transfer.
    active_snippet = nc_utils.start_main_nearby_connection_v3(
        self.advertiser,
        self.discoverer,
        metrics=self.get_current_iteration_metrics(),
        connection_medium=constants.NearbyMedium.BLE_ONLY,
        upgrade_medium_under_test=self.test_runtime.upgrade_medium_under_test,
        connect_timeout=constants.DEFAULT_FIRST_CONNECTION_TIMEOUTS,
        supported_services=_SUPPORTED_SERVICES,
    )

    # Let wifi aware slot update complete before the transfer.
    # This is important especially for the transfer speed test.
    # time.sleep(
    #     constants.WIFI_AWARE_AFTER_CONNECTION_START_THROUGHPUT_WAIT_TIME_SEC
    #     .total_seconds()
    # )

    # Test Step: Transfer file on the established NC.
    try:
      throughput = active_snippet.transfer_file(
          payload_size_kb=_PAYLOAD_REQUEST_SIZE_KB,
          timeout=_PAYLOAD_TRANSFER_TIMEOUT,
          payload_type=_V3_PAYLOAD_TYPE,
          response_payload_type=nc_constants.V3PayloadType.FILES_RESPONSE,
          response_size_kb=_PAYLOAD_FILES_RESPONSE_SIZE_KB,
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

      # Collect test metrics and check the transfer medium info regardless of
      # whether the transfer succeeded or not.
      # TODO: do we need this ?
      nc_test_result_utils.collect_nc_test_metrics(
          self.get_current_iteration_metrics(), self.test_runtime
      )

    active_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
