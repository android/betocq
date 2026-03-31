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

"""Android Nearby device setup."""

from collections.abc import Callable, Iterable, Sequence
import datetime
import pprint
import re
import time
from typing import Any, Literal

from mobly import asserts
from mobly import base_test
from mobly import records
from mobly import signals
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import adb
from mobly.controllers.android_device_lib import apk_utils
from mobly.controllers.android_device_lib.services import snippet_management_service
from mobly.snippet import errors

from betocq.gms import hermetic_overrides_partner
from betocq import constants
from betocq import gms_auto_updates_util
from betocq import resources

_DEFAULT_OVERRIDES = '//wireless/android/platform/testing/bettertogether/betocq:default_overrides'

_WIFI_DIRECT_HOTSPOT_OFF_OVERRIDES = '//wireless/android/platform/testing/bettertogether/betocq:wifi_direct_hotspot_off_overrides'
_FLAG_SETUP_TEMPLATE_KEY = 'google3/java/com/google/android/libraries/phenotype/codegen/hermetic/setup_flags_template.sh'
_GMS_PACKAGE = 'com.google.android.gms'

WIFI_COUNTRYCODE_CONFIG_TIME_SEC = 3
TOGGLE_AIRPLANE_MODE_WAIT_TIME_SEC = 2
PH_FLAG_WRITE_WAIT_TIME_SEC = 3
WIFI_DISCONNECTION_DELAY_SEC = 3
ADB_RETRY_WAIT_TIME_SEC = 2

_DISABLE_ENABLE_GMS_UPDATE_WAIT_TIME_SEC = 2


WIFI_SCAN_WAIT_TIME_SEC = 5
_WIFI_CONNECT_INTERVAL_SEC = 5
_WIFI_CONNECT_RETRY_TIMES = 3

_CLEAN_WIFI_ENV_CHECK_BSSID_THRESHOLD = 5

read_ph_flag_failed = False

NEARBY_LOG_TAGS = [
    'Nearby',
    'NearbyMessages',
    'NearbyDiscovery',
    'NearbyConnections',
    'NearbyMediums',
    'NearbySetup',
]

_UNKNOWN_BT_FIRMWARE_VERSION = 'unknown'

_WIFI_SCAN_PATTERN = re.compile(
    r"""
        ([0-9a-f:]{17})  # Captures BSSID
        \s+
        (\d+)            # Captures Frequency
        \s+
        [-\d()./:]+      # Matches RSSI (skipped)
        \s+
        [\d.]+           # Matches Age (skipped)
        \s*
        (.*?)            # Captures SSID (non-greedy)
        \s+
        (\[.*\])         # Captures Flags starting with '['
    """,
    re.VERBOSE,
)


def get_betocq_device_specific_info(
    ad: android_device.AndroidDevice,
) -> dict[str, Any]:
  """Gets the device specific info from the class attribute."""
  # Check if the class attribute exists. If not, create it as an empty dict.
  if not hasattr(android_device.AndroidDevice, 'betocq_customized_device_info'):
    setattr(android_device.AndroidDevice, 'betocq_customized_device_info', {})
  info_dict = getattr(
      android_device.AndroidDevice, 'betocq_customized_device_info'
  )
  # Check if the device specific attribute exists. If not, create it as an
  # empty dict.
  device_specific_dict = info_dict.setdefault(ad.serial, {})
  return device_specific_dict


def get_snippet_apk_path(
    user_params: dict[str, Any], snippet_name: str
) -> str | None:
  """Gets the APK path for the given snippet name from user params.

  Args:
    user_params: The user parameters from the testbed.
    snippet_name: The snippet name used to find the snippet APK in user_params
      (e.g., 'nearby_snippet').

  Returns:
    The path to the snippet APK, or None if not provided.
  """
  file_tag = 'files' if 'files' in user_params else 'mh_files'
  apk_paths = user_params.get(file_tag, {}).get(snippet_name, [''])
  if not apk_paths or not apk_paths[0]:
    # allow the apk_path to be empty as github release does not install
    # the apk in the script.
    return None
  return apk_paths[0]


def set_country_code(
    ad: android_device.AndroidDevice,
    country_code: str,
    force_telephony_cc: bool = False,
) -> None:
  """Sets Wi-Fi and Telephony country code.

  When you set the phone to EU or JP, the available 5GHz channels shrinks.
  Some phones, like Pixel 2, can't use Wi-Fi Direct or Hotspot on 5GHz
  in these countries. Pixel 3+ can, but only on some channels.
  Not all of them. So, test Nearby Share or Nearby Connections without
  Wi-Fi LAN to catch any bugs and make sure we don't break it later.

  Args:
    ad: AndroidDevice, Mobly Android Device.
    country_code: WiFi and Telephony Country Code.
    force_telephony_cc: True to force Telephony Country Code.
  """
  try:
    if not ad.is_adb_root:
      ad.log.info(
          'Skipped setting wifi country code on device %r '
          'because we do not set country code on unrooted phone.',
          ad.serial,
      )
      return
    _do_set_country_code(ad, country_code, force_telephony_cc)
  except adb.AdbError:
    ad.log.exception(
        'Failed to set country code on device %r, try again.', ad.serial
    )
    time.sleep(ADB_RETRY_WAIT_TIME_SEC)
    _do_set_country_code(ad, country_code)


def _do_set_country_code(
    ad: android_device.AndroidDevice,
    country_code: str,
    force_telephony_cc: bool = False,
) -> None:
  """Sets Wi-Fi and Telephony country code."""
  ad.log.info('Set Wi-Fi country code to %s.', country_code)
  try:
    ad.adb.shell('cmd wifi set-wifi-enabled disabled')
    time.sleep(WIFI_COUNTRYCODE_CONFIG_TIME_SEC)
    if force_telephony_cc:
      ad.log.info('Set Telephony country code to %s.', country_code)
      ad.adb.shell(
          'am broadcast -a'
          ' com.android.internal.telephony.action.COUNTRY_OVERRIDE --es'
          f' country {country_code}'
      )
      toggle_airplane_mode(ad)
    ad.adb.shell(f'cmd wifi force-country-code enabled {country_code}')
    ad.adb.shell('cmd wifi set-wifi-enabled enabled')
    if force_telephony_cc:
      telephony_country_code = (
          ad.adb.shell('dumpsys wifi | grep mTelephonyCountryCode')
          .decode('utf-8')
          .strip()
      )
      ad.log.info('Telephony country code: %s', telephony_country_code)
  except adb.AdbError:
    ad.log.exception(
        'Failed to set country code on device %r.', ad.serial
    )


def enable_logs(ad: android_device.AndroidDevice) -> None:
  """Enables Nearby, WiFi and BT detailed logs."""
  op = 'adb shell'
  try:
    op = 'increase log buffer size'
    if ad.is_adb_root:
      # Increase log buffer size.
      ad.adb.shell('setprop persist.logd.size 8388608')  # 8M
    else:
      ad.adb.shell('logcat -G 5242880')  # 5M
    op = 'enable Nearby verbose logs'
    for tag in NEARBY_LOG_TAGS:
      ad.adb.shell(f'setprop log.tag.{tag} VERBOSE')

    # Enable WiFi verbose logging.
    ad.adb.shell('cmd wifi set-verbose-logging enabled')
    op = 'enable Bluetooth HCI logs'
    # Enable Bluetooth HCI logs.
    if ad.is_adb_root:
      ad.adb.shell('setprop persist.bluetooth.btsnooplogmode full')
    else:
      ad.log.info(
          'Skipped setting Bluetooth HCI logs on device,'
          'because we do not set Bluetooth HCI logs on unrooted phone.'
      )
    op = 'enable Bluetooth verbose logs'
    # Enable Bluetooth verbose logs.
    ad.adb.shell('setprop persist.log.tag.bluetooth VERBOSE')
  except adb.AdbError:
    ad.log.info('Failed to enable logs on device for "%s".', op)


def grant_manage_external_storage_permission(
    ad: android_device.AndroidDevice, package_name: str
) -> None:
  """Grants MANAGE_EXTERNAL_STORAGE permission to Nearby snippet."""
  try:
    _do_grant_manage_external_storage_permission(ad, package_name)
  except adb.AdbError:
    ad.log.exception(
        'Failed to grant MANAGE_EXTERNAL_STORAGE permission on device %r,'
        ' try again.',
        ad.serial,
    )
    time.sleep(ADB_RETRY_WAIT_TIME_SEC)
    _do_grant_manage_external_storage_permission(ad, package_name)


def _do_grant_manage_external_storage_permission(
    ad: android_device.AndroidDevice, package_name: str
) -> None:
  """Grants MANAGE_EXTERNAL_STORAGE permission to Nearby snippet."""
  build_version_sdk = int(ad.build_info['build_version_sdk'])
  if build_version_sdk < 30:
    return
  ad.log.info(
      'Grant MANAGE_EXTERNAL_STORAGE permission on device %r.', ad.serial
  )
  _grant_manage_external_storage_permission(ad, package_name)


def grant_permission(
    ad: android_device.AndroidDevice,
    pkg: str,
    permission: str,
) -> None:
  """Grants the Android permission to specific package."""
  try:
    if permission == 'android.permission.MANAGE_EXTERNAL_STORAGE':
      ad.adb.shell(f'appops set --uid {pkg} MANAGE_EXTERNAL_STORAGE allow')
      return
    # Get current user ID to grant permission to support multiuser devices
    # (go/supporting-hsum)
    user_id = ad.adb.shell(['am', 'get-current-user']).decode().strip()
    ad.adb.shell(['pm', 'grant', f'--user {user_id}', pkg, permission])
  except adb.AdbError as e:
    no_such_permission_error = (
        f'Package {pkg} has not requested permission {permission}'
    )
    if no_such_permission_error not in str(e):
      raise
    ad.log.warning(no_such_permission_error)


def dump_gms_version(ad: android_device.AndroidDevice) -> int | None:
  """Dumps GMS version from dumpsys to sponge properties."""
  gms_version = _do_dump_gms_version(ad)
  if gms_version is None:
    time.sleep(ADB_RETRY_WAIT_TIME_SEC)
    gms_version = _do_dump_gms_version(ad)
  return gms_version


def _do_dump_gms_version(ad: android_device.AndroidDevice) -> int | None:
  """Dumps GMS version from dumpsys to sponge properties."""
  try:
    out = (
        ad.adb.shell(
            'dumpsys package com.google.android.gms | grep "versionCode="'
        )
        .decode('utf-8')
        .strip()
    )
  except adb.AdbError:
    ad.log.exception(
        'Failed to dump GMS version on device %r, try again.', ad.serial
    )
    return None

  ad.log.info('GMS version: %s', out)
  prefix = 'versionCode='
  postfix = 'minSdk'
  search_last = False
  return get_int_between_prefix_postfix(out, prefix, postfix, search_last)


def toggle_airplane_mode(ad: android_device.AndroidDevice) -> None:
  """Toggles airplane mode on the given device."""
  ad.log.info('turn on airplane mode')
  enable_airplane_mode(ad)
  ad.log.info('turn off airplane mode')
  disable_airplane_mode(ad)


def connect_to_wifi_sta_till_success(
    ad: android_device.AndroidDevice, wifi_ssid: str, wifi_password: str
) -> datetime.timedelta:
  """Connecting to the specified wifi STA/AP."""
  ad.log.info('Start connecting to wifi STA/AP')
  wifi_connect_start = datetime.datetime.now()
  if not wifi_password:
    wifi_password = None
  connect_to_wifi(
      ad, wifi_ssid, wifi_password, num_retries=_WIFI_CONNECT_RETRY_TIMES
  )
  return datetime.datetime.now() - wifi_connect_start


def wifi_is_enabled(ad: android_device.AndroidDevice) -> bool:
  """Checks if wifi is enabled on the given device."""
  return ad.nearby.wifiCheckState(constants.WifiState.ENABLED)


def connect_to_wifi(
    ad: android_device.AndroidDevice,
    ssid: str,
    password: str | None = None,
    num_retries: int = 1,
) -> None:
  """Connects to the specified wifi AP and raise exception if failed."""
  if not wifi_is_enabled(ad):
    ad.nearby.wifiEnable()
  # return until the wifi is connected.
  wifi_password = password or None
  ad.log.info('Connect to wifi: ssid: %r, password: %r', ssid, wifi_password)
  for i in range(num_retries):
    try:
      ad.nearby.wifiConnectSimple(ssid, wifi_password)
      return
    except errors.ApiError:
      ad.log.warning(
          'Failed to connect to wifi %r, retry attempt %d', ssid, i + 1
      )
      if i < num_retries - 1:
        # Reset wifi to make sure the wifi state is clean.
        ad.nearby.wifiDisable()
        ad.nearby.wifiEnable()
        time.sleep(_WIFI_CONNECT_INTERVAL_SEC)
      else:
        ad.log.error(
            'Still failed to connect to wifi %r after %d attempts.',
            ssid,
            num_retries,
            exc_info=True,
        )
        raise


def remove_current_connected_wifi_network(
    ad: android_device.AndroidDevice,
) -> bool:
  """Removes the currently connected wifi network.

  Args:
    ad: The Android device to operate on.

  Returns:
    True if a network was found and removed, False otherwise.
  """
  wifi_info = ad.nearby.wifiGetConnectionInfo()
  if (
      not wifi_info
      or wifi_info.get('SupplicantState', '')
      == constants.WIFI_SUPPLICANT_STATE_DISCONNECTED
  ):
    ad.log.info('No current connected wifi network')
    return False

  network_id = get_sta_network_id_from_wifi_info(wifi_info)
  if network_id != constants.INVALID_NETWORK_ID:
    ad.log.info('disconnecting from %r', wifi_info.get('SSID', ''))
    ad.nearby.wifiRemoveNetwork(network_id)
  else:
    ad.log.warning(
        'No valid network id for %r, try to remove all networks.',
        wifi_info.get('SSID', ''),
    )
    remove_disconnect_wifi_network(ad)

  return True


def remove_disconnect_wifi_network(ad: android_device.AndroidDevice) -> None:
  """Removes and disconnects all wifi network on the given device."""
  was_wifi_enabled = ad.nearby.wifiIsEnabled()
  if was_wifi_enabled:
    # wifiClearConfiguredNetworks() calls getConfiguredNetworks() and
    # removeNetworks() which could take a long time to complete because these
    # calls have the complicated ownership check and wifi thread could be busy
    # with other tasks. Wifi thread is optimized in V but not in old releases.
    # Therefore let's disable wifi so that these calls can be completed on time.
    ad.nearby.wifiDisable()
  ad.log.info('Clear wifi configured networks')
  ad.nearby.wifiClearConfiguredNetworks()
  if was_wifi_enabled:
    ad.nearby.wifiEnable()
  time.sleep(constants.WIFI_DISCONNECTION_DELAY.total_seconds())


def wait_for_wifi_auto_join(
    ad: android_device.AndroidDevice,
    wifi_ssid: str,
    wifi_password: str,
) -> None:
  """Waits for the wifi connection after disruptive test."""
  initial_max_wait_time_sec = 6
  max_wait_time_sec = initial_max_wait_time_sec
  wifi_is_connected = ad.nearby.wifiIsConnected(wifi_ssid)
  while not wifi_is_connected and max_wait_time_sec > 0:
    time.sleep(1)
    wifi_is_connected = ad.nearby.wifiIsConnected(wifi_ssid)
    if not wifi_is_connected:
      ad.nearby.wifiConnectSimple(wifi_ssid, wifi_password)
    max_wait_time_sec -= 1
  ad.log.info(
      'Waiting %d seconds for'
      ' wifi connection after disruptive test, is the wifi sta connected:'
      ' %s',
      initial_max_wait_time_sec - max_wait_time_sec,
      wifi_is_connected,
  )


def _grant_manage_external_storage_permission(
    ad: android_device.AndroidDevice, package_name: str
) -> None:
  """Grants MANAGE_EXTERNAL_STORAGE permission to Nearby snippet.

  This permission will not grant automatically by '-g' option of adb install,
  you can check the all permission granted by:
  am start -a android.settings.APPLICATION_DETAILS_SETTINGS
           -d package:{YOUR_PACKAGE}

  Reference for MANAGE_EXTERNAL_STORAGE:
  https://developer.android.com/training/data-storage/manage-all-files

  This permission will reset to default "Allow access to media only" after
  reboot if you never grant "Allow management of all files" through system UI.
  The appops command and MANAGE_EXTERNAL_STORAGE only available on API 30+.

  Args:
    ad: AndroidDevice, Mobly Android Device.
    package_name: The nearbu snippet package name.
  """
  try:
    ad.adb.shell(
        f'appops set --uid {package_name} MANAGE_EXTERNAL_STORAGE allow'
    )
  except adb.Error:
    ad.log.info('Failed to grant MANAGE_EXTERNAL_STORAGE permission.')


def enable_airplane_mode(ad: android_device.AndroidDevice) -> None:
  """Enables airplane mode on the given device."""
  try:
    _do_enable_airplane_mode(ad)
  except adb.AdbError:
    ad.log.exception(
        'Failed to enable airplane mode on device %r, try again.', ad.serial
    )
    time.sleep(ADB_RETRY_WAIT_TIME_SEC)
    _do_enable_airplane_mode(ad)


def _do_enable_airplane_mode(ad: android_device.AndroidDevice) -> None:
  """Enables airplane mode on the given device."""
  if ad.is_adb_root:
    ad.adb.shell(['settings', 'put', 'global', 'airplane_mode_on', '1'])
    ad.adb.shell([
        'am',
        'broadcast',
        '-a',
        'android.intent.action.AIRPLANE_MODE',
        '--ez',
        'state',
        'true',
    ])
  ad.adb.shell(['svc', 'wifi', 'disable'])
  ad.adb.shell(['svc', 'bluetooth', 'disable'])
  time.sleep(TOGGLE_AIRPLANE_MODE_WAIT_TIME_SEC)


def disable_airplane_mode(ad: android_device.AndroidDevice) -> None:
  """Disables airplane mode on the given device."""
  try:
    _do_disable_airplane_mode(ad)
  except adb.AdbError:
    ad.log.exception(
        'Failed to disable airplane mode on device %r, try again.', ad.serial
    )
    time.sleep(ADB_RETRY_WAIT_TIME_SEC)
    _do_disable_airplane_mode(ad)


def _do_disable_airplane_mode(ad: android_device.AndroidDevice) -> None:
  """Disables airplane mode on the given device."""
  if ad.is_adb_root:
    ad.adb.shell(['settings', 'put', 'global', 'airplane_mode_on', '0'])
    ad.adb.shell([
        'am',
        'broadcast',
        '-a',
        'android.intent.action.AIRPLANE_MODE',
        '--ez',
        'state',
        'false',
    ])
  ad.adb.shell(['svc', 'wifi', 'enable'])
  ad.adb.shell(['svc', 'bluetooth', 'enable'])
  time.sleep(TOGGLE_AIRPLANE_MODE_WAIT_TIME_SEC)


def restart_gms(ad: android_device.AndroidDevice) -> None:
  """Restarts GMS on the given device."""
  ad.log.info(
      'Restart GMS. Note that the flag sync will NOT complete before Nearby'
      ' connection. Please ensure the default flags are correct or you override'
      ' in the test.'
  )
  ad.adb.shell('am force-stop com.google.android.gms')


def disable_gms_auto_updates(ad: android_device.AndroidDevice) -> None:
  """Disable GMS auto updates on the given device."""
  if not ad.is_adb_root:
    ad.log.warning(
        'You should disable the play store auto updates manually on a'
        'unrooted device, otherwise the test may be broken unexpected'
    )
  ad.log.info('try to disable GMS Auto Updates.')
  gms_auto_updates_util.GmsAutoUpdatesUtil(ad).disable_gms_auto_updates()
  time.sleep(_DISABLE_ENABLE_GMS_UPDATE_WAIT_TIME_SEC)


def enable_gms_auto_updates(ad: android_device.AndroidDevice) -> None:
  """Enable GMS auto updates on the given device."""
  if not ad.is_adb_root:
    ad.log.warning(
        'You may enable the play store auto updates manually on a'
        'unrooted device after test.'
    )
  ad.log.info('try to enable GMS Auto Updates.')
  gms_auto_updates_util.GmsAutoUpdatesUtil(ad).enable_gms_auto_updates()
  time.sleep(_DISABLE_ENABLE_GMS_UPDATE_WAIT_TIME_SEC)


def enable_location_on_device(ad: android_device.AndroidDevice) -> None:
  """Enable location on the given device."""
  try:
    ad.adb.shell('cmd location set-location-enabled true')
  except adb.AdbError:
    ad.log.exception(
        'Failed to enable location on the device. Make sure'
        ' location is enabled in the settings.'
    )


def get_sta_network_id_from_wifi_info(wifi_info: dict[str, Any]) -> int:
  """Get wifi STA network id on the given device."""
  # introduced for unrooted device.
  network_id = wifi_info.get('NetworkId', constants.INVALID_NETWORK_ID)
  # fallback for rooted device if the 'NetworkId' is not available.
  if network_id == constants.INVALID_NETWORK_ID:
    network_id = wifi_info.get('mNetworkId', constants.INVALID_NETWORK_ID)
  return network_id


def get_sta_rssi_from_wifi_info(wifi_info: dict[str, Any]) -> int:
  """Get wifi STA RSSI from the given wifi info."""
  # introduced for unrooted device.
  rssi = wifi_info.get('RSSI', constants.INVALID_RSSI)
  if rssi == constants.INVALID_RSSI:
    rssi = wifi_info.get('mRssi', constants.INVALID_RSSI)
  return rssi


def get_sta_frequency_from_wifi_info(wifi_info: dict[str, Any]) -> int:
  """Get wifi STA frequency from the given wifi info."""
  # introduced for unrooted device.
  sta_frequency = wifi_info.get('StaFrequency', constants.INVALID_INT)
  if sta_frequency == constants.INVALID_INT:
    sta_frequency = wifi_info.get('mFrequency', constants.INVALID_INT)
  return sta_frequency


def get_sta_max_link_speed_from_wifi_info(wifi_info: dict[str, Any]) -> int:
  """Get wifi STA max supported Tx link speed from the given wifi info."""
  # introduced for unrooted device.
  max_link_speed = wifi_info.get(
      'MaxSupportedTxLinkSpeedMbps', constants.INVALID_INT
  )
  if max_link_speed == constants.INVALID_INT:
    max_link_speed = wifi_info.get(
        'mMaxSupportedTxLinkSpeedMbps', constants.INVALID_INT
    )
  return max_link_speed


def _get_wifi_sta_frequency_from_dumpsys(
    ad: android_device.AndroidDevice,
) -> int:
  """Get wifi STA frequency on the given device."""
  wifi_sta_status = dump_wifi_sta_status(ad)
  if not wifi_sta_status:
    return constants.INVALID_INT
  prefix = 'Frequency:'
  postfix = 'MHz'
  return get_int_between_prefix_postfix(wifi_sta_status, prefix, postfix)


def get_wifi_p2p_frequency(ad: android_device.AndroidDevice) -> int:
  """Get wifi p2p frequency on the given device."""
  wifi_p2p_status = dump_wifi_p2p_status(ad)
  if not wifi_p2p_status:
    return constants.INVALID_INT
  prefix = 'channelFrequency='
  postfix = ', groupRole=GroupOwner'
  return get_int_between_prefix_postfix(wifi_p2p_status, prefix, postfix)


def _get_wifi_sta_max_link_speed_from_dumpsys(
    ad: android_device.AndroidDevice,
) -> int:
  """Get wifi STA max supported Tx link speed on the given device."""
  wifi_sta_status = dump_wifi_sta_status(ad)
  if not wifi_sta_status:
    return constants.INVALID_INT
  prefix = 'Max Supported Tx Link speed:'
  postfix = 'Mbps'
  return get_int_between_prefix_postfix(wifi_sta_status, prefix, postfix)


def get_int_between_prefix_postfix(
    string: str, prefix: str, postfix: str, search_last: bool = True
) -> int:
  """Get int between prefix and postfix by searching prefix and then postfix."""
  if search_last:
    left_index = string.rfind(prefix)
    right_index = string.rfind(postfix)
  else:
    left_index = string.find(prefix)
    right_index = string.find(postfix)
  if left_index >= 0 and right_index > left_index:
    try:
      return int(string[left_index + len(prefix) : right_index].strip())
    except ValueError:
      return constants.INVALID_INT
  return constants.INVALID_INT


def dump_wifi_sta_status(ad: android_device.AndroidDevice) -> str:
  """Dumps wifi STA status on the given device."""
  try:
    return (
        ad.adb.shell('cmd wifi status | grep WifiInfo').decode('utf-8').strip()
    )
  except adb.AdbError:
    return ''


def dump_wifi_p2p_status(ad: android_device.AndroidDevice) -> str:
  """Dumps wifi p2p status on the given device."""
  try:
    return ad.adb.shell('dumpsys wifip2p').decode('utf-8').strip()
  except adb.AdbError:
    return ''


def is_5g_band_supported(ad: android_device.AndroidDevice) -> bool:
  """Checks if 5G band is supported on the given device."""
  try:
    return ad.nearby.wifiIs5GHzBandSupported()
  except adb.AdbError:
    return False


def is_wifi_direct_supported(ad: android_device.AndroidDevice) -> bool:
  """Checks if WiFi Direct is supported on the given device."""
  try:
    return ad.nearby.wifiIsP2pSupported()
  except Exception as e:  # pylint: disable=broad-except
    ad.log.info('WiFi Direct is not supported due to %s', e)
    return False


def _parse_wifi_scan(scan_results: Iterable[str]) -> Sequence[dict[str, Any]]:
  """Parses the output of 'cmd wifi list-scan-results'.

  Args:
    scan_results: A list of strings, where each string is a line from the 'cmd
      wifi list-scan-results' output.

  Returns:
    A list of dictionaries, where each dictionary contains the 'SSID' and
    'Frequency' of a scanned Wi-Fi network.
  """
  results = []

  for line in scan_results:
    match = _WIFI_SCAN_PATTERN.search(line)
    if match:
      bssid, freq, raw_ssid, _ = match.groups()
      # If SSID is just whitespace, it means it's hidden/empty
      ssid = raw_ssid.strip() or constants.WIFI_UNKNOWN_SSID
      results.append({
          'BSSID': bssid,
          'SSID': ssid,
          'Frequency': int(freq),
      })
  return results


def check_wifi_env(
    ad: android_device.AndroidDevice,
) -> Sequence[dict[str, Any]] | None:
  """Let WI-FI scan and get scan results. Check if the environment is clean.

  Args:
    ad: AndroidDevice, Mobly Android Device.

  Returns:
    Wi-Fi scan results as a list of SSID and Frequency or None if it fails to
    get scan results.
  """
  # Initialize the number of BSSIDs found in the wifi scan.
  device_specific_info = get_betocq_device_specific_info(ad)
  device_specific_info['wifi_env_bssid_count'] = 0
  # Start wifi scan.
  try:
    ad.adb.shell('cmd wifi start-scan')
    time.sleep(WIFI_SCAN_WAIT_TIME_SEC)
  except adb.AdbError:
    ad.log.warning('Failed to start wifi scan.', exc_info=True)
    return None

  # List scanned result.
  try:
    wifi_scan_results = (
        ad.adb.shell('cmd wifi list-scan-results')
        .decode('utf-8')
        .strip()
        .splitlines()
    )
    # Exclude the header from the scan results.
    wifi_simple_results = _parse_wifi_scan(wifi_scan_results[1:])
    ad.log.info(
        'wifi scan results:\n%s',
        pprint.pformat(wifi_simple_results, sort_dicts=False),
    )
  except (adb.AdbError, ValueError):
    ad.log.warning('Failed to retrieve wifi scan results.', exc_info=True)
    return None

  num_of_bssid = len(wifi_simple_results)
  # Check the number of results against the threshold.
  if num_of_bssid > _CLEAN_WIFI_ENV_CHECK_BSSID_THRESHOLD:
    ad.log.warning(
        'Please clean up the Wi-Fi test environment: %d BSSIDs found, which is'
        ' more than the threshold of %d.',
        num_of_bssid,
        _CLEAN_WIFI_ENV_CHECK_BSSID_THRESHOLD,
    )
  else:
    ad.log.info('Wi-Fi test environment is clean.')

  # Update the number of BSSIDs found in the wifi scan.
  device_specific_info['wifi_env_bssid_count'] = num_of_bssid
  return wifi_simple_results


def is_valid_wifi_2g_freq(freq: int) -> bool:
  """Checks if the frequency is a valid 2G frequency."""
  return freq <= constants.MAX_FREQ_2G_MHZ


def is_valid_wifi_5g_freq(freq: int) -> bool:
  """Checks if the frequency is a valid 5G frequency."""
  return (
      constants.MAX_FREQ_2G_MHZ < freq < constants.MIN_FREQ_5G_DFS_MHZ
      or freq > constants.MAX_FREQ_5G_DFS_MHZ
  )


def is_valid_wifi_5g_dfs_freq(freq: int) -> bool:
  """Checks if the frequency is a valid 5G DFS frequency."""
  return (
      constants.MIN_FREQ_5G_DFS_MHZ
      <= freq
      <= constants.MAX_FREQ_5G_DFS_MHZ
  )


def is_aware_pairing_supported(ad: android_device.AndroidDevice) -> bool:
  """Checks if Aware pairing is supported on the given device."""
  try:
    # get the dumpsys output
    dumpsys_output = ad.adb.shell('dumpsys wifiaware').decode('utf-8')
    return 'isNanPairingSupported=true' in dumpsys_output
  except Exception as e:  # pylint: disable=broad-except
    ad.log.info('Aware pairing is not supported due to %s', e)
    return False


def wait_for_aware_pairing_supported(
    ad: android_device.AndroidDevice,
    timeout: datetime.timedelta = constants.WIFI_AWARE_AVAILABLE_WAIT_TIME,
) -> bool:
  """Waits for Wifi Aware pairing to be available on the given device."""
  return wait_for_predicate(
      lambda: is_aware_pairing_supported(ad),
      timeout,
      interval=datetime.timedelta(seconds=1),
  )


def is_wifi_aware_available(ad: android_device.AndroidDevice) -> bool:
  """Checks if Aware is supported on the given device."""
  try:
    return ad.nearby.wifiAwareIsAvailable()
  except Exception as e:  # pylint: disable=broad-except
    ad.log.info('Aware is not supported due to %s', e)
    return False


def wait_for_aware_available(
    ad: android_device.AndroidDevice,
    timeout: datetime.timedelta = constants.WIFI_AWARE_AVAILABLE_WAIT_TIME,
) -> bool:
  """Waits for Wifi Aware to be available on the given device."""
  return wait_for_predicate(
      lambda: is_wifi_aware_available(ad),
      timeout,
      interval=datetime.timedelta(seconds=1),
  )


def get_hardware(ad: android_device.AndroidDevice) -> str:
  """Gets hardware information on the given device."""
  return ad.adb.getprop('ro.hardware')


def get_wifi_sta_rssi(ad: android_device.AndroidDevice, ssid: str) -> int:
  """get the scan rssi of the given device and SSID."""
  try:
    scan_result = (
        ad.adb.shell(f'cmd wifi list-scan-results|grep {ssid}')
        .decode('utf-8')
        .strip()
    )
    if scan_result:
      return int(scan_result.split()[2].strip())
    return constants.INVALID_RSSI
  except (adb.AdbError, ValueError):
    ad.log.warning('Failed to get wifi sta rssi')
    return constants.INVALID_RSSI


def log_sta_event_list(ad: android_device.AndroidDevice):
  """Obtain the 'StaEventList' from dumpsys and place them in the logs."""
  try:
    # get the dumpsys output
    dumpsys_output = ad.adb.shell('dumpsys wifi')

    # processing
    lines = dumpsys_output.splitlines()
    sta_events = []
    in_section = False

    # retrieve the 'StaEventList' section from dumpsys output, ending
    # the retrieval at the next label -'UserActionEvents'.
    for line in lines:
      decoded_line = line.decode('utf-8').strip()
      if 'StaEventList' in decoded_line:
        in_section = True
        sta_events.append(decoded_line)
      elif 'UserActionEvents' in decoded_line and in_section:
        break
      elif in_section:
        sta_events.append(decoded_line)

    line_count = len(sta_events)

    # include in adb log the 'StaEventList' header found at the beginning of
    # 'sta_events' and add the data lines from 'sta_events'(for longer logs -
    # the return is 8 lines maximum counting from the end).
    max_sta_events_to_log = 8
    if line_count > 0:
      start_index = 1
      reminder = ''
      if line_count > max_sta_events_to_log + 1:
        start_index = line_count - max_sta_events_to_log  # show last lines
        reminder = f' (last {max_sta_events_to_log} lines)'

      ad.log.info('%s%s', sta_events[0], reminder)  # log the header
      # log the data lines
      for event in sta_events[start_index:line_count]:
        ad.log.info('%s', event)
    else:
      ad.log.warning('Warning: No "StaEventList" was found in dumpsys wifi')

  except adb.AdbError as e:
    ad.log.info('Error in log_sta_event_list %s', e)
    return


def _overrides_file_for_target(target: str) -> str:
  """Returns the resource path for the given target."""
  key = target.replace('//', 'google3/').replace(':', '/') + '_generated.txt'
  return resources.GetResourceFilename(key)


def _get_resource_contents(name: str) -> str:
  """Returns the contents of the given resource."""
  file_path = resources.GetResourceFilename(name)
  with open(file_path, 'r') as f:
    return f.read()


# set wifi tdls mode by using adb wl command. Only works with BRCM chipsets.
def set_wifi_tdls_mode_by_adb_wl_command(
    ad: android_device.AndroidDevice,
    enable_tdls: bool,
    catch_exception: bool = True,
) -> None:
  """Sets Wi-Fi TDLS mode on the given device by using adb wl command.

  Args:
    ad: AndroidDevice, Mobly Android Device.
    enable_tdls: True to enable TDLS, False to disable.
    catch_exception: True to catch exception, False to raise exception.
  """
  if not ad.is_adb_root:
    ad.log.info('Skipped setting wifi tdls mode on unrooted device.')
    return

  try:
    if enable_tdls:
      ad.adb.shell('wl tdls_enable')
      ad.log.info('Start wifi tdls through adb wl command')
    else:
      ad.adb.shell('wl tdls_enable 0')
      ad.log.info('Stop wifi tdls through adb wl command')
  except adb.AdbError:
    if not catch_exception:
      raise
    ad.log.warning('Failed to set wifi tdls mode.', exc_info=True)
    return


def set_wifi_tdls_mode_by_wifi_manager_api(
    ad: android_device.AndroidDevice,
    remote_ad: android_device.AndroidDevice,
    *,
    enable_tdls: bool,
    snippet_name: str,
    catch_exception: bool = True,
) -> None:
  """Sets Wi-Fi TDLS mode on the given device by using WifiManager API.

  Args:
    ad: AndroidDevice, Mobly Android Device.
    remote_ad: AndroidDevice, the remote device to get IP address from.
    enable_tdls: True to enable TDLS, False to disable.
    snippet_name: The name of the snippet (e.g., 'nearby').
    catch_exception: True to catch exception, False to raise exception.

  Raises:
    AttributeError: If `snippet_name` is not a valid attribute of the device.
    adb.AdbError: If an ADB command fails and `catch_exception` is False.
    ValueError: If parsing the IP address from `cmd wifi status` fails and
      `catch_exception` is False.
  """
  snippet = getattr(ad, snippet_name)
  # WifiManager.setTdlsEnabled() doesn't work with Pixel devices.
  # Use the wl command instead.
  remote_ip_address = None
  try:
    remote_status = (
        remote_ad.adb.shell('cmd wifi status').decode('utf-8').strip()
    )
    for line in remote_status.splitlines():
      if 'WifiInfo:' in line:
        match = re.search(r'IP: /((?:[0-9]{1,3}\.){3}[0-9]{1,3})', line)
        if match:
          remote_ip_address = match.group(1)
          break
    if remote_ip_address is None:
      remote_ad.log.warning('Cannot find IP address in "cmd wifi status".')
      return
  except ValueError:
    if not catch_exception:
      raise
    remote_ad.log.warning('Failed to get IP address from remote device.')
    return

  # ad.log.info(f'Remote device IP address: {remote_ip_address}')
  snippet.wifiSetTdlsEnable(remote_ip_address, enable_tdls)
  ad.log.info('Set wifi tdls mode to %s', enable_tdls)


def set_flags(
    ad: android_device.AndroidDevice,
    output_path: str,
):
  """Sets default flags on the given device."""
  ad.log.info('Installing hermetic overrides from %s', _DEFAULT_OVERRIDES)
  install_overrides(ad, output_path, _DEFAULT_OVERRIDES, False)


def set_flag_wifi_direct_hotspot_off(
    ad: android_device.AndroidDevice,
    output_path: str,
):
  """Turn off the flag use_wifi_direct_hotspot on the given device."""
  ad.log.info('turn off wifi direct hotspot')
  install_overrides(
      ad,
      output_path,
      _WIFI_DIRECT_HOTSPOT_OFF_OVERRIDES,
      False,
  )


def install_overrides(
    ad: android_device.AndroidDevice,
    output_path: str,
    target: str,
    merge_with_existing_overrides: bool,
):
  """Installs overrides on the given device."""
  if not ad.is_adb_root:
    ad.log.info('Skipped installing hermetic overrides on unrooted device.')
    return

  template_content = _get_resource_contents(_FLAG_SETUP_TEMPLATE_KEY)
  ad.log.info('Installing hermetic overrides from %s', target)
  hermetic_overrides_partner.install_hermetic_overrides(
      ad,
      _overrides_file_for_target(target),
      output_path,
      _GMS_PACKAGE,
      template_content,
      merge_with_existing_overrides=merge_with_existing_overrides,
  )
  restart_gms(ad)


def clear_hermetic_overrides(
    ad: android_device.AndroidDevice,
    restart_gms_process: bool = True,
) -> None:
  """Clear hermetic overrides.

  Args:
    ad: AndroidDevice, Mobly Android Device.
    restart_gms_process: Whether to restart GMS process after clearing
      overrides.
  """
  if not ad.is_adb_root:
    ad.log.info('Skipped clearing hermetic overrides on unrooted device.')
    return

  ad.adb.shell(
      'rm -f'
      ' /data/user_de/0/com.google.android.gms/app_phenotype_hermetic/overrides.txt'
  )
  ad.log.info('Cleared hermetic flags override.')
  if restart_gms_process:
    restart_gms(ad)


def get_sta_frequency_and_max_link_speed(
    ad: android_device.AndroidDevice,
    connection_info: dict[str, Any] | None = None,
) -> tuple[int, int]:
  """Gets the STA frequency and max link speed."""
  if connection_info is None:
    connection_info = ad.nearby.wifiGetConnectionInfo()
  sta_frequency = get_sta_frequency_from_wifi_info(connection_info)
  sta_max_link_speed_mbps = get_sta_max_link_speed_from_wifi_info(
      connection_info
  )

  # If the info is not available, try getting them by adb wifi status command.
  if sta_frequency == constants.INVALID_INT:
    sta_frequency = _get_wifi_sta_frequency_from_dumpsys(ad)
    sta_max_link_speed_mbps = _get_wifi_sta_max_link_speed_from_dumpsys(ad)
  return (sta_frequency, sta_max_link_speed_mbps)


def get_target_sta_frequency_and_max_link_speed(
    ad: android_device.AndroidDevice,
) -> tuple[int, int]:
  """Gets the STA frequency and max link speed."""
  connection_info = ad.nearby.wifiGetConnectionInfo()
  sta_frequency = get_sta_frequency_from_wifi_info(connection_info)
  sta_max_link_speed_mbps = get_sta_max_link_speed_from_wifi_info(
      connection_info
  )

  # If the info is not available, try getting them by adb wifi status command.
  if sta_frequency == constants.INVALID_INT:
    sta_frequency = _get_wifi_sta_frequency_from_dumpsys(ad)
    sta_max_link_speed_mbps = _get_wifi_sta_max_link_speed_from_dumpsys(ad)
  return (sta_frequency, sta_max_link_speed_mbps)


def load_nearby_snippet(
    ad: android_device.AndroidDevice,
    config: constants.SnippetConfig,
):
  """Loads a nearby snippet with the given snippet config."""
  device_specific_dict = get_betocq_device_specific_info(ad)

  if config.apk_path:
    key_apk_installed = config.package_name + '_installed'
    if not device_specific_dict.get(key_apk_installed, False):
      ad.log.info('try to install snippet apk')
      apk_utils.install(ad, config.apk_path)
      device_specific_dict[key_apk_installed] = True
  else:
    ad.log.warning(
        ' apk path is not specified, '
        'make sure it is installed in the device'
    )
  if not device_specific_dict.get('external_storage_permission_granted', False):
    ad.log.info('grant manage external storage permission')
    grant_manage_external_storage_permission(ad, config.package_name)
    device_specific_dict['external_storage_permission_granted'] = True

  ad.load_snippet(config.snippet_name, config.package_name)


def unload_nearby_snippet(
    ad: android_device.AndroidDevice,
    config: constants.SnippetConfig,
):
  """Unloads a nearby snippet with the given snippet config."""
  device_specific_dict = get_betocq_device_specific_info(ad)
  key_apk_installed = config.package_name + '_installed'
  try:
    ad.unload_snippet(config.snippet_name)
    if device_specific_dict.get(key_apk_installed, False):
      ad.log.info('try to uninstall snippet_apk')
      apk_utils.uninstall(ad, config.package_name)
      device_specific_dict[key_apk_installed] = False
  except (adb.AdbError, snippet_management_service.Error):
    ad.log.warning('Failed to unload snippet_apk.')


def wait_for_predicate(
    predicate: Callable[[], bool],
    timeout: datetime.timedelta,
    interval: datetime.timedelta | None = None,
) -> bool:
  """Returns True if the predicate returns True within the given timeout.

  Any exception raised in the predicate will terminate the wait immediately.

  Args:
    predicate: A predicate function.
    timeout: The timeout to wait.
    interval: The interval time between each check of the predicate.

  Returns:
    Whether the predicate returned True within the given timeout.
  """
  start_time = time.monotonic()
  deadline = start_time + timeout.total_seconds()
  while time.monotonic() < deadline:
    if predicate():
      return True
    if interval is not None:
      time.sleep(interval.total_seconds())
  return False


def get_thermal_zone_data(
    ad: android_device.AndroidDevice,
) -> dict[str, int]:
  """Reads and logs temperature and type from /sys/class/thermal/thermal_zone*.

  Args:
    ad: AndroidDevice, Mobly Android Device.

  Returns:
    A dictionary mapping thermal zone types to their temperatures in integer
    format, or an empty dictionary if data could not be retrieved.
  """
  thermal_data = []
  try:
    if not ad.is_adb_root:
      ad.log.info('Skipped getting thermal zone data on unrooted device.')
      return {}

    thermal_zones = (
        ad.adb.shell('ls /sys/class/thermal | grep thermal_zone')
        .decode('utf-8')
        .splitlines()
    )
  except adb.AdbError:
    ad.log.exception('Failed to list thermal zones.')
    return {}

  for zone_name in thermal_zones:
    zone_name = zone_name.strip()
    zone_path = f'/sys/class/thermal/{zone_name}'
    try:
      zone_type = ad.adb.shell(f'cat {zone_path}/type').decode('utf-8').strip()
      temp_str = ad.adb.shell(f'cat {zone_path}/temp').decode('utf-8').strip()
      try:
        temp = int(temp_str)
        if temp > 0:
          thermal_data.append((zone_type, temp))
        else:
          ad.log.debug(
              'Ignoring thermal zone %s with temp %s <= 0', zone_path, temp_str
          )
      except ValueError:
        ad.log.debug(
            'Failed to parse temperature %r from %s', temp_str, zone_path
        )
    except adb.AdbError:
      ad.log.debug('Failed to read thermal zone %s.', zone_path, exc_info=True)
      continue
  ad.log.info('Thermal zone data: %s', pprint.pformat(thermal_data))
  # Return the thermal data in a dict for easier access.
  return {zone_type: temp for zone_type, temp in thermal_data}


def abort_if_on_unrooted_device(
    ads: list[android_device.AndroidDevice],
    reason: str,
) -> None:
  """Aborts test class if any device is not rooted."""
  failed_messages = f'skipping the test on unrooted devices. due to {reason}'
  for ad in ads:
    asserts.abort_class_if(
        not ad.is_adb_root,
        failed_messages,
    )


def report_error_on_setup_class(
    test: base_test.BaseTestClass,
    error_message: str,
    abort_all: bool = False,
    error_class: type[signals.TestSignal] = signals.TestAbortClass,
) -> None:
  """Reports an error on setup class and aborts all test in the suite or class.

  Generally, result store/sponge takes such error as skip; with this method,
  this will be taken as error/failure.

  Args:
    test: The Mobly base test class instance.
    error_message: The message to include in the abort signal.
    abort_all: If True, aborts all tests in all classes, otherwise aborts all
      tests in the current class.
    error_class: The specific TestSignal class to raise if abort_all is False.
  """
  test_result_record = records.TestResultRecord(
      base_test.STAGE_NAME_SETUP_CLASS,
      test.TAG,
  )
  test_result_record.test_begin()
  if abort_all:
    termination_signal = signals.TestAbortAll(
        f'Aborting all tests due to {error_message}.'
    )
  else:
    if issubclass(error_class, signals.TestAbortClass):
      termination_signal = error_class(
          f'Aborting all tests in current class due to {error_message}.'
      )
    else:
      termination_signal = error_class(error_message)

  test_result_record.test_fail(termination_signal)
  test.results.add_class_error(test_result_record)
  test.summary_writer.dump(
      test_result_record.to_dict(), records.TestSummaryEntryType.RECORD
  )
  raise termination_signal


def abort_if_2g_ap_not_ready(
    test_parameters: constants.TestParameters,
) -> None:
  """Aborts test class if 2G AP is not ready."""
  if test_parameters.use_programmable_ap:
    return
  asserts.abort_class_if(
      not test_parameters.wifi_2g_ssid, '2G AP is not ready for this test.'
  )


def abort_if_5g_ap_not_ready(
    test_parameters: constants.TestParameters,
) -> None:
  """Aborts test class if 5G AP is not ready."""
  if test_parameters.use_programmable_ap:
    return
  asserts.abort_class_if(
      not test_parameters.wifi_5g_ssid, '5G AP is not ready for this test.'
  )


def abort_if_dfs_5g_ap_not_ready(
    test_parameters: constants.TestParameters,
) -> None:
  """Aborts test class if DFS 5G AP is not ready."""
  if test_parameters.use_programmable_ap:
    return
  asserts.abort_class_if(
      not test_parameters.wifi_dfs_5g_ssid,
      '5G DFS AP is not ready for this test.',
  )


def abort_if_any_5g_or_dfs_aps_not_ready(
    test_parameters: constants.TestParameters,
) -> None:
  """Aborts test class if any 5G or DFS 5G APs is not ready."""
  asserts.abort_class_if(
      test_parameters.use_programmable_ap,
      'Programmable AP does not support 5G and DFS 5G at the same time yet.',
  )
  asserts.abort_class_if(
      not test_parameters.wifi_5g_ssid,
      '5G AP is not ready. This test requires both 5G and 5G DFS APs.',
  )
  asserts.abort_class_if(
      not test_parameters.wifi_dfs_5g_ssid,
      '5G DFS AP is not ready. This test requires both 5G and 5G DFS APs.',
  )


def abort_if_5g_band_not_supported(
    ads: list[android_device.AndroidDevice],
) -> None:
  """Skips test class if any device does not support 5G band."""
  for ad in ads:
    asserts.abort_class_if(
        not is_5g_band_supported(ad),
        f'5G band is not supported on the device {ad}, skip the whole test.',
    )


def abort_if_5g_band_supported(
    ads: list[android_device.AndroidDevice],
) -> None:
  """Aborts test class if any device supports 5G band."""
  for ad in ads:
    asserts.abort_class_if(
        is_5g_band_supported(ad),
        f'5G band is supported on the device {ad}, skip the whole test.',
    )


def abort_if_wifi_direct_not_supported(
    ads: list[android_device.AndroidDevice],
) -> None:
  """Aborts test class if any device does not support Wi-Fi Direct."""
  for ad in ads:
    asserts.abort_class_if(
        not is_wifi_direct_supported(ad),
        f'Wifi Direct is not supported on the device {ad}.',
    )


def abort_if_wifi_hotspot_not_supported(
    ads: list[android_device.AndroidDevice],
) -> None:
  """Aborts test class if any device does not support Wi-Fi Hotspot."""
  for ad in ads:
    # We are checking Wi-Fi Direct capability here because Wi-Fi Hotspot is
    # implemented using Wi-Fi Direct in NC.
    asserts.abort_class_if(
        not is_wifi_direct_supported(ad),
        f'Wifi Hotspot is not supported on the device {ad}.',
    )


def abort_if_wifi_aware_not_available(
    ads: list[android_device.AndroidDevice],
) -> None:
  """Aborts test class if Wi-Fi Aware is not available in any device."""
  for ad in ads:
    # The utility function waits a small time. This is because Aware is not
    # immediately available after enabling WiFi.
    asserts.abort_class_if(
        not wait_for_aware_available(ad),
        f'Wifi Aware is not available in the device {ad}.',
    )


def abort_if_wifi_aware_pairing_not_supported(
    ads: list[android_device.AndroidDevice],
) -> None:
  """Aborts test class if Wi-Fi Aware pairing is not supported in any device."""
  for ad in ads:
    # The utility function waits a small time. This is because Aware is not
    # immediately available after enabling WiFi.
    asserts.abort_class_if(
        not wait_for_aware_pairing_supported(ad),
        f'Wifi Aware pairing is not supported in the device {ad}.',
    )


def abort_if_device_cap_not_match(
    ads: list[android_device.AndroidDevice],
    attribute_name: str,
    expected_value: bool,
) -> None:
  """Aborts class if the device capability does not match the expected value."""
  for ad in ads:
    actual_value = getattr(ad, attribute_name)
    asserts.abort_class_if(
        actual_value != expected_value,
        (
            f'{ad}, "{attribute_name}" is'
            f' {"enabled" if actual_value else "disabled"}, which does not'
            ' match test case requirement.'
        ),
    )


def reset_nearby_connection(
    ad: android_device.AndroidDevice,
) -> None:
  """Resets Nearby Connection on the given device.

  Safe guard for the failure test, in case the previous test failed in the
  middle of the NC, this function makes the NC be reset in best effort properly.

  Args:
    ad: A AndroidDevice instances.
  """
  ad.log.info('reset_nearby_connection')
  for prop in ['nearby', 'nearby2', 'nearby3']:
    if nearby := getattr(ad, prop, None):
      nearby.stopAdvertising()
      nearby.stopDiscovery()
      nearby.stopAllEndpoints()
  time.sleep(constants.NEARBY_RESET_WAIT_TIME.total_seconds())


_Priority = Literal['d', 'e', 'f', 'i', 'v', 'w', 's']


def log_message_to_logcat(
    ad: android_device.AndroidDevice,
    message: str,
    tag: str = 'BetoCQ',
    priority: _Priority = 'd',
):
  """logs a message to logcat.

  Args:
    ad: A AndroidDevice instances.
    message: The message to log.
    tag: The tag of the log.
    priority: The priority of the log. Default is 'd' (debug). d: DEBUG  e:
      ERROR  f: FATAL  i: INFO  v: VERBOSE  w: WARN  s: SILENT
  """
  try:
    ad.adb.shell(f'log -p {priority} -t {tag} "{message}"')
  except adb.AdbError:
    ad.log.warning(
        'Failed to log message to logcat on device %r.',
        ad.serial,
    )


def is_gms_version_above_required_version(
    ad: android_device.AndroidDevice, required_version: int
) -> bool:
  """Checks if the GMS version is above the required version."""
  gms_version = dump_gms_version(ad)
  if gms_version is None:
    ad.log.warning(
        'Failed to get GMS version on device %r, assuming it is below the'
        ' required version.',
        ad.serial,
    )
    return False
  return int(gms_version) >= required_version


def is_nc_wlan_file_transfer_flaky_issue_fixed(
    advertiser: android_device.AndroidDevice,
) -> bool:
  """Checks if the nearby connection WLAN file transfer flaky issue is fixed.

  See (internal) for details.

  Args:
    advertiser: The AndroidDevice instance.

  Returns:
    True if the GMS version is above the required version, False otherwise.
  """
  return is_gms_version_above_required_version(advertiser, 260200000)


def clear_all_accessibility_services(
    ad: android_device.AndroidDevice,
) -> None:
  """Clears accessibility services on the given device."""
  if not ad.is_adb_root:
    ad.log.warning(
        'Skipped clearing accessibility services on unrooted device. Your'
        ' test might fail because accessibility services were enabled by'
        ' others.'
    )
    return
  try:
    ad.adb.shell('settings delete secure enabled_accessibility_services')
  except adb.AdbError:
    ad.log.warning(
        'Failed to clear accessibility services on device %r.',
        ad.serial,
    )


def get_wifi_concurrency_mode(
    p2p_frequency: int,
    sta_frequency: int,
    is_dbs_mode_mattered: bool = False,
    dbs_wfd_status: constants.WifiDbsWfdStatus = constants.WifiDbsWfdStatus.UNKNOWN,
) -> constants.WifiConcurrencyMode:
  """Gets the wifi concurrency mode of the device."""
  if (
      p2p_frequency == constants.INVALID_INT
      or sta_frequency == constants.INVALID_INT
  ):
    return constants.WifiConcurrencyMode.UNKNOWN

  is_p2p_2g = p2p_frequency <= constants.MAX_FREQ_2G_MHZ
  is_sta_2g = sta_frequency <= constants.MAX_FREQ_2G_MHZ

  if p2p_frequency == sta_frequency:
    if is_p2p_2g:
      return constants.WifiConcurrencyMode.SCC_2G
    else:
      return constants.WifiConcurrencyMode.SCC_5G

  if is_dbs_mode_mattered:
    if dbs_wfd_status == constants.WifiDbsWfdStatus.DBS_WFD_ENABLED:
      if is_p2p_2g:
        return constants.WifiConcurrencyMode.SCC_2G
      else:
        return constants.WifiConcurrencyMode.SCC_5G
    elif dbs_wfd_status == constants.WifiDbsWfdStatus.DBS_WFD_DISABLED:
      if is_p2p_2g and not is_sta_2g:
        return constants.WifiConcurrencyMode.MCC_2G_P2P_5G_STA
      elif not is_p2p_2g and is_sta_2g:
        return constants.WifiConcurrencyMode.MCC_5G_P2P_2G_STA
      elif not is_p2p_2g and not is_sta_2g:
        return constants.WifiConcurrencyMode.MCC_5G_P2P_5G_STA
      else:  # both 2g but different freq
        return constants.WifiConcurrencyMode.UNKNOWN
    else:  # UNKNOWN dbs status
      return constants.WifiConcurrencyMode.UNKNOWN

  # if is_dbs_mode_mattered=False, then calculate MCC based on band
  if is_p2p_2g and not is_sta_2g:
    return constants.WifiConcurrencyMode.MCC_2G_P2P_5G_STA
  elif not is_p2p_2g and is_sta_2g:
    return constants.WifiConcurrencyMode.MCC_5G_P2P_2G_STA
  elif not is_p2p_2g and not is_sta_2g:
    return constants.WifiConcurrencyMode.MCC_5G_P2P_5G_STA
  else:  # both 2g but different freq
    return constants.WifiConcurrencyMode.UNKNOWN


def get_wifi_firmware_version(
    ad: android_device.AndroidDevice,
) -> str:
  """Gets the Wi-Fi firmware version on the given device."""
  try:
    version = ad.adb.getprop('vendor.wlan.firmware.version')
  except (adb.AdbError):
    ad.log.warning(
        'Failed to get Wi-Fi firmware version on device %r.',
        ad.serial,
        exc_info=True,
    )
    return 'adb error'
  return version


def get_bt_firmware_version(
    ad: android_device.AndroidDevice,
) -> str:
  """Gets the BT firmware version on the given device."""
  try:
    bt_dumpsys_output = (
        ad.adb.shell(
            'dumpsys android.hardware.bluetooth.IBluetoothHci/default'
        )
        .strip()
        .decode('utf-8')
    )
  except (adb.AdbError, ValueError):
    ad.log.warning(
        'Failed to get BT firmware version on device %r.',
        ad.serial,
        exc_info=True,
    )
    return _UNKNOWN_BT_FIRMWARE_VERSION

  if not bt_dumpsys_output:
    ad.log.warning(
        'BT IBluetoothHci dumpsys output is empty on device %r.',
        ad.serial,
    )
    return _UNKNOWN_BT_FIRMWARE_VERSION

  try:
    version = _extract_bt_firmware_version(ad, bt_dumpsys_output)
  except (TypeError, ValueError):
    ad.log.warning(
        'Failed to extract BT firmware version on device %r.',
        ad.serial,
        exc_info=True,
    )
    return _UNKNOWN_BT_FIRMWARE_VERSION
  return version


def _extract_bt_firmware_version(
    ad: android_device.AndroidDevice,
    bt_dumpsys_output: str) -> str:
  """Extracts Bluetooth controller firmware version from dumpsys output.

  Args:
    ad: AndroidDevice, Mobly Android Device.
    bt_dumpsys_output: A string containing the output from the dumpsys
      BT command.

  Returns:
      A string containing the firmware version, or None if not found.
  """
  lines = bt_dumpsys_output.splitlines()
  header_keywords = [
      'Firmware Version',
      'Firmware Information',
      'Firmware Info',
      'Firmware Ver',
      'FW Version',
      'FW Information',
      'FW Info',
      'FW Ver',
  ]

  for i, line in enumerate(lines):
    line_lower = line.lower()
    for lower_keyword in [keyword.lower() for keyword in header_keywords]:
      if lower_keyword in line_lower:
        # The firmware version is expected on the next non-empty line
        # after the header and its separator line.
        for j in range(i + 1, len(lines)):
          next_line = lines[j].strip()
          if not next_line:  # Skip empty lines
            continue

          # Skip separator lines
          if (
              '====' in next_line
              or '----' in next_line
              or '****' in next_line
              or '════' in next_line
              or next_line.startswith('╠══')
          ):
            ad.log.info('Skip separator line: %s', next_line)
            continue

          # Attempt to extract the version string
          # Remove potential leading characters like '║' and extra spaces
          match = re.search(r'^(?:║\s*)?(?P<version>.+)$', next_line)
          if match:
            version = match.group('version').strip()
            ad.log.info('version: %s', version)
            # Basic check to ensure it looks like a version string
            if ('FW' in version or 'Firmware' in version or
                re.search(r'[0-9a-fA-F]{6,}', version)):
              return version
          break  # Stop searching after checking the line(s) below the header
        break  # Move to the next line in the dumpsys output
  return _UNKNOWN_BT_FIRMWARE_VERSION
