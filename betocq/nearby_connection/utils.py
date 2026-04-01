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

"""Utility functions for testing against Nearby Connection."""

import logging
from typing import Any, Sequence

from mobly import base_test
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import snippet_client_v2

from betocq import android_wifi_utils
from betocq import constants
from betocq import setup_utils
from betocq import test_result_utils
from betocq.nearby_connection import nc_constants
from betocq.nearby_connection import nearby_connection_wrapper


def check_wifi_ap_status_in_setup_class(
    test_class: base_test.BaseTestClass,
    advertiser: android_device.AndroidDevice,
    test_parameters: constants.TestParameters,
) -> None:
  """Checks the WiFi AP status.

  Aborts the test class if the APs are not ready.

  Args:
    test_class: The Mobly base test class instance.
    advertiser: The Android device acting as the Nearby Connection advertiser.
    test_parameters: The test parameters containing Wi-Fi SSID information.
  """
  device_specific_info = setup_utils.get_betocq_device_specific_info(advertiser)
  if device_specific_info.get('is_wifi_ap_ready', False):
    advertiser.log.info(
        'WiFi AP status is already checked and ready, skip the check.'
    )
    return

  wifi_ap_error_count = device_specific_info.get('wifi_ap_error_count', 0)
  wifi_ap_last_error_message = device_specific_info.get(
      'wifi_ap_last_error_message', ''
  )
  abort_all = not test_parameters.run_all_tests_in_suite

  def _report_error(error_message: str) -> None:
    device_specific_info['wifi_ap_error_count'] = wifi_ap_error_count + 1
    device_specific_info['wifi_ap_last_error_message'] = error_message
    if abort_all:
      setup_utils.report_error_on_setup_class(
          test_class,
          error_message,
          abort_all=True,
      )
    else:
      setup_utils.report_error_on_setup_class(
          test_class,
          error_message,
          abort_all=False,
          error_class=constants.WifiApNotReadyError,
      )

  if wifi_ap_error_count > 1:
    advertiser.log.warning(
        'WiFi AP status check failed %d times, skip the check and report the'
        ' error earlier.',
        wifi_ap_error_count,
    )
    _report_error(wifi_ap_last_error_message)
    return

  wifi_scan_results_list = setup_utils.check_wifi_env(advertiser)
  if test_parameters.use_programmable_ap:
    return
  if not test_parameters.abort_all_if_any_ap_not_ready:
    return
  if not wifi_scan_results_list:
    advertiser.log.warning(
        'WiFi scan results are not available, skip the ssid and frequency'
        ' check, the tests might be failed.'
    )
    return

  freq_by_ssids = {
      result['SSID']: result['Frequency'] for result in wifi_scan_results_list
  }
  wifi_2g_ssid = test_parameters.wifi_2g_ssid
  wifi_5g_ssid = test_parameters.wifi_5g_ssid
  wifi_dfs_5g_ssid = test_parameters.wifi_dfs_5g_ssid
  freq_2g = freq_by_ssids.get(wifi_2g_ssid)
  freq_5g = freq_by_ssids.get(wifi_5g_ssid)
  freq_5g_dfs = freq_by_ssids.get(wifi_dfs_5g_ssid)

  if freq_2g is None or freq_5g is None or freq_5g_dfs is None:
    logging.warning(
        'WiFi APs not detected in first scan: 2G:%s(%s), 5G:%s(%s), DFS:%s(%s).'
        ' Retrying...',
        wifi_2g_ssid,
        freq_2g,
        wifi_5g_ssid,
        freq_5g,
        wifi_dfs_5g_ssid,
        freq_5g_dfs,
    )
    wifi_scan_results_list = setup_utils.check_wifi_env(
        advertiser,
        wifi_scan_wait_time_sec=setup_utils.WIFI_SCAN_WAIT_TIME_SEC * 2
    )
    if wifi_scan_results_list:
      freq_by_ssids = {
          result['SSID']: result['Frequency']
          for result in wifi_scan_results_list
      }
      freq_2g = freq_by_ssids.get(wifi_2g_ssid)
      freq_5g = freq_by_ssids.get(wifi_5g_ssid)
      freq_5g_dfs = freq_by_ssids.get(wifi_dfs_5g_ssid)

  if freq_2g is None or freq_5g is None or freq_5g_dfs is None:
    _report_error(
        'WiFi APs are not detected in the environment, they are: 2G:'
        f' {wifi_2g_ssid} {"OK" if freq_2g else "Not Detected"}, 5G:'
        f' {wifi_5g_ssid} {"OK" if freq_5g else "Not Detected"}, DFS:'
        f' {wifi_dfs_5g_ssid} {"OK" if freq_5g_dfs else "Not Detected"}.'
        f' Check your AP status, may reboot the AP if needed.',
    )
  if not setup_utils.is_valid_wifi_2g_freq(freq_2g):
    _report_error(
        f'2G AP - {wifi_2g_ssid}, frequency - {freq_2g} is not valid. Set'
        f' the AP channel, reboot the AP and try again.'
    )
  if not setup_utils.is_valid_wifi_5g_freq(freq_5g):
    _report_error(
        f'5G AP - {wifi_5g_ssid}, frequency - {freq_5g} is not valid. Set'
        ' the AP channel, reboot the AP and try again.'
    )
  if not setup_utils.is_valid_wifi_5g_dfs_freq(freq_5g_dfs):
    _report_error(
        f'5G DFS AP - {wifi_dfs_5g_ssid}, frequency - {freq_5g_dfs} is not'
        ' valid. Set the AP channel, reboot the AP and try again.'
    )
  device_specific_info['is_wifi_ap_ready'] = True
  device_specific_info['wifi_ap_error_count'] = 0


def get_nearby_snippet_config(
    user_params: dict[str, Any],
) -> constants.SnippetConfig:
  """Returns the snippet config for the first nearby snippet instance."""
  return constants.SnippetConfig(
      snippet_name='nearby',
      package_name=constants.NEARBY_SNIPPET_PACKAGE_NAME,
      apk_path=setup_utils.get_snippet_apk_path(user_params, 'nearby_snippet'),
  )


def get_nearby2_snippet_config(
    user_params: dict[str, Any],
) -> constants.SnippetConfig:
  """Returns the snippet config for the second nearby snippet instance."""
  return constants.SnippetConfig(
      snippet_name='nearby2',
      package_name=constants.NEARBY_SNIPPET_2_PACKAGE_NAME,
      apk_path=setup_utils.get_snippet_apk_path(
          user_params, 'nearby_snippet_2'
      ),
  )


def setup_android_device_for_nc_tests(
    ad: android_device.AndroidDevice,
    snippet_confs: Sequence[constants.SnippetConfig],
    country_code: str,
    skip_flag_override: bool = False,
) -> None:
  """Performs general Android device setup steps for NC tests."""
  # TODO: Double check if the set_flags() may break this as it will
  # restart GMS.

  for conf in snippet_confs:
    setup_utils.load_nearby_snippet(ad, conf)

  if not skip_flag_override:
    setup_utils.clear_hermetic_overrides(ad, restart_gms_process=False)
    setup_utils.set_flags(ad, ad.log_path)
  else:
    setup_utils.clear_hermetic_overrides(ad)

  device_specific_dict = setup_utils.get_betocq_device_specific_info(ad)
  if not device_specific_dict.get('one_time_setup_done', False):
    setup_utils.enable_location_on_device(ad)
    setup_utils.enable_logs(ad)

    setup_utils.enable_airplane_mode(ad)
    if setup_utils.wifi_is_enabled(ad):
      ad.nearby.wifiDisable()
    # Put it here to work around the WifiManager#getConfiguredNetworks() issue
    # before Android 15
    ad.log.info('Forgetting all wifi networks')
    android_wifi_utils.forget_all_wifi(ad)
    setup_utils.disable_airplane_mode(ad)
    if not setup_utils.wifi_is_enabled(ad):
      ad.nearby.wifiEnable()
    setup_utils.reset_nearby_connection(ad)
    device_specific_dict['wifi_fw'] = setup_utils.get_wifi_firmware_version(
        ad
    )
    device_specific_dict['bt_fw'] = setup_utils.get_bt_firmware_version(ad)
    device_specific_dict['one_time_setup_done'] = True

  if country_code != device_specific_dict.get('wifi_country_code', ''):
    setup_utils.set_country_code(ad, country_code)
    device_specific_dict['wifi_country_code'] = country_code

  setup_utils.disable_gms_auto_updates(ad)

  # Acquire the UiAutomation instance for the device.
  setup_utils.clear_all_accessibility_services(ad)
  ad.nearby.acquireUiAutomation()


def connect_ad_to_wifi_sta(
    ad: android_device.AndroidDevice,
    wifi_ssid: str,
    wifi_password: str,
    test_result: test_result_utils.SingleTestResult,
    is_discoverer: bool,
) -> bool:
  """Connects NC discoverer or advertiser to the given Wi-Fi STA.

  Args:
    ad: The device to connect to Wi-Fi STA.
    wifi_ssid: The Wi-Fi SSID.
    wifi_password: The Wi-Fi password.
    test_result: The object to record test result and metrics.
    is_discoverer: Whether the device is the NC discoverer. This is used for
      generating test failure reason and result summary info.

  Returns:
    True if the device successfully connected to a new Wi-Fi network, False if
    the device was already connected to the specified Wi-Fi network.

  Raises:
    Exception: If an error occurs during the Wi-Fi connection process.
  """
  try:
    wifi_info = ad.nearby.wifiGetConnectionInfo()
    current_wifi_ssid = wifi_info.get('SSID', '')
    if current_wifi_ssid == wifi_ssid:
      ad.log.info(f'already connected to {wifi_ssid}')
      return False

    if (
        current_wifi_ssid
        and current_wifi_ssid != constants.WIFI_UNKNOWN_SSID
    ):
      network_id = setup_utils.get_sta_network_id_from_wifi_info(wifi_info)
      if network_id != constants.INVALID_NETWORK_ID:
        ad.log.info(f'disconnecting from {current_wifi_ssid})')
        ad.nearby.wifiRemoveNetwork(network_id)
      else:
        ad.log.warning(
            f'No valid network id for {current_wifi_ssid}, try'
            ' to remove all networks.'
        )
        setup_utils.remove_disconnect_wifi_network(ad)

    latency = setup_utils.connect_to_wifi_sta_till_success(
        ad, wifi_ssid, wifi_password
    )
  except Exception:
    fail_reason = (
        constants.SingleTestFailureReason.SOURCE_WIFI_CONNECTION
        if is_discoverer
        else constants.SingleTestFailureReason.TARGET_WIFI_CONNECTION
    )
    result_messages = [
        constants.COMMON_TRIAGE_TIP.get(fail_reason, '').format(
            serial=ad.serial
        ),
    ]
    rssi = setup_utils.get_wifi_sta_rssi(ad, wifi_ssid)
    if rssi == constants.INVALID_RSSI:
      ad.log.info('No valid RSSI')
    if rssi > constants.RSSI_HIGH_THRESHOLD:
      high_rssi_tip = (
          f'RSSI={rssi} of which is too high. Consider to move the device'
          ' away from the AP.'
      )
      ad.log.info(high_rssi_tip)
      result_messages.append(high_rssi_tip)
    test_result.set_active_nc_fail_reason(
        fail_reason, result_message=' '.join(result_messages)
    )
    setup_utils.log_sta_event_list(ad)
    raise

  if is_discoverer:
    test_result.discoverer_sta_latency = latency
  else:
    test_result.advertiser_sta_latency = latency
  ad.log.info('connecting to wifi in %d s', round(latency.total_seconds()))
  new_wifi_info = ad.nearby.wifiGetConnectionInfo()
  ad.log.info(
      'sta frequency: %s, rssi: %s for new wifi connection',
      setup_utils.get_sta_frequency_from_wifi_info(new_wifi_info),
      setup_utils.get_sta_rssi_from_wifi_info(new_wifi_info),
  )

  return True


def start_prior_bt_nearby_connection(
    advertiser: android_device.AndroidDevice,
    discoverer: android_device.AndroidDevice,
    test_result: test_result_utils.SingleTestResult,
    test_parameters: constants.TestParameters | None = None,
) -> nearby_connection_wrapper.NearbyConnectionWrapper:
  """Starts a prior BT Nearby Connection."""
  logging.info('Set up a prior BT connection.')
  prior_bt_snippet = _get_snippet(
      advertiser,
      discoverer,
      advertiser.nearby2,
      discoverer.nearby2,
      advertising_discovery_medium=constants.NearbyMedium.BLE_ONLY,
      connection_medium=constants.NearbyMedium.BT_ONLY,
      upgrade_medium=constants.NearbyMedium.BT_ONLY,
  )
  try:
    prior_bt_snippet.start_nearby_connection(
        timeouts=constants.DEFAULT_FIRST_CONNECTION_TIMEOUTS,
        medium_upgrade_type=constants.MediumUpgradeType.NON_DISRUPTIVE,
        test_parameters=test_parameters,
    )
  finally:
    test_result.prior_nc_quality_info = prior_bt_snippet.connection_quality_info
    test_result.set_prior_nc_fail_reason(prior_bt_snippet.test_failure_reason)
  return prior_bt_snippet


def start_main_nearby_connection(
    advertiser: android_device.AndroidDevice,
    discoverer: android_device.AndroidDevice,
    test_result: test_result_utils.SingleTestResult,
    upgrade_medium_under_test: constants.NearbyMedium,
    test_parameters: constants.TestParameters | None = None,
    connection_medium: constants.NearbyMedium = constants.NearbyMedium.BT_ONLY,
    connect_timeout: constants.ConnectionSetupTimeouts = constants.DEFAULT_FIRST_CONNECTION_TIMEOUTS,
    medium_upgrade_type: constants.MediumUpgradeType = constants.MediumUpgradeType.DISRUPTIVE,
    keep_alive_timeout_ms: int = nc_constants.KEEP_ALIVE_TIMEOUT_WIFI_MS,
    keep_alive_interval_ms: int = nc_constants.KEEP_ALIVE_INTERVAL_WIFI_MS,
) -> nearby_connection_wrapper.NearbyConnectionWrapper:
  """Starts a main Nearby Connection which is used for file transfer."""
  logging.info('Set up a nearby connection for file transfer.')

  active_snippet = _get_snippet(
      advertiser,
      discoverer,
      advertiser.nearby,
      discoverer.nearby,
      advertising_discovery_medium=constants.NearbyMedium.BLE_ONLY,
      connection_medium=connection_medium,
      upgrade_medium=upgrade_medium_under_test,
  )
  try:
    active_snippet.start_nearby_connection(
        timeouts=connect_timeout,
        medium_upgrade_type=medium_upgrade_type,
        keep_alive_timeout_ms=keep_alive_timeout_ms,
        keep_alive_interval_ms=keep_alive_interval_ms,
        enable_target_discovery=False,
        test_parameters=test_parameters,
    )
  finally:
    test_result.quality_info = active_snippet.connection_quality_info
    fail_reason = active_snippet.test_failure_reason
    result_message = None
    if fail_reason == constants.SingleTestFailureReason.WIFI_MEDIUM_UPGRADE:
      default_message = (
          f'Unexpected upgrade medium - {upgrade_medium_under_test.name}.'
      )
      result_message = constants.MEDIUM_UPGRADE_FAIL_TRIAGE_TIPS.get(
          upgrade_medium_under_test, default_message
      )

    if fail_reason != constants.SingleTestFailureReason.SUCCESS:
      test_result.set_active_nc_fail_reason(fail_reason, result_message)

  return active_snippet


def handle_file_transfer_failure(
    fail_reason: constants.SingleTestFailureReason,
    test_result: test_result_utils.SingleTestResult,
    file_transfer_failure_tip: str,
):
  """Collects metrics and generates result message for file transfer failure."""
  if fail_reason == constants.SingleTestFailureReason.SUCCESS:
    return
  result_message = None
  if fail_reason == constants.SingleTestFailureReason.FILE_TRANSFER_FAIL:
    result_message = file_transfer_failure_tip
  test_result.set_active_nc_fail_reason(fail_reason, result_message)


def _get_snippet(
    advertiser: android_device.AndroidDevice,
    discoverer: android_device.AndroidDevice,
    advertiser_nearby: snippet_client_v2.SnippetClientV2,
    discoverer_nearby: snippet_client_v2.SnippetClientV2,
    advertising_discovery_medium: constants.NearbyMedium,
    connection_medium: constants.NearbyMedium,
    upgrade_medium: constants.NearbyMedium,
) -> nearby_connection_wrapper.NearbyConnectionWrapper:
  """Gets the snippet for Nearby Connection."""
  return nearby_connection_wrapper.NearbyConnectionWrapper(
      advertiser,
      discoverer,
      advertiser_nearby,
      discoverer_nearby,
      advertising_discovery_medium,
      connection_medium,
      upgrade_medium,
  )
