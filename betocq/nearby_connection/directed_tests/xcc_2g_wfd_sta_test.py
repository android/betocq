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

"""This test is to test the WFD medium with 2G channel and Country code 00.

In this case, the STA is using the 2G channel; and the WFD is expected to use
the 2G channel as well in the world wide country code '00'. but allow 5G channel
in case the device does not follow the world wide country code wifi channel.

Test requirements:
  The device requirements
    support Wi-Fi Direct
  The AP requirements:
    Wi-Fi channel: 6 (2437) or other 2G channels.

Test preparations:
  Set country code to '00' on Android devices.

Test steps:
  1. Disconnect discoverer from the current connected Wi-Fi network.
  2. Set up a prior Nearby Connection through Bluetooth medium.
  3. Connect advertiser to the 2.4G Wi-Fi network.
  4. Set up a connection with Wi-Fi Direct as upgrade medium.
  5. Transfer file on the connection established in step 4.
  6. Tear down all Nearby Connections.

Expected results:
  1. The file transfer completes and throughput meets the target. The
     target is calculated according to the device capabilities.
  2. The Wi-Fi STA frequency is a 2G frequency.
  3. The Wi-Fi P2P frequency is the same as the STA frequency.
  4. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
     success rate of no less than `SUCCESS_RATE_TARGET`.
"""

import time

from mobly import base_test
from mobly import test_runner
from mobly import utils
from mobly.controllers import android_device

from betocq import constants
from betocq import performance_test_base
from betocq import setup_utils
from betocq import test_result_utils
from betocq.nearby_connection import nc_constants
from betocq.nearby_connection import utils as nc_utils


# use the SCC test count as most devices should be in SCC mode, except the
# device does not follow the world wide country code wifi channel, which will be
# MCC mode.
TEST_ITERATION_NUM = constants.SCC_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = constants.SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = constants.SCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
_FILE_TRANSFER_NUM = 1
_PAYLOAD_TYPE = constants.PayloadType.FILE
_COUNTRY_CODE = '00'


_THROUGHPUT_LOW_TIP = (
    'This is a SCC 2G test case with WFD medium. Check with the wifi chip'
    ' vendor about the possible firmware Tx/Rx issues in this mode.'
)


_FILE_TRANSFER_FAILURE_TIP = (
    'The Wifi Direct connection might be broken, check related logs.'
)


class Xcc2gWfdStaTest(performance_test_base.PerformanceTestBase):
  """Test class for Wifi XCC with 2G STA.

  This test  covers both SCC(if WFD is 2G) or MCC(if WFD is 5G) scenarios.
  """

  test_runtime: constants.NcTestRuntime
  wifi_info: constants.WifiInfo

  def setup_class(self):
    super().setup_class()

    self.setup_wifi_env(
        d2d_type=constants.WifiD2DType.SCC_2G, country_code=_COUNTRY_CODE
    )
    nc_utils.check_wifi_ap_status_in_setup_class(
        self, self.advertiser, self.test_parameters
    )
    self.wifi_info = constants.WifiInfo.from_test_parameters(
        d2d_type=constants.WifiD2DType.XCC_2G_STA, params=self.test_parameters
    )
    self.test_runtime = constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        upgrade_medium_under_test=(
            constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT
        ),
        country_code=_COUNTRY_CODE,
        wifi_info=self.wifi_info,
    )

    self.test_results.test_iterations_expected = TEST_ITERATION_NUM
    self.test_results.success_rate_target = SUCCESS_RATE_TARGET
    self.test_results.nc_test_runtime = self.test_runtime

    # Test specific device setup steps.
    utils.concurrent_exec(
        self._setup_android_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    # Check device capabilities.
    setup_utils.abort_if_wifi_direct_not_supported(
        [self.discoverer, self.advertiser]
    )

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    # Load an extra snippet instance nearby2 for the prior BT connection.
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[
            nc_utils.get_nearby_snippet_config(self.user_params),
            nc_utils.get_nearby2_snippet_config(self.user_params),
        ],
        country_code=self.test_runtime.country_code,
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )

  def _assert_test_conditions(self):
    """Aborts the test class if any test condition is not met."""
    # Check rooted devices.
    setup_utils.abort_if_on_unrooted_device(
        [self.discoverer, self.advertiser],
        'the country code can not be set.'
    )
    # Check WiFi AP.
    setup_utils.abort_if_2g_ap_not_ready(self.test_parameters)

  @base_test.repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=_MAX_CONSECUTIVE_ERROR,
  )
  def test_xcc_2g_wfd_sta(self):
    """Test the performance for Wifi SCC with 2G WFD and STA."""
    # Test Step: Disconnect discoverer from the current connected wifi sta.
    discoverer_sta_op = setup_utils.remove_current_connected_wifi_network(
        self.discoverer
    )

    # Test Step: Set up a prior BT connection.
    prior_bt_snippet = nc_utils.start_prior_bt_nearby_connection(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        test_parameters=self.test_parameters,
    )

    # Test Step: Connect advertiser to wifi sta.
    advertiser_sta_op = nc_utils.connect_ad_to_wifi_sta(
        self.advertiser,
        self.wifi_info.advertiser_wifi_ssid,
        self.wifi_info.advertiser_wifi_password,
        self.current_test_result,
        is_discoverer=False,
    )
    if discoverer_sta_op or advertiser_sta_op:
      # Let scan, DHCP and internet validation complete before NC.
      # This is important especially for the transfer speed or WLAN test.
      time.sleep(self.test_parameters.target_post_wifi_connection_idle_time_sec)

    test_result_utils.set_and_assert_sta_frequency(
        self.advertiser,
        self.current_test_result,
        self.wifi_info.sta_type,
    )

    # Test Step: Set up a NC connection for file transfer.
    active_snippet = nc_utils.start_main_nearby_connection(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        upgrade_medium_under_test=self.test_runtime.upgrade_medium_under_test,
        connect_timeout=constants.DEFAULT_SECOND_CONNECTION_TIMEOUTS,
        test_parameters=self.test_parameters,
    )

    test_result_utils.populate_medium_frequency(
        self.advertiser,
        self.current_test_result,
    )
    wifi_concurrency_mode = setup_utils.get_wifi_concurrency_mode(
        p2p_frequency=self.current_test_result.quality_info.medium_frequency,
        sta_frequency=self.current_test_result.sta_frequency,
    )

    test_result_utils.set_and_assert_concurrency_mode(
        current_concurrency_mode=wifi_concurrency_mode,
        valid_concurrency_modes=[
            constants.WifiConcurrencyMode.SCC_2G,
            constants.WifiConcurrencyMode.MCC_5G_P2P_2G_STA,
            constants.WifiConcurrencyMode.UNKNOWN,
        ],
        test_result=self.current_test_result,
        additional_error_message=(
            'In world wide country code, WFD should use the 2G channel, but the'
            ' device may use the 5G channel as well if the device does not'
            ' follow the world wide country code wifi channel. You may work'
            ' with your wifi chipset vendor to fix this frequency selection'
            ' issue.'
        ),
    )
    self.advertiser.log.info(
        'p2p_frequency: %s, sta_frequency: %s, wifi_concurrency_mode: %s',
        self.current_test_result.quality_info.medium_frequency,
        self.current_test_result.sta_frequency,
        wifi_concurrency_mode.name,
    )

    file_transfer_file_size_kb = nc_constants.NC_SCC_2G_TRANSFER_FILE_SIZE_KB
    file_transfer_timeout = constants.WIFI_2G_20M_PAYLOAD_TRANSFER_TIMEOUT
    if wifi_concurrency_mode == constants.WifiConcurrencyMode.MCC_5G_P2P_2G_STA:
      file_transfer_file_size_kb = (
          nc_constants.NC_MCC_5G_D2D_2G_STA_TRANSFER_FILE_SIZE_KB
      )
      file_transfer_timeout = constants.WIFI_100M_PAYLOAD_TRANSFER_TIMEOUT

    # Test Step: Transfer file on the established NC.
    try:
      if wifi_concurrency_mode is not constants.WifiConcurrencyMode.UNKNOWN:
        single_file_transfer_throughput_kbps = (
            active_snippet.transfer_file(
                file_size_kb=file_transfer_file_size_kb,
                timeout=file_transfer_timeout,
                payload_type=_PAYLOAD_TYPE,
                num_files=_FILE_TRANSFER_NUM,
            )
        )
      else:
        self.advertiser.log.warning(
            'The concurrency mode is unknown, this should not happen, '
            'workaround to get the throughput in the unknown concurrency mode.'
        )
        # TODO: refactor transfer_file_for_unknown_concurrency_mode
        # to use low high throughput mode, not mcc/scc mode.
        single_file_transfer_throughput_kbps = (
            active_snippet.transfer_file_for_unknown_concurrency_mode(
                mcc_file_size_kb=nc_constants.NC_SCC_2G_TRANSFER_FILE_SIZE_KB,
                mcc_timeout=constants.WIFI_2G_20M_PAYLOAD_TRANSFER_TIMEOUT,
                scc_file_size_kb=nc_constants.NC_MCC_5G_D2D_2G_STA_TRANSFER_FILE_SIZE_KB,
                scc_timeout=constants.WIFI_100M_PAYLOAD_TRANSFER_TIMEOUT,
                payload_type=_PAYLOAD_TYPE,
            )
        )

      self.current_test_result.file_transfer_throughput_kbps = (
          single_file_transfer_throughput_kbps
      )
      self.discoverer.log.info(
          'single_file_transfer_throughput_kbps: %s',
          single_file_transfer_throughput_kbps
      )
    finally:
      nc_utils.handle_file_transfer_failure(
          active_snippet.test_failure_reason,
          self.current_test_result,
          file_transfer_failure_tip=_FILE_TRANSFER_FAILURE_TIP,
      )

    prior_bt_snippet.disconnect_endpoint()
    active_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
