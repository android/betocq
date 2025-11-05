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

"""This test is to test the Wifi SCC with 2G Wifi D2D and 2G STA.

In this case, even though the expected wifi medium is the WFD, but the wifi D2D
could be any technologies, such as WFD, HOTSPOT, WifiLAN; Once the WFD is
failed, other mediums will be tried. Both the D2D and STA are using the same 2G
channel.

Test requirements:
  The device requirements:
    supports_5g=False in config file
    support Wi-Fi Direct
  The AP requirements:
    wifi channel: 6 (2437)

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Connect discoverer to a 2G Wi-Fi network.
  2. Set up a prior Nearby Connection through Bluetooth medium.
  3. Connect advertiser to the same Wi-Fi network.
  4. Set up a connection and upgrade to any available Wi-Fi medium.
      * The expected wifi medium is WFD, but other mediums will be tried if
        WFD is failed.
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

from betocq import nc_constants
from betocq import performance_test_base
from betocq import setup_utils
from betocq import test_result_utils
from betocq.nearby_connection import utils as nc_utils


TEST_ITERATION_NUM = nc_constants.SCC_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = nc_constants.SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = nc_constants.SCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
_FILE_TRANSFER_NUM = 1
_FILE_TRANSFER_SIZE_KB = nc_constants.TRANSFER_FILE_SIZE_20MB
_FILE_TRANSFER_TIMEOUT = nc_constants.WIFI_2G_20M_PAYLOAD_TRANSFER_TIMEOUT
_PAYLOAD_TYPE = nc_constants.PayloadType.FILE
_COUNTRY_CODE = 'US'


_THROUGHPUT_LOW_TIP_RAW = (
    'This is a 2G SCC case. Check with the wifi chip vendor for any firmware'
    ' issue in this mode.'
)
_THROUGHPUT_LOW_TIP = (
    'The upgraded medium is {upgraded_medium_name}.'
    f' {_THROUGHPUT_LOW_TIP_RAW}'
)


_FILE_TRANSFER_FAILURE_TIP = (
    'The upgraded wifi medium {upgraded_medium_name} might be broken,'
    ' check the related log. Or check throughput low tip:'
    f' {_THROUGHPUT_LOW_TIP_RAW}'
)


class Scc2gAllWifiStaTest(performance_test_base.PerformanceTestBase):
  """Test class for Wifi SCC with 2G Wifi D2D and 2G STA."""

  test_runtime: nc_constants.NcTestRuntime
  wifi_info: nc_constants.WifiInfo

  def setup_class(self):
    super().setup_class()

    self.setup_wifi_env(
        d2d_type=nc_constants.WifiD2DType.SCC_2G,
        country_code=_COUNTRY_CODE,
    )
    self.wifi_info = nc_constants.WifiInfo.from_test_parameters(
        d2d_type=nc_constants.WifiD2DType.SCC_2G, params=self.test_parameters
    )
    self.test_runtime = nc_constants.NcTestRuntime(
        advertiser=self.advertiser,
        discoverer=self.discoverer,
        upgrade_medium_under_test=nc_constants.NearbyMedium.UPGRADE_TO_ALL_WIFI,
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
    # Check WiFi AP.
    setup_utils.abort_if_2g_ap_not_ready(self.test_parameters)
    # Check device capabilities.
    setup_utils.abort_if_device_cap_not_match(
        [self.discoverer, self.advertiser], 'supports_5g', expected_value=False
    )

  @base_test.repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=_MAX_CONSECUTIVE_ERROR,
  )
  def test_scc_2g_all_wifi_sta(self):
    """Test the 2G SCC case, both the wifi D2D medium and STA are using 2G."""
    # Test Step: Connect discoverer to wifi sta in case WLAN is used.
    discoverer_sta_op = nc_utils.connect_ad_to_wifi_sta(
        self.discoverer,
        self.wifi_info.discoverer_wifi_ssid,
        self.wifi_info.discoverer_wifi_password,
        self.current_test_result,
        is_discoverer=True,
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

    # Test Step: Set up a NC connection for file transfer.
    active_snippet = nc_utils.start_main_nearby_connection(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        upgrade_medium_under_test=self.test_runtime.upgrade_medium_under_test,
        connect_timeout=nc_constants.DEFAULT_SECOND_CONNECTION_TIMEOUTS,
        test_parameters=self.test_parameters,
    )
    upgraded_medium_name = None
    upgrade_medium = self.current_test_result.quality_info.upgrade_medium
    if upgrade_medium is not None:
      upgraded_medium_name = upgrade_medium.name
    # due to (internal), the file transfer is not stable for wifi LAN medium.
    do_file_transfer = True
    if (
        upgrade_medium == nc_constants.NearbyMedium.WIFILAN_ONLY
        and self.test_parameters.do_nc_wlan_file_transfer_test
    ):
      do_file_transfer = self.test_parameters.do_nc_wlan_file_transfer_test

    if do_file_transfer:
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
            file_transfer_failure_tip=_FILE_TRANSFER_FAILURE_TIP.format(
                upgraded_medium_name=upgraded_medium_name
            ),
        )

      # Collect test metrics and check the transfer medium info regardless of
      # whether the transfer succeeded or not.
      test_result_utils.collect_nc_test_metrics(
          self.current_test_result, self.test_runtime
      )
      test_result_utils.assert_sta_frequency(
          self.current_test_result,
          expected_wifi_type=self.wifi_info.sta_type,
      )
      if upgrade_medium in [
          nc_constants.NearbyConnectionMedium.WIFI_DIRECT,
          nc_constants.NearbyConnectionMedium.WIFI_HOTSPOT,
      ]:
        test_result_utils.assert_p2p_frequency(
            self.current_test_result,
            is_mcc=self.wifi_info.is_mcc,
            is_dbs_mode=self.test_runtime.is_dbs_mode,
        )

    test_result_utils.assert_2g_wifi_throughput_and_run_iperf_if_needed(
        test_result=self.current_test_result,
        nc_test_runtime=self.test_runtime,
        low_throughput_tip=_THROUGHPUT_LOW_TIP.format(
            upgraded_medium_name=upgraded_medium_name
        ),
        did_nc_file_transfer=do_file_transfer,
    )

    prior_bt_snippet.disconnect_endpoint()
    active_snippet.disconnect_endpoint()

    # Wait for the STA to be connected as the 'DISRUPPTIVE' upgrade medium
    # will disconnect the STA during the file transfer.
    setup_utils.wait_for_wifi_auto_join(
        self.discoverer,
        self.wifi_info.discoverer_wifi_ssid,
        self.wifi_info.discoverer_wifi_password,
    )

if __name__ == '__main__':
  test_runner.main()
