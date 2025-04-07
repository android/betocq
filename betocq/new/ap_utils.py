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

"""Utilitiess related to control the WiFi environment."""

from mobly.controllers.wifi import local_sniffer_device
from mobly.controllers.wifi import openwrt_device
from mobly.controllers.wifi.lib import wifi_configs

from betocq.new import nc_constants


def start_wifi(
    ap: openwrt_device.OpenWrtDevice,
    wifi_channel: int,
    country_code: str,
    test_parameters: nc_constants.TestParameters,
):
  """Starts a WiFi network and sets SSID and password to the test parameters.

  Args:
    ap: The programmable AP device to start the WiFi network.
    wifi_channel: The WiFi channel to start the network on.
    country_code: The country code to set the AP to.
    test_parameters: The test parameter object to set the SSID and password to.
  """
  ap_config = wifi_configs.WiFiConfig(
      channel=wifi_channel,
      country_code=country_code,
  )

  ap.log.debug('Starting a WiFi network with config: %s', ap_config)
  started_wifi_info = ap.start_wifi(config=ap_config)
  ssid = started_wifi_info.ssid
  password = started_wifi_info.password

  ap.log.debug(
      'Started WiFi network with ssid "%s" password "%s"', ssid, password
  )

  if wifi_channel == nc_constants.CHANNEL_2G:
    test_parameters.wifi_2g_ssid = ssid
    test_parameters.wifi_2g_password = password
  elif wifi_channel == nc_constants.CHANNEL_5G:
    test_parameters.wifi_5g_ssid = ssid
    test_parameters.wifi_5g_password = password
  elif wifi_channel == nc_constants.CHANNEL_5G_DFS:
    test_parameters.wifi_dfs_5g_ssid = ssid
    test_parameters.wifi_dfs_5g_password = password
  else:
    raise ValueError(f'Unknown WiFi channel: {wifi_channel}')
