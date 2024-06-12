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

"""Utils for Android Wi-Fi operations."""

import dataclasses
import datetime
import enum
import re
import time

from mobly.controllers import android_device
from mobly.controllers.android_device_lib import adb

_DELAY_AFTER_CHANGE_WIFI_STATUS = datetime.timedelta(seconds=5)
_WAIT_FOR_CONNECTION = datetime.timedelta(seconds=30)

_SAVED_WIFI_LIST_PATTERN = re.compile(
    r'(?P<id>\d+)\s+(?P<ssid>.*)\s+(?P<security>.*)'
)
_SSID_PATTERN = re.compile(rb'Wifi is connected to "(?P<ssid>.*?)"')


@dataclasses.dataclass(frozen=True)
class SavedWifiInfo:
  """Information about a saved Wi-Fi network."""

  id: str
  ssid: str
  security: str


@enum.unique
class WiFiSecurity(enum.StrEnum):
  """Security type of the Wi-Fi network."""

  OPEN = 'open'
  OWE = 'owe'
  WPA2 = 'wpa2'
  WPA3 = 'wpa3'
  WEP = 'wep'


class AndroidWiFiError(Exception):
  """Error when failed to operate Wi-Fi on Android device."""

  def __init__(self, ad: android_device.AndroidDevice, message: str) -> None:
    self._ad = ad
    self._message = message

  def __str__(self) -> str:
    return self._message if self._ad is None else f'{self._ad} {self._message}'


def connect_to_wifi(
    ad: android_device.AndroidDevice,
    ssid: str,
    passphrase: str | None = None,
    security: WiFiSecurity | None = None,
) -> None:
  """Connects to a W-Fi network and adds to saved networks list."""
  enable_wifi(ad)
  if get_current_wifi(ad) == ssid:
    ad.log.info(f'Wi-Fi was already connected to {repr(ssid)}')
    return
  cmd = ['cmd', 'wifi', 'connect-network', f'"{ssid}"']
  if passphrase is None:
    cmd.append(f'"{security or WiFiSecurity.OPEN}"')
  else:
    cmd.extend([f'"{security or WiFiSecurity.WPA2}"', f'"{passphrase}"'])
  ad.adb.shell(cmd)
  if not _wait_for_data_connected(ad) or get_current_wifi(ad) != ssid:
    raise AndroidWiFiError(ad, f'Fail to connect to Wi-Fi {repr(ssid)}')
  ad.log.info(f'Wi-Fi connected to {repr(ssid)}')


def disable_wifi(ad: android_device.AndroidDevice) -> None:
  """Disables Wi-Fi."""
  if not is_wifi_enabled(ad):
    ad.log.info('Wi-Fi was already disabled.')
    return
  ad.log.info('Disabling Wi-Fi...')
  ad.adb.shell(['cmd', 'wifi', 'set-wifi-enabled', 'disabled'])
  start_time = time.monotonic()
  timeout = start_time + _DELAY_AFTER_CHANGE_WIFI_STATUS.total_seconds()
  while time.monotonic() < timeout:
    if not is_wifi_enabled(ad):
      ad.log.info('Wi-Fi is disabled.')
      return
  raise AndroidWiFiError(
      ad,
      'Fail to disable Wi-Fi after waiting for'
      f' {_DELAY_AFTER_CHANGE_WIFI_STATUS.total_seconds()} seconds',
  )


def enable_wifi(ad: android_device.AndroidDevice) -> None:
  """Enables Wi-Fi."""
  if is_wifi_enabled(ad):
    ad.log.info('Wi-Fi was already enabled.')
    return
  ad.log.info('Enabling Wi-Fi...')
  ad.adb.shell(['cmd', 'wifi', 'set-wifi-enabled', 'enabled'])
  start_time = time.monotonic()
  timeout = start_time + _DELAY_AFTER_CHANGE_WIFI_STATUS.total_seconds()
  while time.monotonic() < timeout:
    if is_wifi_enabled(ad):
      ad.log.info('Wi-Fi is enabled.')
      return
  raise AndroidWiFiError(
      ad,
      'Fail to enable Wi-Fi after waiting for'
      f' {_DELAY_AFTER_CHANGE_WIFI_STATUS.total_seconds()} seconds',
  )


def forget_all_wifi(ad: android_device.AndroidDevice) -> None:
  """Forgets all Wi-Fi from saved networks list."""
  for saved_wifi in list_saved_wifi(ad):
    ad.adb.shell(['cmd', 'wifi', 'forget-network', saved_wifi.id])
  saved_wifis = list_saved_wifi(ad)
  if saved_wifis:
    raise AndroidWiFiError(
        ad,
        'Fail to forget all Wi-Fi networks, remaining in the list:'
        f' {saved_wifis}',
    )


def forget_wifi(ad: android_device.AndroidDevice, ssid: str) -> None:
  """Forgets Wi-Fi from saved networks list."""
  saved_wifis = list_saved_wifi(ad)
  for saved_wifi in saved_wifis:
    if saved_wifi.ssid == ssid:
      stdout = ad.adb.shell(['cmd', 'wifi', 'forget-network', saved_wifi.id])
      if stdout == b'Forget successful\n':
        ad.log.info(f'Wi-Fi {repr(ssid)} was forgotten from saved networks.')
        return
      raise AndroidWiFiError(ad, f'Fail to forget Wi-Fi {repr(ssid)}')
  ad.log.info(f'Nothing was deleted since Wi-Fi {repr(ssid)} was not saved')
  return


def get_current_wifi(ad: android_device.AndroidDevice) -> str:
  """Returns current Wi-Fi network."""
  if match := _SSID_PATTERN.search(ad.adb.shell(['cmd', 'wifi', 'status'])):
    return match.group('ssid').decode()
  return ''


def is_wifi_enabled(ad: android_device.AndroidDevice) -> bool:
  """Returns True if Wi-Fi is enabled, False otherwise."""
  return ad.adb.shell(['cmd', 'wifi', 'status']).startswith(b'Wifi is enabled')


def list_saved_wifi(ad: android_device.AndroidDevice) -> list[SavedWifiInfo]:
  """Returns list of saved Wi-Fi networks."""
  saved_wifis = []
  stdout = ad.adb.shell(['cmd', 'wifi', 'list-networks']).decode()
  if stdout == 'No networks\n':
    return saved_wifis
  for line in stdout.splitlines()[1:]:
    if match := _SAVED_WIFI_LIST_PATTERN.search(line):
      saved_wifis.append(
          SavedWifiInfo(
              id=match.group('id'),
              ssid=match.group('ssid').strip(),
              security=match.group('security'),
          )
      )
  return saved_wifis


def _is_data_connected(ad: android_device.AndroidDevice) -> bool:
  """Returns True if data is connected, False otherwise."""
  try:
    return b'5 received' in ad.adb.shell(['ping', '-c', '5', '8.8.8.8'])
  except adb.AdbError:
    return False


def _wait_for_data_connected(
    ad: android_device.AndroidDevice,
    timeout: datetime.timedelta = _WAIT_FOR_CONNECTION,
) -> bool:
  """Returns True if data is connected before timeout, False otherwise."""
  start_time = time.monotonic()
  timeout = start_time + timeout.total_seconds()
  while time.monotonic() < timeout:
    if _is_data_connected(ad):
      return True
  return False
