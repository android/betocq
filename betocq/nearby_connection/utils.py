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

from collections.abc import Sequence
import logging
import time

from mobly.controllers import android_device
from mobly.controllers.android_device_lib import snippet_client_v2

from betocq import android_wifi_utils
from betocq import nc_constants
from betocq import setup_utils
from betocq import test_result_utils
from betocq.nearby_connection import nearby_connection_wrapper


def setup_android_device_for_nc_tests(
    ad: android_device.AndroidDevice,
    snippet_confs: Sequence[nc_constants.SnippetConfig],
    country_code: str,
    skip_flag_override: bool = False,
    skip_forget_wifi_network: bool = False,
) -> None:
  """Performs general Android device setup steps for NC tests."""
  if not skip_forget_wifi_network:
    android_wifi_utils.forget_all_wifi(ad)
  setup_utils.disable_gms_auto_updates(ad)
  for conf in snippet_confs:
    setup_utils.load_nearby_snippet(ad, conf)
  setup_utils.enable_logs(ad)
  setup_utils.clear_hermetic_overrides(ad)
  if not skip_flag_override:
    setup_utils.set_flags(ad, ad.log_path)
  setup_utils.set_country_code(ad, country_code)
  setup_utils.toggle_airplane_mode(ad)
  ad.nearby.wifiEnable()
  setup_utils.get_thermal_zone_data(ad)


def connect_ad_to_wifi_sta(
    ad: android_device.AndroidDevice,
    wifi_ssid: str,
    wifi_password: str,
    test_result: test_result_utils.SingleTestResult,
    is_discoverer: bool,
):
  """Connects NC discoverer or advertiser to the given Wi-Fi STA.

  Args:
    ad: The device to connect to wifi sta.
    wifi_ssid: The Wi-Fi SSID.
    wifi_password: The Wi-Fi password.
    test_result: The object to record test result and metrics.
    is_discoverer: Whether the device is the NC discoverer. This is used for
      generating test failure reason and result summary info.
  """
  try:
    latency = setup_utils.connect_to_wifi_sta_till_success(
        ad, wifi_ssid, wifi_password
    )
  except Exception:
    fail_reason = (
        nc_constants.SingleTestFailureReason.SOURCE_WIFI_CONNECTION
        if is_discoverer
        else nc_constants.SingleTestFailureReason.TARGET_WIFI_CONNECTION
    )
    result_messages = [
        nc_constants.COMMON_TRIAGE_TIP.get(fail_reason, '').format(
            serial=ad.serial
        ),
    ]
    rssi = setup_utils.get_wifi_sta_rssi(ad, wifi_ssid)
    if rssi == nc_constants.INVALID_RSSI:
      ad.log.info('No valid RSSI')
    if rssi > nc_constants.RSSI_HIGH_THRESHOLD:
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
  ad.log.info(
      'sta frequency: %s',
      ad.nearby.wifiGetConnectionInfo().get('mFrequency'),
  )


def start_prior_bt_nearby_connection(
    advertiser: android_device.AndroidDevice,
    discoverer: android_device.AndroidDevice,
    test_result: test_result_utils.SingleTestResult,
) -> nearby_connection_wrapper.NearbyConnectionWrapper:
  """Starts a prior BT Nearby Connection."""
  logging.info('set up a prior BT connection.')
  prior_bt_snippet = _get_snippet(
      advertiser,
      discoverer,
      advertiser.nearby2,
      discoverer.nearby2,
      advertising_discovery_medium=nc_constants.NearbyMedium.BLE_ONLY,
      connection_medium=nc_constants.NearbyMedium.BT_ONLY,
      upgrade_medium=nc_constants.NearbyMedium.BT_ONLY,
  )
  try:
    prior_bt_snippet.start_nearby_connection(
        timeouts=nc_constants.DEFAULT_FIRST_CONNECTION_TIMEOUTS,
        medium_upgrade_type=nc_constants.MediumUpgradeType.NON_DISRUPTIVE,
    )
  finally:
    test_result.prior_nc_quality_info = prior_bt_snippet.connection_quality_info
    test_result.set_prior_nc_fail_reason(prior_bt_snippet.test_failure_reason)
  return prior_bt_snippet


def start_main_nearby_connection(
    advertiser: android_device.AndroidDevice,
    discoverer: android_device.AndroidDevice,
    test_result: test_result_utils.SingleTestResult,
    upgrade_medium_under_test: nc_constants.NearbyMedium,
    connection_medium: nc_constants.NearbyMedium = nc_constants.NearbyMedium.BT_ONLY,
    connect_timeout: nc_constants.ConnectionSetupTimeouts = nc_constants.DEFAULT_FIRST_CONNECTION_TIMEOUTS,
    medium_upgrade_type: nc_constants.MediumUpgradeType = nc_constants.MediumUpgradeType.DISRUPTIVE,
    keep_alive_timeout_ms: int = nc_constants.KEEP_ALIVE_TIMEOUT_WIFI_MS,
    keep_alive_interval_ms: int = nc_constants.KEEP_ALIVE_INTERVAL_WIFI_MS,
) -> nearby_connection_wrapper.NearbyConnectionWrapper:
  """Starts a main Nearby Connection which is used for file transfer."""
  logging.info('set up a nearby connection for file transfer.')

  active_snippet = _get_snippet(
      advertiser,
      discoverer,
      advertiser.nearby,
      discoverer.nearby,
      advertising_discovery_medium=nc_constants.NearbyMedium.BLE_ONLY,
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
    )
  finally:
    test_result.quality_info = active_snippet.connection_quality_info
    fail_reason = active_snippet.test_failure_reason
    result_message = None
    if fail_reason == nc_constants.SingleTestFailureReason.WIFI_MEDIUM_UPGRADE:
      default_message = (
          f'unexpected upgrade medium - {upgrade_medium_under_test.name}'
      )
      result_message = nc_constants.MEDIUM_UPGRADE_FAIL_TRIAGE_TIPS.get(
          upgrade_medium_under_test, default_message
      )

    if fail_reason != nc_constants.SingleTestFailureReason.SUCCESS:
      test_result.set_active_nc_fail_reason(fail_reason, result_message)

  return active_snippet


def handle_file_transfer_failure(
    fail_reason: nc_constants.SingleTestFailureReason,
    test_result: test_result_utils.SingleTestResult,
    file_transfer_failure_tip: str,
):
  """Collects metrics and generates result message for file transfer failure."""
  if fail_reason == nc_constants.SingleTestFailureReason.SUCCESS:
    return
  result_message = None
  if fail_reason == nc_constants.SingleTestFailureReason.FILE_TRANSFER_FAIL:
    result_message = file_transfer_failure_tip
  test_result.set_active_nc_fail_reason(fail_reason, result_message)


def reset_nearby_connection(
    discoverer: android_device.AndroidDevice,
    advertiser: android_device.AndroidDevice,
) -> None:
  """Resets any nearby connection on the devices."""
  discoverer.nearby.stopDiscovery()
  discoverer.nearby.stopAllEndpoints()
  advertiser.nearby.stopAdvertising()
  advertiser.nearby.stopAllEndpoints()
  if getattr(discoverer, 'nearby2', None):
    discoverer.nearby2.stopDiscovery()
    discoverer.nearby2.stopAllEndpoints()
  if getattr(advertiser, 'nearby2', None):
    advertiser.nearby2.stopAdvertising()
    advertiser.nearby2.stopAllEndpoints()
  if getattr(discoverer, 'nearby3', None):
    discoverer.nearby3p.stopDiscovery()
    discoverer.nearby3p.stopAllEndpoints()
  if getattr(advertiser, 'nearby3', None):
    advertiser.nearby3p.stopAdvertising()
    advertiser.nearby3p.stopAllEndpoints()
  time.sleep(nc_constants.NEARBY_RESET_WAIT_TIME.total_seconds())


def _get_snippet(
    advertiser: android_device.AndroidDevice,
    discoverer: android_device.AndroidDevice,
    advertiser_nearby: snippet_client_v2.SnippetClientV2,
    discoverer_nearby: snippet_client_v2.SnippetClientV2,
    advertising_discovery_medium: nc_constants.NearbyMedium,
    connection_medium: nc_constants.NearbyMedium,
    upgrade_medium: nc_constants.NearbyMedium,
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
