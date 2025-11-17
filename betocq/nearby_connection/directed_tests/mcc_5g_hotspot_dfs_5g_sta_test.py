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

"""This test is to test the Wifi MCC with 5G HOTSPOT and DFS 5G STA.

This is about the feature - using DFS channels for Hotspot, for details, refer
to
https://drive.google.com/file/d/1Aj77Euao8XkvE6uWF15WMK1XCwmYhdxW/view?resourcekey=0-a69XQup8McOcUnzYN9eh0Q
(confidential) and config_wifiEnableStaDfsChannelForPeerNetwork -
https://cs.android.com/android/platform/superproject/main/+/main:packages/modules/Wifi/service/ServiceWifiResources/res/values/config.xml;l=1151
In this case, the feature is disabled for the device; The STA is using the DFS
5G channel, but the hotspot will be started in another non DFS 5G channel.

For hotspot medium, the target device enables WFD GO + STA and the source device
enables STA which tries to connect to WFD GO.

Test requirements:
  The device requirements:
    supports_5g=True in config file
    support Wi-Fi Direct
    (target device only) enable_sta_dfs_channel_for_peer_network=False in config
      file
  The AP requirements:
    wifi channel: 52 (5260)

Test preparations:
  Set country code to GB on Android devices.

Test steps:
  1. Disconnect discoverer from the current connected Wi-Fi network.
  2. Set up a prior Nearby Connection through Bluetooth medium.
  3. Connect advertiser to the 5G DFS Wi-Fi network.
  4. Set up a connection with Wi-Fi Direct as upgrade medium.
      * Nearby Connection will enable WFD GO + STA on the target device
        and STA on the source device which tries to connect to WFD GO.
  5. Transfer file on the connection established in step 4.
  6. Tear down all Nearby Connections.

Expected results:
  1. The file transfer completes and throughput meets the target. The
     target is calculated according to the device capabilities.
  2. The Wi-Fi STA frequency is a 5G DFS frequency.
  3. The Wi-Fi P2P frequency is different from the STA frequency.
  4. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
     success rate of no less than `SUCCESS_RATE_TARGET`.
"""

import time

from mobly import base_test
from mobly import test_runner
from mobly import utils
from mobly.controllers import android_device

from betocq import nc_constants
from betocq import performance_test_base
from betocq import setup_utils
from betocq import test_result_utils
from betocq.nearby_connection import utils as nc_utils


TEST_ITERATION_NUM = nc_constants.MCC_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = nc_constants.MCC_HOTSPOT_TEST_SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = nc_constants.MCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
_FILE_TRANSFER_NUM = 1
_FILE_TRANSFER_SIZE_KB = nc_constants.TRANSFER_FILE_SIZE_100MB
_FILE_TRANSFER_TIMEOUT = nc_constants.WIFI_100M_PAYLOAD_TRANSFER_TIMEOUT
_PAYLOAD_TYPE = nc_constants.PayloadType.FILE
_COUNTRY_CODE = 'GB'


_THROUGHPUT_LOW_TIP = (
    'This is a MCC test case where hotspot uses a 5G non-DFS channel and STA'
    ' uses a 5G DFS channel. Note that in hotspot mode, the target acts as a'
    ' WFD GO while the source device acts as the legacy STA. Check with the'
    ' wifi chip vendor about the possible firmware Tx/Rx issues in MCC mode. FW'
    ' may set a suboptimal duty cycle on source or target sides. Tuning the'
    ' duty cycle parameters may improve the throughput.'
)


_FILE_TRANSFER_FAILURE_TIP = (
    'The Wifi Hotspot connection might be broken, check related logs.'
    f' {_THROUGHPUT_LOW_TIP}'
)


class Mcc5gHotspotDfs5gStaTest(performance_test_base.PerformanceTestBase):
  """Test class for MCC with 5G HOTSPOT and DFS 5G STA."""

  test_runtime: nc_constants.NcTestRuntime
  wifi_info: nc_constants.WifiInfo

  def setup_class(self):
    super().setup_class()

    self.setup_wifi_env(
        d2d_type=nc_constants.WifiD2DType.MCC_5G_HS_5G_DFS_STA,
        country_code=_COUNTRY_CODE,
    )
    self.wifi_info = nc_constants.WifiInfo.from_test_parameters(
        d2d_type=nc_constants.WifiD2DType.MCC_5G_HS_5G_DFS_STA,
        params=self.test_parameters,
    )
    self.test_runtime = nc_constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        upgrade_medium_under_test=(
            nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT
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
    setup_utils.abort_if_wifi_hotspot_not_supported(
        [self.discoverer, self.advertiser]
    )

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    # Load an extra snippet instance nearby2 for the prior BT connection.
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[self.nearby_snippet_config, self.nearby2_snippet_config],
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
    setup_utils.abort_if_dfs_5g_ap_not_ready(self.test_parameters)
    # Check device capabilities.
    setup_utils.abort_if_device_cap_not_match(
        [self.discoverer, self.advertiser], 'supports_5g', expected_value=True
    )
    setup_utils.abort_if_device_cap_not_match(
        [self.advertiser],
        'enable_sta_dfs_channel_for_peer_network',
        expected_value=False,
    )

  @base_test.repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=_MAX_CONSECUTIVE_ERROR,
  )
  def test_mcc_5g_hotspot_dfs_5g_sta(self):
    """Test the performance for wifi MCC with 5G HOTSPOT and DFS 5G STA."""
    # Test Step: Disconnect discoverer from the current connected wifi sta.
    discoverer_wifi_disconnected = (
        setup_utils.remove_current_connected_wifi_network(self.discoverer)
    )

    # Test Step: Set up a prior BT connection.
    prior_bt_snippet = nc_utils.start_prior_bt_nearby_connection(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        test_parameters=self.test_parameters,
    )

    # Test Step: Connect advertiser to wifi sta.
    advertiser_wifi_connected = nc_utils.connect_ad_to_wifi_sta(
        self.advertiser,
        self.wifi_info.advertiser_wifi_ssid,
        self.wifi_info.advertiser_wifi_password,
        self.current_test_result,
        is_discoverer=False,
    )
    if discoverer_wifi_disconnected or advertiser_wifi_connected:
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
        connect_timeout=nc_constants.DEFAULT_SECOND_CONNECTION_TIMEOUTS,
        test_parameters=self.test_parameters,
    )

    test_result_utils.set_and_assert_p2p_frequency(
        self.advertiser,
        self.current_test_result,
        self.wifi_info.is_mcc,
        self.test_runtime.is_dbs_mode,
        sta_frequency=self.current_test_result.sta_frequency,
        additional_error_message=(
            'Check if enable_sta_dfs_channel_for_peer_network is really False'
            ' for the target device. If yes, the device violate the regulation'
            ' of Wi-Fi 5G DFS channel. You may work with the chipset vendor.'
        ),
    )

    # Test Step: Transfer file on the established NC.
    try:
      self.current_test_result.file_transfer_throughput_kbps = (
          active_snippet.transfer_file(
              file_size_kb=_FILE_TRANSFER_SIZE_KB,
              timeout=_FILE_TRANSFER_TIMEOUT,
              payload_type=_PAYLOAD_TYPE,
              num_files=_FILE_TRANSFER_NUM,
          )
      )
    finally:
      nc_utils.handle_file_transfer_failure(
          active_snippet.test_failure_reason,
          self.current_test_result,
          file_transfer_failure_tip=_FILE_TRANSFER_FAILURE_TIP,
      )

    # Check the throughput and run iperf if needed.
    test_result_utils.assert_5g_wifi_throughput_and_run_iperf_if_needed(
        test_result=self.current_test_result,
        nc_test_runtime=self.test_runtime,
        low_throughput_tip=_THROUGHPUT_LOW_TIP,
    )

    prior_bt_snippet.disconnect_endpoint()
    active_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
