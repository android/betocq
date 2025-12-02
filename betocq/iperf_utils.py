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

"""Utilities for running iperf on the devices."""


import logging
import time
from mobly import utils
from mobly.controllers import android_device
from betocq import nc_constants
from betocq import setup_utils

# IPv4, 10 sec, 1 stream
DEFAULT_IPV4_CLIENT_ARGS = '-t 10 -P1'
DEFAULT_IPV4_SERVER_ARGS = '-J'
GROUP_OWNER_IPV4_ADDR_LEN_MAX = 15
IPERF_SERVER_START_DELAY_SEC = 1
IPERF_DEBUG_TIME_SEC = 300


class IPerfServerOnDevice:
  """Class that handles iperf3 server operations on device."""

  def __init__(self, serial, arg=DEFAULT_IPV4_SERVER_ARGS):
    self.iperf_str = 'adb -s {serial} shell iperf3 -s {arg}'.format(
        serial=serial, arg=arg
    )
    self.iperf_process = None
    self.started = False

  def start(self):
    """Starts iperf server on specified port."""
    if self.started:
      return

    cmd = self.iperf_str
    self.iperf_process = utils.start_standing_subprocess(cmd, shell=True)
    self.started = True

  def stop(self):
    if self.started:
      utils.stop_standing_subprocess(self.iperf_process)
      self.started = False


def run_iperf_test(
    ad_network_client: android_device.AndroidDevice,
    ad_network_owner: android_device.AndroidDevice,
    medium: nc_constants.NearbyConnectionMedium,
) -> int:
  """Run iperf test from ad_network_client to ad_network_owner.

  Args:
    ad_network_client: android device that is the client in the iperf test.
    ad_network_owner: android device that is the server in the iperf test.
    medium: wifi medium used in the transfer

  Returns:
    speed in KB/s if there is a valid result or nc_constants.INVALID_INT.
  """
  speed_kbyte_sec = nc_constants.INVALID_INT
  try:
    owner_addr = get_owner_ip_addr(ad_network_client, ad_network_owner, medium)
    if not owner_addr:
      return nc_constants.INVALID_INT
  except android_device.adb.Error:
    ad_network_client.log.info('get_owner_ip_addr() failed')
    owner_ifconfig = get_ifconfig(ad_network_owner)
    ad_network_owner.log.info(owner_ifconfig)
    return nc_constants.INVALID_INT

  client_arg = DEFAULT_IPV4_CLIENT_ARGS
  server_arg = DEFAULT_IPV4_SERVER_ARGS
  # Add IPv6 option if the owner address is an IPv6 address
  if len(owner_addr) > GROUP_OWNER_IPV4_ADDR_LEN_MAX:
    client_arg = DEFAULT_IPV4_CLIENT_ARGS + ' -6'
    server_arg = DEFAULT_IPV4_SERVER_ARGS + ' -6'

  server = IPerfServerOnDevice(ad_network_owner.serial, server_arg)
  try:
    ad_network_owner.log.info('Start iperf server')
    server.start()
    time.sleep(IPERF_SERVER_START_DELAY_SEC)
    ad_network_client.log.info(f'Start iperf client {owner_addr}')
    success, result_list = ad_network_client.run_iperf_client(
        owner_addr, client_arg
    )
    result = ''.join(result_list)
    last_mbits_sec_index = result.rfind('Mbits/sec')
    if success and last_mbits_sec_index > 0:
      speed_mbps = int(
          float(result[:last_mbits_sec_index].strip().split(' ')[-1])
      )
      speed_kbyte_sec = int(speed_mbps * 1024 / 8)
    else:
      ad_network_client.log.info('Can not find valid iperf test result')
  except android_device.adb.AdbError:
    ad_network_client.log.info('run_iperf_client() failed')
    owner_ifconfig = get_ifconfig(ad_network_owner)
    client_ifconfig = get_ifconfig(ad_network_client)
    ad_network_client.log.info(client_ifconfig)
    ad_network_client.log.info(owner_addr)
    ad_network_client.log.info(client_arg)
    ad_network_owner.log.info(owner_ifconfig)
    # time.sleep(IPERF_DEBUG_TIME_SEC)
  else:
    server.stop()
  return speed_kbyte_sec


def get_owner_ip_addr(
    ad_network_client: android_device.AndroidDevice,
    ad_network_owner: android_device.AndroidDevice,
    medium: nc_constants.NearbyConnectionMedium,
) -> str:
  """Get owner ip address.

  For IPv6, the address is postfixed by the client interface name.

  Args:
    ad_network_client: The AndroidDevice acting as the client.
    ad_network_owner: The AndroidDevice acting as the group owner/server.
    medium: The NearbyConnectionMedium being used.

  Returns:
    The IP address of the owner device.
  """
  ip_addr = ''
  if medium == nc_constants.NearbyConnectionMedium.WIFI_DIRECT:
    ip_addr = get_group_owner_addr(ad_network_client)
  elif medium == nc_constants.NearbyConnectionMedium.WIFI_LAN:
    ip_addr = get_wlan_ip_addr(ad_network_owner)
    if len(ip_addr) > GROUP_OWNER_IPV4_ADDR_LEN_MAX:
      ip_addr = f'{ip_addr}%{get_wlan_ifname(ad_network_client)}'
  elif medium == nc_constants.NearbyConnectionMedium.WIFI_HOTSPOT:
    try:
      ip_addr = get_p2p_ip_addr(ad_network_owner)
    except android_device.adb.Error:
      ad_network_owner.log.info(
          'Failed to get p2p ip address, try to get wlan ip address.'
      )
      ip_addr = get_wlan_ip_addr(ad_network_owner)
    if len(ip_addr) > GROUP_OWNER_IPV4_ADDR_LEN_MAX:
      ip_addr = f'{ip_addr}%{get_wlan_ifname(ad_network_client)}'
  elif medium == nc_constants.NearbyConnectionMedium.WIFI_AWARE:
    ip_addr = get_aware_ip_addr(ad_network_owner)
    if len(ip_addr) > GROUP_OWNER_IPV4_ADDR_LEN_MAX:
      ip_addr = f'{ip_addr}%{get_aware_ifname(ad_network_client)}'
  return ip_addr


def get_aware_ip_addr(ad: android_device.AndroidDevice) -> str:
  """Get wlan ip address from ifconfig."""
  ifconfig = get_ifconfig_aware(ad)
  return extract_ip_addr_from_ifconfig(ifconfig)


def get_wlan_ip_addr(ad: android_device.AndroidDevice) -> str:
  """Get wlan ip address from ifconfig."""
  ifconfig = get_ifconfig_wlan(ad)
  return extract_ip_addr_from_ifconfig(ifconfig)


def get_p2p_ip_addr(ad: android_device.AndroidDevice) -> str:
  """Get p2p ip address from ifconfig."""
  ifconfig = get_ifconfig_p2p(ad)
  return extract_ip_addr_from_ifconfig(ifconfig)


def get_aware_ifname(ad: android_device.AndroidDevice) -> str:
  """Get Aware interface name from ifconfig."""
  return get_ifconfig_aware(ad).split()[0].strip()


def get_wlan_ifname(ad: android_device.AndroidDevice) -> str:
  """Get WLAN interface name from ifconfig."""
  ifconfig = get_ifconfig_wlan(ad)
  found_wlan1 = ifconfig.rfind('wlan1')
  if found_wlan1 >= 0:
    return 'wlan1'
  found_wlan0 = ifconfig.rfind('wlan0')
  if found_wlan0 >= 0:
    return 'wlan0'
  return ''


def get_p2p_ifname(ad: android_device.AndroidDevice) -> str:
  """Get P2P interface name from ifconfig."""
  return  get_ifconfig_p2p(ad).split()[0].strip()


def extract_ip_addr_from_ifconfig(ifconfig: str) -> str:
  """Extract ip address from ifconfig with IPv6 preferred."""
  ipv6 = get_substr_between_prefix_postfix(
      ifconfig, 'inet6 addr:', '/64 Scope: Link'
  )
  if ipv6:
    return ipv6
  ipv4 = get_substr_between_prefix_postfix(ifconfig, 'inet addr:', 'Bcast')
  if ipv4:
    return ipv4
  return ''


def get_substr_between_prefix_postfix(
    string: str, prefix: str, postfix: str
) -> str:
  """Get substring between prefix and postfix by searching postfix and then prefix."""
  right_index = string.rfind(postfix)
  if right_index == -1:
    return ''
  left_index = string[:right_index].rfind(prefix)
  if left_index > 0:
    try:
      return string[left_index + len(prefix): right_index].strip()
    except IndexError:
      return ''
  return ''


def get_ifconfig(
    ad: android_device.AndroidDevice,
) -> str:
  """Get network info from adb shell ifconfig."""
  return ad.adb.shell('ifconfig').decode('utf-8').strip()


def get_ifconfig_aware(
    ad: android_device.AndroidDevice,
) -> str:
  """Get aware network info from adb shell ifconfig."""
  logging.info(ad)
  ifconfig = ad.adb.shell('ifconfig | grep aware').decode('utf-8')

  iface_list = ifconfig.split()

  for iface in iface_list:
    str_list = iface.strip().split()
    if not str_list:
      continue
    if_name = str_list[0].strip()
    info = ad.adb.shell(f'ifconfig | grep -A7 {if_name}').decode('utf-8')

    prefix = 'Tx packets'
    postfix = 'errors'
    tx_packets = setup_utils.get_int_between_prefix_postfix(
        info, prefix, postfix
    )
    if tx_packets > 0:
      return info

  return (ifconfig)


def get_ifconfig_wlan(
    ad: android_device.AndroidDevice,
) -> str:
  """Get wlan network info from adb shell ifconfig."""
  return ad.adb.shell('ifconfig | grep -A6 wlan').decode('utf-8').strip()


def get_ifconfig_p2p(
    ad: android_device.AndroidDevice,
) -> str:
  """Get p2p network info from adb shell ifconfig."""
  return ad.adb.shell('ifconfig | grep -A5 p2p').decode('utf-8').strip()


def get_group_owner_addr(
    ad: android_device.AndroidDevice,
) -> str:
  """Get the group owner address from adb shell dumpsys wifip2p.

  This works only if group owner address is the last substring of the line.

  Args:
    ad: android device that is the group client
  Returns:
    ipv4 address or ipv6 address with the link interface
  """

  try:
    return (
        ad.adb.shell(
            'dumpsys wifip2p | egrep "groupOwnerAddress|groupOwnerIpAddress"'
        )
        .decode('utf-8')
        .strip()
        .split()[-1]
        .replace('/', '')
    )
  except android_device.adb.Error:
    ad.log.info('Failed to get group owner address.')
    return ''
