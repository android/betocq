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

from collections.abc import Callable
import datetime
import re
import time
from typing import Any, Literal

from mobly import asserts
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import adb
from mobly.controllers.android_device_lib import apk_utils

from betocq.gms import hermetic_overrides_partner
from betocq import gms_auto_updates_util
from betocq import nc_constants
from betocq import resources

_DEFAULT_OVERRIDES = '//wireless/android/platform/testing/bettertogether/betocq:default_overrides'
    '//wireless/android/platform/testing/bettertogether/betocq:dct_on_overrides'
)
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

MAX_SSID_THRESHOLD = 10

read_ph_flag_failed = False

NEARBY_LOG_TAGS = [
    'Nearby',
    'NearbyMessages',
    'NearbyDiscovery',
    'NearbyConnections',
    'NearbyMediums',
    'NearbySetup',
]


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
  if not ad.is_adb_root:
    ad.log.info(
        f'Skipped setting wifi country code on device "{ad.serial}" '
        'because we do not set country code on unrooted phone.'
    )
    return
  try:
    _do_set_country_code(ad, country_code, force_telephony_cc)
  except adb.AdbError:
    ad.log.exception(
        f'Failed to set country code on device "{ad.serial}, try again.'
    )
    time.sleep(ADB_RETRY_WAIT_TIME_SEC)
    _do_set_country_code(ad, country_code)


def _do_set_country_code(
    ad: android_device.AndroidDevice,
    country_code: str,
    force_telephony_cc: bool = False,
) -> None:
  """Sets Wi-Fi and Telephony country code."""
  ad.log.info(f'Set Wi-Fi country code to {country_code}.')
  ad.adb.shell('cmd wifi set-wifi-enabled disabled')
  time.sleep(WIFI_COUNTRYCODE_CONFIG_TIME_SEC)
  if force_telephony_cc:
    ad.log.info(f'Set Telephony country code to {country_code}.')
    ad.adb.shell(
        'am broadcast -a com.android.internal.telephony.action.COUNTRY_OVERRIDE'
        f' --es country {country_code}'
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
    ad.log.info(f'Telephony country code: {telephony_country_code}')


def enable_logs(ad: android_device.AndroidDevice) -> None:
  """Enables Nearby, WiFi and BT detailed logs."""
  ad.log.info('Enable Nearby loggings.')
  if ad.is_adb_root:
    # Increase log buffer size.
    ad.adb.shell('setprop persist.logd.size 8388608')  # 8M
  else:
    try:
      ad.adb.shell('logcat -G 5242880')  # 5M
    except adb.AdbError:
      ad.log.info('Failed to increase log buffer size on device.')

  for tag in NEARBY_LOG_TAGS:
    ad.adb.shell(f'setprop log.tag.{tag} VERBOSE')

  # Enable WiFi verbose logging.
  ad.adb.shell('cmd wifi set-verbose-logging enabled')

  # Enable Bluetooth HCI logs.
  if ad.is_adb_root:
    ad.adb.shell('setprop persist.bluetooth.btsnooplogmode full')
  else:
    ad.log.info(
        'Skipped setting Bluetooth HCI logs on device,'
        'because we do not set Bluetooth HCI logs on unrooted phone.'
    )

  # Enable Bluetooth verbose logs.
  ad.adb.shell('setprop persist.log.tag.bluetooth VERBOSE')


def grant_manage_external_storage_permission(
    ad: android_device.AndroidDevice, package_name: str
) -> None:
  """Grants MANAGE_EXTERNAL_STORAGE permission to Nearby snippet."""
  try:
    _do_grant_manage_external_storage_permission(ad, package_name)
  except adb.AdbError:
    ad.log.exception(
        'Failed to grant MANAGE_EXTERNAL_STORAGE permission on device'
        f' "{ad.serial}", try again.'
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
      f'Grant MANAGE_EXTERNAL_STORAGE permission on device "{ad.serial}".'
  )
  _grant_manage_external_storage_permission(ad, package_name)


def dump_gms_version(ad: android_device.AndroidDevice) -> int:
  """Dumps GMS version from dumpsys to sponge properties."""
  try:
    gms_version = _do_dump_gms_version(ad)
  except adb.AdbError:
    ad.log.exception(
        f'Failed to dump GMS version on device "{ad.serial}", try again.'
    )
    time.sleep(ADB_RETRY_WAIT_TIME_SEC)
    gms_version = _do_dump_gms_version(ad)
  return gms_version


def _do_dump_gms_version(ad: android_device.AndroidDevice) -> int:
  """Dumps GMS version from dumpsys to sponge properties."""
  out = (
      ad.adb.shell(
          'dumpsys package com.google.android.gms | grep "versionCode="'
      )
      .decode('utf-8')
      .strip()
  )
  ad.log.info(f'GMS version: {out}')
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
  connect_to_wifi(ad, wifi_ssid, wifi_password)
  return datetime.datetime.now() - wifi_connect_start


def connect_to_wifi(
    ad: android_device.AndroidDevice,
    ssid: str,
    password: str | None = None,
) -> None:
  """Connects to the specified wifi AP and raise exception if failed."""
  if not ad.nearby.wifiIsEnabled():
    ad.nearby.wifiEnable()
  # return until the wifi is connected.
  password = password or None
  ad.log.info('Connect to wifi: ssid: %s, password: %s', ssid, password)
  ad.nearby.wifiConnectSimple(ssid, password)


def remove_current_connected_wifi_network(
    ad: android_device.AndroidDevice,
) -> bool:
  """Removes and disconnects the current connected wifi network on the given device."""
  wifi_info = ad.nearby.wifiGetConnectionInfo()
  if (
      not wifi_info
      or wifi_info.get('SupplicantState', '')
      == nc_constants.WIFI_SUPPLICANT_STATE_DISCONNECTED
  ):
    ad.log.info('No current connected wifi network')
    return False

  network_id = get_sta_network_id_from_wifi_info(wifi_info)
  if network_id != nc_constants.INVALID_NETWORK_ID:
    ad.log.info(f'disconnecting from {wifi_info.get("SSID", "")}')
    ad.nearby.wifiRemoveNetwork(network_id)
  else:
    ad.log.warning(
        f'No valid network id for {wifi_info.get("SSID", "")}, try'
        ' to remove all networks.'
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
  time.sleep(nc_constants.WIFI_DISCONNECTION_DELAY.total_seconds())


def wait_for_wifi_auto_join(
    ad: android_device.AndroidDevice,
    wifi_ssid: str,
    wifi_password: str,
) -> None:
  """Waits for the wifi connection after disruptive test."""
  initial_max_wait_time_sec = 6
  max_wait_time_sec = initial_max_wait_time_sec
  wifi_is_connected = ad.nearby.isWifiConnected()
  while not wifi_is_connected and max_wait_time_sec > 0:
    time.sleep(1)
    wifi_is_connected = ad.nearby.isWifiConnected()
    if not wifi_is_connected:
      ad.nearby.wifiConnectSimple(wifi_ssid, wifi_password)
    max_wait_time_sec -= 1
  ad.log.info(
      f'Waiting {initial_max_wait_time_sec - max_wait_time_sec} seconds for'
      ' wifi connection after disruptive test, is the wifi sta connected:'
      f' {wifi_is_connected}'
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
        f'Failed to enable airplane mode on device "{ad.serial}", try again.'
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
        f'Failed to disable airplane mode on device "{ad.serial}", try again.'
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
  network_id = wifi_info.get('NetworkId', nc_constants.INVALID_NETWORK_ID)
  # fallback for rooted device if the 'NetworkId' is not available.
  if network_id == nc_constants.INVALID_NETWORK_ID:
    network_id = wifi_info.get('mNetworkId', nc_constants.INVALID_NETWORK_ID)
  return network_id


def get_sta_rssi_from_wifi_info(wifi_info: dict[str, Any]) -> int:
  """Get wifi STA RSSI from the given wifi info."""
  # introduced for unrooted device.
  rssi = wifi_info.get('RSSI', nc_constants.INVALID_RSSI)
  if rssi == nc_constants.INVALID_RSSI:
    rssi = wifi_info.get('mRssi', nc_constants.INVALID_RSSI)
  return rssi


def get_sta_frequency_from_wifi_info(wifi_info: dict[str, Any]) -> int:
  """Get wifi STA frequency from the given wifi info."""
  # introduced for unrooted device.
  sta_frequency = wifi_info.get('StaFrequency', nc_constants.INVALID_INT)
  if sta_frequency == nc_constants.INVALID_INT:
    sta_frequency = wifi_info.get('mFrequency', nc_constants.INVALID_INT)
  return sta_frequency


def get_sta_max_link_speed_from_wifi_info(wifi_info: dict[str, Any]) -> int:
  """Get wifi STA max supported Tx link speed from the given wifi info."""
  # introduced for unrooted device.
  max_link_speed = wifi_info.get(
      'MaxSupportedTxLinkSpeedMbps', nc_constants.INVALID_INT
  )
  if max_link_speed == nc_constants.INVALID_INT:
    max_link_speed = wifi_info.get(
        'mMaxSupportedTxLinkSpeedMbps', nc_constants.INVALID_INT
    )
  return max_link_speed


def _get_wifi_sta_frequency_from_dumpsys(
    ad: android_device.AndroidDevice,
) -> int:
  """Get wifi STA frequency on the given device."""
  wifi_sta_status = dump_wifi_sta_status(ad)
  if not wifi_sta_status:
    return nc_constants.INVALID_INT
  prefix = 'Frequency:'
  postfix = 'MHz'
  return get_int_between_prefix_postfix(wifi_sta_status, prefix, postfix)


def get_wifi_p2p_frequency(ad: android_device.AndroidDevice) -> int:
  """Get wifi p2p frequency on the given device."""
  wifi_p2p_status = dump_wifi_p2p_status(ad)
  if not wifi_p2p_status:
    return nc_constants.INVALID_INT
  prefix = 'channelFrequency='
  postfix = ', groupRole=GroupOwner'
  return get_int_between_prefix_postfix(wifi_p2p_status, prefix, postfix)


def _get_wifi_sta_max_link_speed_from_dumpsys(
    ad: android_device.AndroidDevice,
) -> int:
  """Get wifi STA max supported Tx link speed on the given device."""
  wifi_sta_status = dump_wifi_sta_status(ad)
  if not wifi_sta_status:
    return nc_constants.INVALID_INT
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
      return nc_constants.INVALID_INT
  return nc_constants.INVALID_INT


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


def is_wifi_direct_supported(ad: android_device.AndroidDevice) -> bool:
  """Checks if WiFi Direct is supported on the given device."""
  try:
    return ad.nearby.wifiIsP2pSupported()
  except Exception as e:  # pylint: disable=broad-except
    ad.log.info('WiFi Direct is not supported due to %s', e)
    return False


def check_wifi_env(ad: android_device.AndroidDevice) -> None:
  """Let WI-FI scan and get scan results. Check if the environment is clean.

  Args:
    ad: AndroidDevice, Mobly Android Device.
  """
  # Initialize the number of SSIDs found in the wifi scan.
  ad.wifi_env_ssid_count = 0
  # Start wifi scan.
  try:
    ad.adb.shell('cmd wifi start-scan')
    time.sleep(WIFI_SCAN_WAIT_TIME_SEC)
  except adb.AdbError:
    ad.log.warning('Failed to start wifi scan.')
    return

  # List scanned result.
  try:
    wifi_scan_results = (
        ad.adb.shell('cmd wifi list-scan-results').decode('utf-8').strip()
    )
  except (adb.AdbError, ValueError):
    ad.log.warning('Failed to retrieve wifi scan results.')
    return

  # Subtract 1st line of results(header line) to get actual number of SSIDs.
  num_of_ssid = len(wifi_scan_results.splitlines()) - 1
  # Check the number of results against the threshold.
  if num_of_ssid > MAX_SSID_THRESHOLD:
    ad.log.warning(
        'Please clean up the Wi-Fi test environment: more than %d SSIDs found.',
        MAX_SSID_THRESHOLD,
    )
  else:
    ad.log.info('Wi-Fi test environment is clean.')

  # Update the number of SSIDs found in the wifi scan.
  ad.wifi_env_ssid_count = num_of_ssid
  return


def is_wifi_aware_available(ad: android_device.AndroidDevice) -> bool:
  """Checks if Aware is supported on the given device."""
  try:
    return ad.nearby.wifiAwareIsAvailable()
  except Exception as e:  # pylint: disable=broad-except
    ad.log.info('Aware is not supported due to %s', e)
    return False


def wait_for_aware_available(
    ad: android_device.AndroidDevice,
    timeout: datetime.timedelta = nc_constants.WIFI_AWARE_AVAILABLE_WAIT_TIME,
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
    return nc_constants.INVALID_RSSI
  except (adb.AdbError, ValueError):
    ad.log.warning('Failed to get wifi sta rssi')
    return nc_constants.INVALID_RSSI


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
  """Sets wifi tdls mode on the given device by using adb wl command.

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
  except adb.AdbError as e:
    if not catch_exception:
      raise
    ad.log.warning(f'Failed to set wifi tdls mode: {e}')
    return


def set_wifi_tdls_mode_by_wifi_manager_api(
    ad: android_device.AndroidDevice,
    remote_ad: android_device.AndroidDevice,
    enable_tdls: bool,
    catch_exception: bool = True,
) -> None:
  """Sets wifi tdls mode on the given device by using WifiManager API."""
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
  except (ValueError):
    if not catch_exception:
      raise
    remote_ad.log.warning('Failed to get IP address from remote device.')
    return

  # ad.log.info(f'Remote device IP address: {remote_ip_address}')
  ad.nearby.wifiSetTdlsEnable(remote_ip_address, enable_tdls)
  ad.log.info(f'Set wifi tdls mode to {enable_tdls}')


def set_flags(
    ad: android_device.AndroidDevice,
    output_path: str,
):
  """Sets default flags on the given device."""
  ad.log.info('Installing hermetic overrides from %s', _DEFAULT_OVERRIDES)
  _install_overrides(ad, output_path, _DEFAULT_OVERRIDES, False)


def set_flag_wifi_direct_hotspot_off(
    ad: android_device.AndroidDevice,
    output_path: str,
):
  """Turn off the flag use_wifi_direct_hotspot on the given device."""
  ad.log.info('turn off wifi direct hotspot')
  _install_overrides(
      ad,
      output_path,
      _WIFI_DIRECT_HOTSPOT_OFF_OVERRIDES,
      False,
  )


def _install_overrides(
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
) -> None:
  """Clear hermetic overrides.

  Args:
    ad: AndroidDevice, Mobly Android Device.
  """
  if not ad.is_adb_root:
    ad.log.info('Skipped clearing hermetic overrides on unrooted device.')
    return

  ad.adb.shell(
      'rm -f'
      ' /data/user_de/0/com.google.android.gms/app_phenotype_hermetic/overrides.txt'
  )
  ad.log.info('Clear hermetic flags override.')


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
  if sta_frequency == nc_constants.INVALID_INT:
    sta_frequency = _get_wifi_sta_frequency_from_dumpsys(ad)
    sta_max_link_speed_mbps = _get_wifi_sta_max_link_speed_from_dumpsys(ad)
  return (sta_frequency, sta_max_link_speed_mbps)


# Add back temporarily, will be removed after refractoring refactor DCT tests.
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
  if sta_frequency == nc_constants.INVALID_INT:
    sta_frequency = _get_wifi_sta_frequency_from_dumpsys(ad)
    sta_max_link_speed_mbps = _get_wifi_sta_max_link_speed_from_dumpsys(ad)
  return (sta_frequency, sta_max_link_speed_mbps)


def load_nearby_snippet(
    ad: android_device.AndroidDevice,
    config: nc_constants.SnippetConfig,
):
  """Loads a nearby snippet with the given snippet config."""
  device_specific_dict = get_betocq_device_specific_info(ad)

  if config.apk_path:
    key_apk_installed = config.package_name + '_installed'
    if not device_specific_dict.get(key_apk_installed, False):
      ad.log.info('try to install nearby_snippet_apk')
      apk_utils.install(ad, config.apk_path)
      device_specific_dict[key_apk_installed] = True
  else:
    ad.log.warning(
        'nearby_snippet apk is not specified, '
        'make sure it is installed in the device'
    )
  if not device_specific_dict.get('external_storage_permission_granted', False):
    ad.log.info('grant manage external storage permission')
    grant_manage_external_storage_permission(ad, config.package_name)
    device_specific_dict['external_storage_permission_granted'] = True

  ad.load_snippet(config.snippet_name, config.package_name)


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


def get_thermal_zone_data(ad: android_device.AndroidDevice) -> None:
  """Reads and logs temperature and type from /sys/class/thermal/thermal_zone*.

  Args:
    ad: AndroidDevice, Mobly Android Device.
  """
  if not ad.is_adb_root:
    ad.log.info('Skipped getting thermal zone data on unrooted device.')
    return
  thermal_data = []
  try:
    thermal_zones = (
        ad.adb.shell('ls /sys/class/thermal | grep thermal_zone')
        .decode('utf-8')
        .splitlines()
    )
  except adb.AdbError as e:
    ad.log.error(f'Failed to list thermal zones: {e}')
    return

  for zone_name in thermal_zones:
    zone_name = zone_name.strip()
    zone_path = f'/sys/class/thermal/{zone_name}'
    try:
      zone_type = ad.adb.shell(f'cat {zone_path}/type').decode('utf-8').strip()
      temp_str = ad.adb.shell(f'cat {zone_path}/temp').decode('utf-8').strip()
      try:
        temp = int(temp_str)
        if temp > 0:
          thermal_data.append((zone_type, temp_str))
        else:
          ad.log.debug(
              f'Ignoring thermal zone {zone_path} with temp {temp_str} <= 0'
          )
      except ValueError:
        ad.log.debug(
            f"Failed to parse temperature '{temp_str}' from {zone_path}"
        )
    except adb.AdbError as e:
      ad.log.debug(f'Failed to read thermal zone {zone_path}: {e}')
      continue
  ad.log.info(f'Thermal zone data: {thermal_data}')


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


def abort_if_2g_ap_not_ready(
    test_parameters: nc_constants.TestParameters,
) -> None:
  """Aborts test class if 2G AP is not ready."""
  if test_parameters.use_programmable_ap:
    return
  asserts.abort_class_if(
      not test_parameters.wifi_2g_ssid, '2G AP is not ready for this test.'
  )


def abort_if_5g_ap_not_ready(
    test_parameters: nc_constants.TestParameters,
) -> None:
  """Aborts test class if 5G AP is not ready."""
  if test_parameters.use_programmable_ap:
    return
  asserts.abort_class_if(
      not test_parameters.wifi_5g_ssid, '5G AP is not ready for this test.'
  )


def abort_if_dfs_5g_ap_not_ready(
    test_parameters: nc_constants.TestParameters,
) -> None:
  """Aborts test class if DFS 5G AP is not ready."""
  if test_parameters.use_programmable_ap:
    return
  asserts.abort_class_if(
      not test_parameters.wifi_dfs_5g_ssid,
      '5G DFS AP is not ready for this test.',
  )


def abort_if_any_5g_or_dfs_aps_not_ready(
    test_parameters: nc_constants.TestParameters,
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
  time.sleep(nc_constants.NEARBY_RESET_WAIT_TIME.total_seconds())


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
  ad.adb.shell(f'log -p {priority} -t {tag} "{message}"')
