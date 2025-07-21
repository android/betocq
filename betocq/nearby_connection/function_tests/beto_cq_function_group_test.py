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

"""The module for all function tests.

Test requirements:
  2 Android devices.
  An Wi-Fi network.

Test setup steps:
  Set country code to US on Android devices.

Test steps:
  See docstring of each test function.
"""

import collections
import datetime
import logging
import time

from mobly import asserts
from mobly import test_runner
from mobly import records
from mobly import utils
from mobly.controllers import android_device

from betocq import base_test
from betocq import nc_constants
from betocq import nc_utils
from betocq import setup_utils
from betocq import test_result_utils


_COUNTRY_CODE = 'US'
_BT_BLE_FILE_TRANSFER_FAILURE_TIP = (
    'The Bluetooth performance is really bad or unknown reason.'
)
_BT_MULTIPLEX_CONNECTIONS_FAILURE_TIP = (
    'The Bluetooth performance is really bad.'
)
_WIFI_TRANSFER_FAILURE_TIP = (
    'the transfer times out. Check if medium is still connected and review'
    ' device logs for more details.'
)
_WIFILAN_FILE_TRANSFER_FAILURE_TIP = (
    f'{nc_constants.NearbyMedium.WIFILAN_ONLY.name}:'
    f' {_WIFI_TRANSFER_FAILURE_TIP}'
)
_WIFI_HOTSPOT_FILE_TRANSFER_FAILURE_TIP = (
    f'{nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT.name}:'
    f' {_WIFI_TRANSFER_FAILURE_TIP}'
)
_WIFI_AWARE_FILE_TRANSFER_FAILURE_TIP = (
    f'{nc_constants.NearbyMedium.WIFIAWARE_ONLY.name}:'
    f' {_WIFI_TRANSFER_FAILURE_TIP}'
)
_WIFI_DIRECT_FILE_TRANSFER_FAILURE_TIP = (
    f'{nc_constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT.name}:'
    f' {_WIFI_TRANSFER_FAILURE_TIP}'
)


def _get_wifi_ssid_password(
    test_parameters: nc_constants.TestParameters,
) -> tuple[str, str]:
  """Returns an available wifi SSID and password from test parameters."""
  if test_parameters.wifi_ssid:
    return (
        test_parameters.wifi_ssid,
        test_parameters.wifi_password,
    )
  if test_parameters.wifi_5g_ssid:
    return (
        test_parameters.wifi_5g_ssid,
        test_parameters.wifi_5g_password,
    )
  if test_parameters.wifi_dfs_5g_ssid:
    return (
        test_parameters.wifi_dfs_5g_ssid,
        test_parameters.wifi_dfs_5g_password,
    )
  if test_parameters.wifi_2g_ssid:
    return (
        test_parameters.wifi_2g_ssid,
        test_parameters.wifi_2g_password,
    )
  return ('', '')


def _start_nearby_connection_and_transfer_file(
    advertiser: android_device.AndroidDevice,
    discoverer: android_device.AndroidDevice,
    test_result: test_result_utils.SingleTestResult,
    upgrade_medium_under_test: nc_constants.NearbyMedium,
    file_transfer_failure_tip: str,
    payload_type: nc_constants.PayloadType,
    payload_size_kb: int = nc_constants.TRANSFER_FILE_SIZE_FUNC_TEST_KB,
    payload_transfer_timeout: datetime.timedelta = nc_constants.TRANSFER_TIMEOUT_FUNC_TEST,
    payload_num: int = nc_constants.TRANSFER_FILE_NUM_FUNC_TEST,
    connect_timeout: nc_constants.ConnectionSetupTimeouts = nc_constants.DEFAULT_FIRST_CONNECTION_TIMEOUTS,
):
  """Starts a nearby connection and transfers files on it."""
  # Test Step: Set up a NC connection for file transfer.
  nearby_snippet = nc_utils.start_main_nearby_connection(
      advertiser,
      discoverer,
      test_result,
      upgrade_medium_under_test=upgrade_medium_under_test,
      medium_upgrade_type=nc_constants.MediumUpgradeType.NON_DISRUPTIVE,
      connect_timeout=connect_timeout,
      keep_alive_timeout_ms=0,
      keep_alive_interval_ms=0,
  )

  # Test Step: Transfer file on the established NC.
  try:
    test_result.file_transfer_throughput_kbps = nearby_snippet.transfer_file(
        file_size_kb=payload_size_kb,
        timeout=payload_transfer_timeout,
        payload_type=payload_type,
        num_files=payload_num,
    )
  finally:
    nc_utils.handle_file_transfer_failure(
        nearby_snippet.test_failure_reason,
        test_result,
        file_transfer_failure_tip=file_transfer_failure_tip,
    )

    nearby_snippet.disconnect_endpoint()


class BetoCqFunctionGroupTest(base_test.BaseTestClass):
  """The test class to group all function tests in one mobly test."""

  # Result information on the test currently being executed.
  current_test_result: test_result_utils.SingleTestResult

  # Store test results of all test cases.
  _test_results: collections.OrderedDict[
      str, test_result_utils.SingleTestResult
  ]

  def __init__(self, configs):
    super().__init__(configs)
    self._test_results = collections.OrderedDict()

  def setup_class(self):
    """Setup steps that will be performed before exucuting any test case."""
    super().setup_class()
    utils.concurrent_exec(
        self._setup_android_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    # Use 5G WiFi for function tests.
    self.setup_wifi_env(
        d2d_type=nc_constants.WifiD2DType.SCC_5G, country_code=_COUNTRY_CODE
    )

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    # Load an extra snippet instance nearby2 for test cases that need to
    # set up 2 nearby connections.
    nc_utils.setup_android_device_for_nc_tests(
        ad,
        snippet_confs=[self.nearby_snippet_config, self.nearby2_snippet_config],
        country_code=_COUNTRY_CODE,
        debug_output_dir=self.current_test_info.output_path,
        skip_flag_override=self.test_parameters.skip_default_flag_override,
    )

  def setup_test(self):
    """Setup steps that will be performed before exucuting each test case."""
    super().setup_test()
    self.current_test_result = test_result_utils.SingleTestResult()
    self._test_results[self.current_test_info.name] = self.current_test_result
    nc_utils.reset_nearby_connection(self.discoverer, self.advertiser)

  def test_bt_ble_function(self):
    """Test the NC with the BT/BLE medium only.

    Test Step:
      1. Set up a nearby connection with the BT/BLE medium only and transfer
         file.
      2. Tear down the connection.
    """
    _start_nearby_connection_and_transfer_file(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        upgrade_medium_under_test=nc_constants.NearbyMedium.BT_ONLY,
        file_transfer_failure_tip=_BT_BLE_FILE_TRANSFER_FAILURE_TIP,
        payload_type=nc_constants.PayloadType.FILE,
        payload_size_kb=nc_constants.TRANSFER_FILE_SIZE_1KB,
        payload_transfer_timeout=nc_constants.BT_1K_PAYLOAD_TRANSFER_TIMEOUT,
        payload_num=nc_constants.TRANSFER_FILE_NUM_DEFAULT,
    )

  def test_wifilan_function(self):
    """Test the NC with upgrading to the Wifi LAN medium.

    Test steps:
      1. Connect to wifi.
      2. Set up a nearby connection with the WifiLAN medium and transfer file.
      3. Tear down the connection.
    """
    # Test Step: Connect discoverer and advertiser to wifi sta.
    wifi_ssid, wifi_password = _get_wifi_ssid_password(self.test_parameters)
    if not wifi_ssid:
      self.current_test_result.set_active_nc_fail_reason(
          nc_constants.SingleTestFailureReason.AP_IS_NOT_CONFIGURED
      )
      asserts.fail('Wifi AP must be specified.')

    logging.info('connect to wifi: %s', wifi_ssid)

    nc_utils.connect_ad_to_wifi_sta(
        self.discoverer,
        wifi_ssid,
        wifi_password,
        self.current_test_result,
        is_discoverer=True,
    )

    nc_utils.connect_ad_to_wifi_sta(
        self.advertiser,
        wifi_ssid,
        wifi_password,
        self.current_test_result,
        is_discoverer=False,
    )
    # Let scan, DHCP and internet validation complete before NC.
    time.sleep(self.test_parameters.target_post_wifi_connection_idle_time_sec)

    # Test Step: Set up nearby connection and transfer file.
    _start_nearby_connection_and_transfer_file(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        nc_constants.NearbyMedium.WIFILAN_ONLY,
        file_transfer_failure_tip=_WIFILAN_FILE_TRANSFER_FAILURE_TIP,
        payload_type=nc_constants.PayloadType.FILE,
        payload_size_kb=nc_constants.TRANSFER_FILE_SIZE_FUNC_TEST_KB,
        payload_num=nc_constants.TRANSFER_FILE_NUM_FUNC_TEST,
    )

  def test_d2d_hotspot_file_transfer_function(self):
    """Test the NC with the HOTSPOT medium and payload type FILE.

    Test requirements:
      WiFi Direct is supported on both devices.

    Test steps:
      1. Set up a nearby connection with the HOTSPOT medium and transfer payload
         with NC payload type FILE.
      2. Tear down the connection.
    """
    self._skip_if_wifi_hotspot_not_supported()

    _start_nearby_connection_and_transfer_file(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT,
        file_transfer_failure_tip=_WIFI_HOTSPOT_FILE_TRANSFER_FAILURE_TIP,
        payload_type=nc_constants.PayloadType.FILE,
        payload_size_kb=nc_constants.TRANSFER_FILE_SIZE_FUNC_TEST_KB,
        payload_num=nc_constants.TRANSFER_FILE_NUM_FUNC_TEST,
    )

  def test_d2d_hotspot_stream_transfer_function(self):
    """Test the NC with the HOTSPOT medium and payload type STREAM.

    Test requirements:
      WiFi Direct is supported on both devices.

    Test steps
      1. Set up a nearby connection with the HOTSPOT medium and transfer payload
         with NC payload type STREAM.
      2. Tear down the connection.
    """
    self._skip_if_wifi_hotspot_not_supported()

    _start_nearby_connection_and_transfer_file(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT,
        file_transfer_failure_tip=_WIFI_HOTSPOT_FILE_TRANSFER_FAILURE_TIP,
        payload_type=nc_constants.PayloadType.STREAM,
        payload_size_kb=nc_constants.TRANSFER_FILE_SIZE_FUNC_TEST_KB,
        payload_num=nc_constants.TRANSFER_FILE_NUM_FUNC_TEST,
    )

  def test_wifi_direct_file_transfer_function(self):
    """Test the NC with the WiFi Direct medium and payload type FILE.

    Test requirements:
      WiFi Direct is supported on both devices.

    Test steps:
      1. Set up a nearby connection with the WiFi Direct medium and transfer
         payload with NC payload type FILE.
      2. Tear down the connection.
    """
    self._skip_if_wifi_direct_not_supported()

    _start_nearby_connection_and_transfer_file(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT,
        file_transfer_failure_tip=_WIFI_DIRECT_FILE_TRANSFER_FAILURE_TIP,
        payload_type=nc_constants.PayloadType.FILE,
        payload_size_kb=nc_constants.TRANSFER_FILE_SIZE_FUNC_TEST_KB,
        payload_num=nc_constants.TRANSFER_FILE_NUM_FUNC_TEST,
    )

  def test_wifi_direct_stream_transfer_function(self):
    """Test the NC with the WiFi Direct medium and payload type STREAM.

    Test requirements:
      WiFi Direct is supported on both devices.

    Test steps
      1. Set up a nearby connection with the WiFi Direct medium and transfer
         payload with NC payload type STREAM.
      2. Tear down the connection.
    """
    self._skip_if_wifi_direct_not_supported()

    _start_nearby_connection_and_transfer_file(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        nc_constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT,
        file_transfer_failure_tip=_WIFI_DIRECT_FILE_TRANSFER_FAILURE_TIP,
        payload_type=nc_constants.PayloadType.STREAM,
        payload_size_kb=nc_constants.TRANSFER_FILE_SIZE_FUNC_TEST_KB,
        payload_num=nc_constants.TRANSFER_FILE_NUM_FUNC_TEST,
    )

  def test_wifi_aware_file_transfer_function(self):
    """Test the NC with the WiFi Aware medium and payload type FILE.

    Test requirements:
      WiFi Aware is supported on both devices.

    Test steps:
      1. Set up a nearby connection with the WiFi Aware medium and transfer
         payload with NC payload type FILE.
      2. Tear down the connection.
    """
    self._skip_if_wifi_aware_not_supported()

    _start_nearby_connection_and_transfer_file(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        nc_constants.NearbyMedium.WIFIAWARE_ONLY,
        file_transfer_failure_tip=_WIFI_AWARE_FILE_TRANSFER_FAILURE_TIP,
        payload_type=nc_constants.PayloadType.FILE,
        payload_size_kb=nc_constants.TRANSFER_FILE_SIZE_FUNC_TEST_KB,
        payload_num=nc_constants.TRANSFER_FILE_NUM_FUNC_TEST,
    )

  def test_wifi_aware_stream_transfer_function(self):
    """Test the NC with the WiFi Aware medium and payload type STREAM.

    Test requirements:
      WiFi Aware is supported on both devices.

    Test steps
      1. Set up a nearby connection with the WiFi Aware medium and transfer
         payload with NC payload type STREAM.
      2. Tear down the connection.
    """
    self._skip_if_wifi_aware_not_supported()

    _start_nearby_connection_and_transfer_file(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        nc_constants.NearbyMedium.WIFIAWARE_ONLY,
        file_transfer_failure_tip=_WIFI_AWARE_FILE_TRANSFER_FAILURE_TIP,
        payload_type=nc_constants.PayloadType.STREAM,
        payload_size_kb=nc_constants.TRANSFER_FILE_SIZE_FUNC_TEST_KB,
        payload_num=nc_constants.TRANSFER_FILE_NUM_FUNC_TEST,
    )

  def test_bt_multiplex_connections(self):
    """Test the BT multiplex function of nearby connection.

    Test steps:
      1. Set up 2 nearby connections with the BT medium and transfer
         payload with one of them.
      2. Tear down all connections.
    """
    if not self.test_parameters.requires_bt_multiplex:
      message = (
          'BT multiplex is not required for this CUJ -'
          f' {self.test_parameters.target_cuj_name}'
      )
      self.current_test_result.set_active_nc_fail_reason(
          nc_constants.SingleTestFailureReason.SKIPPED,
          result_message=message,
      )
      asserts.skip(message)

    # Test Step: Set up a prior BT connection.
    prior_bt_snippet = nc_utils.start_prior_bt_nearby_connection(
        self.advertiser, self.discoverer, self.current_test_result
    )

    # Test Step: Set up 2st BT connection.
    _start_nearby_connection_and_transfer_file(
        self.advertiser,
        self.discoverer,
        self.current_test_result,
        upgrade_medium_under_test=nc_constants.NearbyMedium.BT_ONLY,
        file_transfer_failure_tip=_BT_MULTIPLEX_CONNECTIONS_FAILURE_TIP,
        payload_type=nc_constants.PayloadType.FILE,
        payload_num=nc_constants.TRANSFER_FILE_NUM_DEFAULT,
        payload_transfer_timeout=nc_constants.BT_1K_PAYLOAD_TRANSFER_TIMEOUT,
        payload_size_kb=nc_constants.TRANSFER_FILE_SIZE_1KB,
        connect_timeout=nc_constants.DEFAULT_SECOND_CONNECTION_TIMEOUTS,
    )

    prior_bt_snippet.disconnect_endpoint()

  def teardown_test(self) -> None:
    """Tears down and records results for current test case."""
    self.current_test_result.end_test()
    self.record_data({
        'Test Name': self.current_test_info.name,
        'properties': {
            'result': self.current_test_result.result_message,
        },
    })
    super().teardown_test()

  def on_pass(self, record: records.TestResultRecord):
    """Steps that will be performed when current test case passed."""
    self.current_test_result.set_active_nc_fail_reason(
        nc_constants.SingleTestFailureReason.SUCCESS
    )
    self._record_single_test_case_report()
    super().on_pass(record)

  def on_fail(self, record: records.TestResultRecord):
    """Steps that will be performed when current test case failed."""
    # If any exception is raised in `setup_class`, `on_fail` will be invoked
    # and we should not record any result because no test is executed.
    if self._test_results:
      self._record_single_test_case_report()
    super().on_fail(record)

  def _record_single_test_case_report(self):
    self.record_data({
        'Test Name': self.current_test_info.name,
        'properties': {
            'result': self.current_test_result.result_message,
        },
    })

  def teardown_class(self):
    """Tears down and records results for all test cases."""
    if not self._test_results:
      logging.info('Skipping teardown class.')
      return

    test_result_str = '\n'.join(
        f'{test_name}: {test_result.result_message}'
        for test_name, test_result in self._test_results.items()
    )
    test_summary = test_result_utils.gen_basic_test_summary(
        self.discoverer, self.advertiser, test_result_str
    )
    test_summary_with_index = {}
    for index, (k, v) in enumerate(test_summary.items()):
      test_summary_with_index[f'{index:02}_{k}'] = v
    self.record_data(
        {'Test Class': self.TAG, 'properties': test_summary_with_index}
    )

    super().teardown_class()

  def _skip_if_wifi_hotspot_not_supported(self):
    # Check Direct capability because Hotspot is implemented using Direct in NC.
    if not setup_utils.is_wifi_direct_supported(
        self.advertiser
    ) or not setup_utils.is_wifi_direct_supported(self.discoverer):
      message = 'Wifi Hotspot is not supported in the device'
      self.current_test_result.set_active_nc_fail_reason(
          nc_constants.SingleTestFailureReason.SKIPPED,
          result_message=message,
      )
      asserts.skip(message)

  def _skip_if_wifi_direct_not_supported(self):
    if not setup_utils.is_wifi_direct_supported(
        self.advertiser
    ) or not setup_utils.is_wifi_direct_supported(self.discoverer):
      message = 'Wifi Direct is not supported in the device'
      self.current_test_result.set_active_nc_fail_reason(
          nc_constants.SingleTestFailureReason.SKIPPED,
          result_message=message,
      )
      asserts.skip(message)

  def _skip_if_wifi_aware_not_supported(self):
    if (
        not self.test_parameters.run_aware_test
        or not setup_utils.is_wifi_aware_available(self.advertiser)
        or not setup_utils.is_wifi_aware_available(self.discoverer)
    ):
      message = 'Aware test is disabled or aware is not available in the device'
      self.current_test_result.set_active_nc_fail_reason(
          nc_constants.SingleTestFailureReason.SKIPPED,
          result_message=message,
      )
      asserts.skip(message)


if __name__ == '__main__':
  test_runner.main()
