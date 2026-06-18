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

"""Test the Wifi MCC case with 5G WFD and 2G STA with non-DBS-capable devices.

In this case, the WFD is using the 5G channel, but STA is connected to 2G
channel, as the device (don't support DBS) can not handle the 5G and 2G at
the same time, there is concurrent contention for the 5G channel and 2G
channel handling in firmware, the firmware needs to switch 5G and 2G from time
to time.

Test requirements:
  The device requirements:
    support 5G band
    support Wi-Fi Direct
    (target device only) supports_dbs_sta_wfd=False in config file
  The AP requirements:
    wifi channel: 6 (2437) or other 2G channels.

Test preparations:
  Set country code to US on Android devices.

Test steps:
  1. Disconnect discoverer from the current connected Wi-Fi network.
  2. Set up a prior Nearby Connection through Bluetooth medium.
  3. Connect advertiser to the 2.4G Wi-Fi network.
  4. Set up a connection with Wi-Fi Direct as upgrade medium.
      * Wi-Fi Direct will be set up by Nearby Connection in a 5G channel.
  5. Transfer file on the connection established in step 4.
  6. Tear down all Nearby Connections.

Expected results:
  1. The file transfer completes and throughput meets the target. The
     target is calculated according to the device capabilities.
  2. The Wi-Fi STA frequency is a 2G frequency.
  3. The Wi-Fi P2P frequency is different from the STA frequency.
  4. This test will be repeated for `TEST_ITERATION_NUM` times, requiring a
     success rate of no less than `SUCCESS_RATE_TARGET`.
"""

import time

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


TEST_ITERATION_NUM = nc_constants.MCC_PERFORMANCE_TEST_COUNT
SUCCESS_RATE_TARGET = constants.SUCCESS_RATE_TARGET
_MAX_CONSECUTIVE_ERROR = nc_constants.MCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR
_FILE_TRANSFER_NUM = 1
_FILE_TRANSFER_SIZE_KB = (
    nc_constants.NC_MCC_5G_D2D_2G_STA_TRANSFER_FILE_SIZE_KB
)
_FILE_TRANSFER_TIMEOUT = constants.WIFI_100M_PAYLOAD_TRANSFER_TIMEOUT
_PAYLOAD_TYPE = constants.PayloadType.FILE
_COUNTRY_CODE = 'US'


_THROUGHPUT_LOW_TIP = (
    'This is a MCC test case where WFD uses a 5G channel and STA uses a 2G'
    ' channel. Check with the wifi chip vendor about the possible firmware'
    ' Tx/Rx issues in MCC mode.'
)


_FILE_TRANSFER_FAILURE_TIP = (
    'The Wifi Direct connection might be broken, check related logs.'
)


class Mcc5gWfdNonDbs2gStaTest(nc_performance_test_base.NcPerformanceTestBase):
  """Test class for MCC case with 5G WFD and 2G STA."""

  test_runtime: constants.NcTestRuntime
  wifi_info: constants.WifiInfo

  @override
  def get_success_rate(self, scenario_name: str) -> float:
    """Returns the expected success rate target."""
    del self, scenario_name  # Unused in this implementation.
    return SUCCESS_RATE_TARGET

  def _get_advertiser_sta_frequency(self) -> int:
    """Gets the advertiser STA frequency from the current iteration metrics."""
    sta_freq_metric = self.get_current_iteration_metrics().get(
        'advertiser_sta_frequency'
    )
    return sta_freq_metric.value if sta_freq_metric else constants.INVALID_INT

  @override
  def setup_class(self):
    """Sets up the test class and test runtime environment."""
    super().setup_class()

    self.setup_wifi_env(
        d2d_type=constants.WifiD2DType.MCC_5G_WFD_2G_STA,
        country_code=_COUNTRY_CODE,
    )
    nc_utils.check_wifi_ap_status_in_setup_class(
        self, self.advertiser, self.test_parameters
    )
    self.wifi_info = constants.WifiInfo.from_test_parameters(
        d2d_type=constants.WifiD2DType.MCC_5G_WFD_2G_STA,
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
    """Configures snippets and settings for an Android device."""
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
    # Check WiFi AP.
    setup_utils.abort_if_2g_ap_not_ready(self.test_parameters)
    # Check device capabilities.
    setup_utils.abort_if_device_cap_not_match(
        [self.advertiser], 'supports_dbs_sta_wfd', expected_value=False
    )

  @setup_utils.betocq_repeat(
      count=TEST_ITERATION_NUM,
      max_consecutive_error=_MAX_CONSECUTIVE_ERROR,
  )
  def test_mcc_5g_wfd_non_dbs_2g_sta(self):
    """Test the performance for wifi MCC with 5G WFD and 2G STA."""
    # Test Step: Disconnect discoverer from the current connected wifi sta.
    discoverer_sta_op = setup_utils.remove_current_connected_wifi_network(
        self.discoverer
    )

    # Test Step: Set up a prior BT connection.
    prior_bt_snippet = nc_utils.start_prior_bt_nearby_connection(
        self.advertiser,
        self.discoverer,
        metrics=self.get_current_iteration_metrics(),
        test_parameters=self.test_parameters,
    )

    # Test Step: Connect advertiser to wifi sta.
    advertiser_sta_op = nc_utils.connect_ad_to_wifi_sta(
        self.advertiser,
        wifi_ssid=self.wifi_info.advertiser_wifi_ssid,
        wifi_password=self.wifi_info.advertiser_wifi_password,
        metrics=self.get_current_iteration_metrics(),
        is_discoverer=False,
    )
    if discoverer_sta_op or advertiser_sta_op:
      # Let scan, DHCP and internet validation complete before NC.
      # This is important especially for the transfer speed or WLAN test.
      time.sleep(self.test_parameters.target_post_wifi_connection_idle_time_sec)

    nc_test_result_utils.set_and_assert_sta_frequency(
        self.advertiser,
        self.get_current_iteration_metrics(),
        self.wifi_info.sta_type,
        prefix='advertiser_',
    )

    # Test Step: Set up a NC connection for file transfer.
    active_snippet = nc_utils.start_main_nearby_connection(
        self.advertiser,
        self.discoverer,
        metrics=self.get_current_iteration_metrics(),
        upgrade_medium_under_test=self.test_runtime.upgrade_medium_under_test,
        connect_timeout=constants.DEFAULT_SECOND_CONNECTION_TIMEOUTS,
        test_parameters=self.test_parameters,
    )

    nc_test_result_utils.set_and_assert_p2p_frequency(
        self.advertiser,
        self.get_current_iteration_metrics(),
        is_mcc=self.wifi_info.is_mcc,
        is_dbs_mode=self.test_runtime.is_dbs_mode,
        sta_frequency=self._get_advertiser_sta_frequency(),
        additional_error_message=(
            'Check if supports_dbs_sta_wfd is really false for the target'
            ' device. If yes, it is a real issue to be fixed.'
            ' You may work with the chipset vendor.'
        ),
    )

    # Test Step: Transfer file on the established NC.
    try:
      self.get_current_iteration_metrics().record(
          'file_transfer_throughput_kbps',
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
          self.get_current_iteration_metrics(),
          file_transfer_failure_tip=_FILE_TRANSFER_FAILURE_TIP,
      )

    # Check the throughput and run iperf if needed.
    if not self.test_parameters.skip_throughput_assertion:
      nc_test_result_utils.assert_5g_wifi_throughput_and_run_iperf_if_needed(
          metrics=self.get_current_iteration_metrics(),
          nc_test_runtime=self.test_runtime,
          low_throughput_tip=_THROUGHPUT_LOW_TIP,
      )

    prior_bt_snippet.disconnect_endpoint()
    active_snippet.disconnect_endpoint()


if __name__ == '__main__':
  test_runner.main()
