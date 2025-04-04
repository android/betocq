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

import datetime
import time

from mobly.controllers import android_device
from mobly.controllers.android_device_lib import adb

from betocq.gms import hermetic_overrides_partner
from betocq import gms_auto_updates_util
from betocq import nc_constants
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


read_ph_flag_failed = False

NEARBY_LOG_TAGS = [
    'Nearby',
    'NearbyMessages',
    'NearbyDiscovery',
    'NearbyConnections',
    'NearbyMediums',
    'NearbySetup',
]


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
  if not ad.is_adb_root:
    ad.log.info(
        f'Skipped setting wifi country code on device "{ad.serial}" '
        'because we do not set country code on unrooted phone.'
    )
    return

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
  for tag in NEARBY_LOG_TAGS:
    ad.adb.shell(f'setprop log.tag.{tag} VERBOSE')

  # Enable WiFi verbose logging.
  ad.adb.shell('cmd wifi set-verbose-logging enabled')

  # Enable Bluetooth HCI logs.
  if not ad.is_adb_root:
    ad.log.info(
        'Skipped setting Bluetooth HCI logs on device,'
        'because we do not set Bluetooth HCI logs on unrooted phone.'
    )
    return
  ad.adb.shell('setprop persist.bluetooth.btsnooplogmode full')

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


def remove_disconnect_wifi_network(ad: android_device.AndroidDevice) -> None:
  """Removes and disconnects all wifi network on the given device."""
  if not ad.is_adb_root:
    ad.log.info("Can't clear wifi network in non-rooted device")
    return
  was_wifi_enabled = ad.nearby.wifiIsEnabled()
  if was_wifi_enabled:
    # wifiClearConfiguredNetworks() calls getConfiguredNetworks() and
    # removeNetworks() which could take a long time to complete because these
    # calls have the complicated ownership check and wifi thread could be busy
    # with other tasks. Wifi thread is optimized in V but not in old releases.
    # Therefore let's disable wifi so that these calls can be completed on time.
    ad.nearby.wifiDisable()
  ad.nearby.wifiClearConfiguredNetworks()
  if was_wifi_enabled:
    ad.nearby.wifiEnable()


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
  ad.log.info('Restart GMS.')
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


def get_wifi_sta_frequency(ad: android_device.AndroidDevice) -> int:
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


def get_wifi_sta_max_link_speed(ad: android_device.AndroidDevice) -> int:
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


def is_wifi_aware_available(ad: android_device.AndroidDevice) -> bool:
  """Checks if Aware is supported on the given device."""
  try:
    return ad.nearby.wifiAwareIsAvailable()
  except Exception as e:  # pylint: disable=broad-except
    ad.log.info('Aware is not supported due to %s', e)
    return False


def is_wifi_direct_supported(ad: android_device.AndroidDevice) -> bool:
  """Checks if WiFi Direct is supported on the given device."""
  try:
    return ad.nearby.wifiIsP2pSupported()
  except Exception as e:  # pylint: disable=broad-except
    ad.log.info('WiFi Direct is not supported due to %s', e)
    return False


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
  except adb.AdbError:
    return nc_constants.INVALID_RSSI


def _overrides_file_for_target(target: str) -> str:
  """Returns the resource path for the given target."""
  key = target.replace('//', 'google3/').replace(':', '/') + '_generated.txt'
  return resources.GetResourceFilename(key)


def _get_resource_contents(name: str) -> str:
  """Returns the contents of the given resource."""
  file_path = resources.GetResourceFilename(name)
  with open(file_path, 'r') as f:
    return f.read()


def set_flags(
    ad: android_device.AndroidDevice,
    output_path: str,
):
  """Sets flags on the given device."""
  ad.log.info('Installing hermetic overrides from %s', _DEFAULT_OVERRIDES)
  _install_overrides(ad, output_path, _DEFAULT_OVERRIDES, False)


def set_flag_wifi_direct_hotspot_off(
    ad: android_device.AndroidDevice,
    output_path: str,
):
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
