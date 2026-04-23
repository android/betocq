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

"""This test is to test the Wifi throughput with DFS 5G STA for WFD.

This is about the feature - using DFS channels for WFD, for details, refer to
https://drive.google.com/file/d/1Aj77Euao8XkvE6uWF15WMK1XCwmYhdxW/view?resourcekey=0-a69XQup8McOcUnzYN9eh0Q
(confidential) and config_wifiEnableStaDfsChannelForPeerNetwork -
https://cs.android.com/android/platform/superproject/main/+/main:packages/modules/Wifi/service/ServiceWifiResources/res/values/config.xml;l=1151
If the feature is disabled for the device, the STA is using the DFS
5G channel, but the WFD will be started in another 5G channel and this will be
a MCC case.
If the feature is enabled for the device, the STA and WFD will use the same
DFS 5G channel and this will be a SCC case.

Test requirements:
  The device requirements:
    support 5G band
    support Wi-Fi Direct
  The AP requirements:
    wifi channel: 52 (5260) or 112 (5560) or other DFS channels.

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Disconnect discoverer from the current connected Wi-Fi network.
  2. Set up a prior Nearby Connection through Bluetooth medium.
  3. Connect advertiser to a 5G DFS Wi-Fi network.
  4. Set up a connection with Wi-Fi Direct as upgrade medium.
      * Wi-Fi Direct will be set up by Nearby Connection in a 5G channel that is
        different from the STA channel for MCC case, or same as STA for SCC
        case.
  5. Transfer file on the connection established in step 4.
  6. Tear down all Nearby Connections.

Expected results:
  1. The file transfer completes successfully.
  2. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
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


# Use MCC strategy for iteration number and max consecutive error,
# as most devices do not support SCC_5G mode in this case.
TEST_ITERATION_NUM = nc_constants.MCC_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = constants.SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = nc_constants.MCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
_FILE_TRANSFER_NUM = 1
_PAYLOAD_TYPE = constants.PayloadType.FILE
_COUNTRY_CODE = 'US'


_FILE_TRANSFER_FAILURE_TIP = (
    'The Wifi Direct connection might be broken, check related logs.'
)


class XccWfdDfs5gStaTest(performance_test_base.PerformanceTestBase):
  """Test class for XCC with 5G WFD and DFS 5G STA.

  This test covers both SCC and MCC scenarios, depending on whether the device
  supports using DFS channels for peer networks when STA is on a DFS channel.
  """

  test_runtime: constants.NcTestRuntime
  wifi_info: constants.WifiInfo

  def setup_class(self) -> None:
    super().setup_class()

    self.setup_wifi_env(
        d2d_type=constants.WifiD2DType.XCC_5G_DFS_STA,
        country_code=_COUNTRY_CODE,
    )
    nc_utils.check_wifi_ap_status_in_setup_class(
        self, self.advertiser, self.test_parameters
    )
    self.wifi_info = constants.WifiInfo.from_test_parameters(
        d2d_type=constants.WifiD2DType.XCC_5G_DFS_STA,
        params=self.test_parameters,
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
    setup_utils.abort_if_5g_band_not_supported(
        [self.discoverer, self.advertiser]
    )
    setup_utils.abort_if_wifi_direct_not_supported(
        [self.discoverer, self.advertiser]
    )

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[
            nc_utils.get_nearby_snippet_config(self.user_params),
            nc_utils.get_nearby2_snippet_config(self.user_params),
        ],
        country_code=self.test_runtime.country_code,
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )

  def _assert_test_conditions(self) -> None:
    """Aborts the test class if any test condition is not met."""
    # Check rooted devices.
    setup_utils.abort_if_on_unrooted_device(
        [self.discoverer, self.advertiser],
        'the country code can not be set.'
    )
    # Check WiFi AP.
    setup_utils.abort_if_dfs_5g_ap_not_ready(self.test_parameters)

  @base_test.repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=_MAX_CONSECUTIVE_ERROR,
  )
  def test_xcc_wfd_dfs_5g_sta(self) -> None:
    """Test the performance for wifi XCC with 5G WFD and DFS 5G STA.

    This test covers both SCC (if enable_sta_dfs_channel_for_peer_network is
    supported) and MCC (otherwise) scenarios.
    """
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
        self.advertiser, self.current_test_result
    )
    wifi_concurrency_mode = setup_utils.get_wifi_concurrency_mode(
        p2p_frequency=self.current_test_result.quality_info.medium_frequency,
        sta_frequency=self.current_test_result.sta_frequency,
    )
    test_result_utils.set_and_assert_concurrency_mode(
        current_concurrency_mode=wifi_concurrency_mode,
        valid_concurrency_modes=[
            constants.WifiConcurrencyMode.SCC_5G,
            constants.WifiConcurrencyMode.MCC_5G_P2P_5G_STA,
            constants.WifiConcurrencyMode.UNKNOWN,
        ],
        test_result=self.current_test_result,
        additional_error_message=(
            'If enable_sta_dfs_channel_for_peer_network=False, concurrency'
            ' should be'
            f' {constants.WifiConcurrencyMode.MCC_5G_P2P_5G_STA.name},'
            f' otherwise {constants.WifiConcurrencyMode.SCC_5G.name}. If'
            ' not, something is wrong with the firmware of the device.'
        ),
    )
    self.advertiser.log.info(
        'p2p_frequency: %s, sta_frequency: %s, wifi_concurrency_mode: %s',
        self.current_test_result.quality_info.medium_frequency,
        self.current_test_result.sta_frequency,
        wifi_concurrency_mode.name,
    )

    file_transfer_size_kb = (
        nc_constants.NC_MCC_5G_D2D_5G_STA_TRANSFER_FILE_SIZE_KB
    )
    file_transfer_timeout = constants.WIFI_100M_PAYLOAD_TRANSFER_TIMEOUT
    if wifi_concurrency_mode == constants.WifiConcurrencyMode.SCC_5G:
      file_transfer_size_kb = constants.TRANSFER_FILE_SIZE_500MB
      file_transfer_timeout = constants.WIFI_500M_PAYLOAD_TRANSFER_TIMEOUT

    # Test Step: Transfer file on the established NC.
    try:
      if wifi_concurrency_mode is not constants.WifiConcurrencyMode.UNKNOWN:
        single_file_transfer_throughput_kbps = active_snippet.transfer_file(
            file_size_kb=file_transfer_size_kb,
            timeout=file_transfer_timeout,
            payload_type=_PAYLOAD_TYPE,
            num_files=_FILE_TRANSFER_NUM,
        )
      else:
        # Workaround to get the throughput in the unknown concurrency mode,
        # although this is not expected to happen (P2P freq is not gotten?).
        single_file_transfer_throughput_kbps = (
            active_snippet.transfer_file_for_unknown_concurrency_mode(
                mcc_file_size_kb=(
                    nc_constants.NC_MCC_5G_D2D_5G_STA_TRANSFER_FILE_SIZE_KB
                ),
                mcc_timeout=constants.WIFI_100M_PAYLOAD_TRANSFER_TIMEOUT,
                scc_file_size_kb=nc_constants.NC_SCC_5G_TRANSFER_FILE_SIZE_KB,
                scc_timeout=constants.WIFI_500M_PAYLOAD_TRANSFER_TIMEOUT,
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
