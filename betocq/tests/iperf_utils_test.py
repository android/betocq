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

"""Unittest for iperf_utils."""

import unittest
from unittest import mock

from betocq import iperf_utils


class IPerfServerOnDeviceTest(unittest.TestCase):
  """Class that handles iperf3 server operations on device."""

  def test_get_ifconfig_aware_pixel(self):
    """Test get_ifconfig_aware function for pixel devices.

    This test mocks the adb shell command function to return a sample
    ifconfig output from the pixel devices and asserts that the parsed ifconfig
    object matches the expected value.
    """
    mock_android_device_pixel = mock.Mock()

    mock_android_device_pixel.adb.shell.return_value = (
        b"'aware_nmi0','Link encap:Ethernet','HWaddr 2a:eb:2a:db:0c:cd','inet6"
        b" addr: fe80::68a1:5aff:fe87:421a/64 Scope: Link','UP BROADCAST"
        b" RUNNING MULTICAST  MTU:1500  Metric:1','RX packets:0 errors:0"
        b" dropped:0 overruns:0 frame:0','TX packets:0 errors:0 dropped:0"
        b" overruns:0 carrier:0','collisions:0 txqueuelen:1000','RX bytes:0 TX"
        b" bytes:0','aware_data0','Link encap:Ethernet','HWaddr"
        b" 46:0d:f7:cf:b6:e3','inet6 addr: fe80::440d:f7ff:fecf:b6e3/64 Scope:"
        b" Link','UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1','RX"
        b" packets:50667 errors:0 dropped:0 overruns:0 frame:0','TX"
        b" packets:2199 errors:0 dropped:0 overruns:0 carrier:0','collisions:0"
        b" txqueuelen:1000','RX bytes:75937716 TX bytes:189170'"
    )

    expected_ifconfig_pixel = (
        "'aware_nmi0','Link encap:Ethernet','HWaddr 2a:eb:2a:db:0c:cd','inet6 "
        "addr: fe80::68a1:5aff:fe87:421a/64 Scope: Link','UP BROADCAST RUNNING "
        "MULTICAST  MTU:1500  Metric:1','RX packets:0 errors:0 dropped:0 "
        "overruns:0 frame:0','TX packets:0 errors:0 dropped:0 overruns:0 "
        "carrier:0','collisions:0 txqueuelen:1000','RX bytes:0 TX bytes:0',"
        "'aware_data0','Link encap:Ethernet','HWaddr 46:0d:f7:cf:b6:e3',"
        "'inet6 addr: fe80::440d:f7ff:fecf:b6e3/64 Scope: Link','UP BROADCAST "
        "RUNNING MULTICAST  MTU:1500  Metric:1','RX packets:50667 errors:0 "
        "dropped:0 overruns:0 frame:0','TX packets:2199 errors:0 dropped:0 "
        "overruns:0 carrier:0','collisions:0 txqueuelen:1000','RX "
        "bytes:75937716 TX bytes:189170'"
    )

    if_config_pixel = iperf_utils.get_ifconfig_aware(mock_android_device_pixel)
    self.assertEqual(if_config_pixel, expected_ifconfig_pixel)

  def test_get_ifconfig_aware_non_pixel(self):
    """Test get_ifconfig_aware function for non pixel devices.

    This test mocks the adb shell command function to return a sample
    ifconfig output from the non pixel devices and asserts that the parsed
    ifconfig object matches the expected value.
    """
    mock_android_device_non_pixel = mock.Mock()

    mock_android_device_non_pixel.adb.shell.return_value = (
        b"'wifi-aware0','Link encap:Ethernet','HWaddr"
        b" f2:cd:31:81:08:54','Driver cnss_pci','UP BROADCAST MULTICAST "
        b" MTU:1500  Metric:1','RX packets:0 errors:0 dropped:0 overruns:0"
        b" frame:0','TX packets:0 errors:0 dropped:0 overruns:0"
        b" carrier:0','collisions:0 txqueuelen:3000','RX bytes:0 TX"
        b" bytes:0','aware_data0','Link encap:Ethernet','HWaddr"
        b" 02:2c:55:bd:73:ca','Driver cnss_pci','inet6 addr:"
        b" fe80::2c:55ff:febd:73ca/64 Scope: Link','UP BROADCAST RUNNING"
        b" MULTICAST  MTU:1500  Metric:1','RX packets:276314 errors:0 dropped:0"
        b" overruns:0 frame:0','TX packets:12846 errors:0 dropped:0 overruns:0"
        b" carrier:0','collisions:0 txqueuelen:3000','RX bytes:414058408 TX"
        b" bytes:1104992'"
    )

    expected_ifconfig_non_pixel = (
        "'wifi-aware0','Link encap:Ethernet','HWaddr f2:cd:31:81:08:54','Driver"
        " cnss_pci','UP BROADCAST MULTICAST  MTU:1500  Metric:1','RX"
        " packets:0 errors:0 dropped:0 overruns:0 frame:0','TX packets:0"
        " errors:0 dropped:0 overruns:0 carrier:0','collisions:0"
        " txqueuelen:3000','RX bytes:0 TX bytes:0','aware_data0','Link"
        " encap:Ethernet','HWaddr 02:2c:55:bd:73:ca','Driver cnss_pci','inet6"
        " addr: fe80::2c:55ff:febd:73ca/64 Scope: Link','UP BROADCAST RUNNING"
        " MULTICAST  MTU:1500  Metric:1','RX packets:276314 errors:0 dropped:0"
        " overruns:0 frame:0','TX packets:12846 errors:0 dropped:0 overruns:0"
        " carrier:0','collisions:0 txqueuelen:3000','RX bytes:414058408 TX"
        " bytes:1104992'"
    )

    if_config_non_pixel = iperf_utils.get_ifconfig_aware(
        mock_android_device_non_pixel
    )
    self.assertEqual(if_config_non_pixel, expected_ifconfig_non_pixel)

  def test_get_ifconfig_wlan_pixel(self):
    """Test get_ifconfig_wlan function for pixel devices.

    This test mocks the adb shell command function to return a sample
    ifconfig output from the pixel devices and asserts that the parsed
    ifconfig object matches the expected value.
    """
    mock_android_device_pixel = mock.Mock()
    mock_android_device_pixel.adb.shell.return_value = (
        b"'wlan0','Link encap:Ethernet','HWaddr b2:33:73:81:ef:3e'"
        b"'inet addr:192.168.1.205  Bcast:192.168.1.255  Mask:255.255.255.0'"
        b"'inet6 addr: fe80::b033:73ff:fe81:ef3e/64 Scope: Link'"
        b"'UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1'"
        b"'RX packets:178287 errors:0 dropped:7 overruns:0 frame:0'"
        b"'TX packets:206010 errors:0 dropped:38 overruns:0 carrier:0'"
        b"'collisions:0 txqueuelen:1000'"
        b"'RX bytes:117125843 TX bytes:173695970'"
    )
    expected_ifconfig_wlan_pixel = (
        "'wlan0','Link encap:Ethernet','HWaddr b2:33:73:81:ef:3e'"
        "'inet addr:192.168.1.205  Bcast:192.168.1.255  Mask:255.255.255.0'"
        "'inet6 addr: fe80::b033:73ff:fe81:ef3e/64 Scope: Link'"
        "'UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1'"
        "'RX packets:178287 errors:0 dropped:7 overruns:0 frame:0'"
        "'TX packets:206010 errors:0 dropped:38 overruns:0 carrier:0'"
        "'collisions:0 txqueuelen:1000'"
        "'RX bytes:117125843 TX bytes:173695970'"
    )

    if_config_wlan_pixel = iperf_utils.get_ifconfig_wlan(
        mock_android_device_pixel
    )

    self.assertEqual(if_config_wlan_pixel, expected_ifconfig_wlan_pixel)

  def test_get_ifconfig_wlan_non_pixel(self):
    """Test get_ifconfig_wlan function for non pixel devices.

    This test mocks the adb shell command function to return a sample
    ifconfig output from the non pixel devices and asserts that the parsed
    ifconfig object matches the expected value.
    """
    mock_android_device_non_pixel = mock.Mock()
    mock_android_device_non_pixel.adb.shell.return_value = (
        b"'wlan0','Link encap:Ethernet','HWaddr 62:5a:c2:b1:8c:0f','Driver "
        b"cnss_pci','inet addr:192.168.1.132  Bcast:192.168.1.255"
        b"Mask:255.255.255.0','inet6 addr: fe80::605a:c2ff:feb1:8c0f/64 Scope:"
        b"Link','UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1'"
        b"'RX packets:20635830 errors:0 dropped:56500 overruns:0 frame:0'"
        b"'TX packets:1130354 errors:0 dropped:69 overruns:0 carrier:0'"
        b"'collisions:0 txqueuelen:3000'"
        b"'RX bytes:5530145535 TX bytes:238809451'"
    )
    expected_ifconfig_wlan_non_pixel = (
        "'wlan0','Link encap:Ethernet','HWaddr 62:5a:c2:b1:8c:0f','Driver "
        "cnss_pci','inet addr:192.168.1.132  Bcast:192.168.1.255"
        "Mask:255.255.255.0','inet6 addr: fe80::605a:c2ff:feb1:8c0f/64 Scope:"
        "Link','UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1'"
        "'RX packets:20635830 errors:0 dropped:56500 overruns:0 frame:0'"
        "'TX packets:1130354 errors:0 dropped:69 overruns:0 carrier:0'"
        "'collisions:0 txqueuelen:3000'"
        "'RX bytes:5530145535 TX bytes:238809451'"
    )

    if_config_wlan_non_pixel = iperf_utils.get_ifconfig_wlan(
        mock_android_device_non_pixel
    )

    self.assertEqual(if_config_wlan_non_pixel, expected_ifconfig_wlan_non_pixel)

  def test_get_ifconfig_p2p_pixel(self):
    """Test get_ifconfig_p2p function for pixel devices.

    This test mocks the adb shell command function to return a sample
    ifconfig output from the pixel devices and asserts that the parsed
    ifconfig object matches the expected value.
    """
    mock_android_device_pixel = mock.Mock()
    mock_android_device_pixel.adb.shell.return_value = (
        b"'p2p-wlan0-0','Link encap:Ethernet','HWaddr fa:1f:be:e5:8e:6a'"
        b"'inet6 addr: fe80::f81f:beff:fee5:8e6a/64 Scope: Link'"
        b"'UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1'"
        b"'RX packets:23757 errors:0 dropped:0 overruns:0 frame:0'"
        b"'TX packets:572413 errors:0 dropped:16 overruns:0 carrier:0'"
        b"'collisions:0 txqueuelen:1000'"
        b"'RX bytes:1710836 TX bytes:866080745'"
    )
    expected_ifconfig_p2p_pixel = (
        "'p2p-wlan0-0','Link encap:Ethernet','HWaddr fa:1f:be:e5:8e:6a'"
        "'inet6 addr: fe80::f81f:beff:fee5:8e6a/64 Scope: Link'"
        "'UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1'"
        "'RX packets:23757 errors:0 dropped:0 overruns:0 frame:0'"
        "'TX packets:572413 errors:0 dropped:16 overruns:0 carrier:0'"
        "'collisions:0 txqueuelen:1000'"
        "'RX bytes:1710836 TX bytes:866080745'"
    )

    if_config_p2p_pixel = iperf_utils.get_ifconfig_p2p(
        mock_android_device_pixel
    )

    self.assertEqual(if_config_p2p_pixel, expected_ifconfig_p2p_pixel)

  def test_get_ifconfig_p2p_non_pixel(self):
    """Test get_ifconfig_p2p function for non pixel devices.

    This test mocks the adb shell command function to return a sample
    ifconfig output from the non pixel devices and asserts that the parsed
    ifconfig object matches the expected value.
    """
    mock_android_device_non_pixel = mock.Mock()
    mock_android_device_non_pixel.adb.shell.return_value = (
        b"'p2p-wlan0-0','Link encap:Ethernet','HWaddr"
        b" f2:cd:31:fa:88:54','Drivercnss_pci','inet addr:192.168.49.1 "
        b" Bcast:192.168.49.255  Mask:255.255.255.0','inet6 addr:"
        b" fdc2:4a33:e9c::e(internal) Scope: Global','inet6 addr:"
        b" fe80::f0cd:31ff:fefa:8854/64 Scope: Link','UP BROADCAST RUNNING"
        b" MULTICAST  MTU:1500  Metric:1','RX packets:58075 errors:0 dropped:0"
        b" overruns:0 frame:0','TX packets:2880 errors:0 dropped:0 overruns:0"
        b" carrier:0','collisions:0 txqueuelen:3000','RX bytes:87826360 TX"
        b" bytes:193840'"
    )
    expected_ifconfig_p2p_non_pixel = (
        "'p2p-wlan0-0','Link encap:Ethernet','HWaddr"
        " f2:cd:31:fa:88:54','Drivercnss_pci','inet addr:192.168.49.1 "
        " Bcast:192.168.49.255  Mask:255.255.255.0','inet6 addr:"
        " fdc2:4a33:e9c::e(internal) Scope: Global','inet6 addr:"
        " fe80::f0cd:31ff:fefa:8854/64 Scope: Link','UP BROADCAST RUNNING"
        " MULTICAST  MTU:1500  Metric:1','RX packets:58075 errors:0 dropped:0"
        " overruns:0 frame:0','TX packets:2880 errors:0 dropped:0 overruns:0"
        " carrier:0','collisions:0 txqueuelen:3000','RX bytes:87826360 TX"
        " bytes:193840'"
    )

    if_config_p2p_non_pixel = iperf_utils.get_ifconfig_p2p(
        mock_android_device_non_pixel
    )

    self.assertEqual(if_config_p2p_non_pixel, expected_ifconfig_p2p_non_pixel)

  def test_get_group_owner_ipv4_addr(self):
    """Test get_group_owner_addr function which returns ipv4 address."""
    mock_android_device = mock.Mock()
    mock_android_device.adb.shell.return_value = b" inet addr: 192.168.49.1"
    expected_group_owner_ipv4_addr = "192.168.49.1"

    group_owner_ipv4_addr = iperf_utils.get_group_owner_addr(
        mock_android_device
    )

    self.assertEqual(group_owner_ipv4_addr, expected_group_owner_ipv4_addr)

  def test_get_group_owner_ipv6_addr(self):
    """Test get_group_owner_addr function which returns ipv6 address with link interface."""
    mock_android_device = mock.Mock()
    mock_android_device.adb.shell.return_value = (
        b" inet6 addr: fe80::8cf5:c5ff:feae:2121/64-p2p-wlan0-0"
    )
    expected_group_owner_ipv6_addr = "fe80::8cf5:c5ff:feae:212164-p2p-wlan0-0"

    group_owner_ipv6_addr = iperf_utils.get_group_owner_addr(
        mock_android_device
    )

    self.assertEqual(group_owner_ipv6_addr, expected_group_owner_ipv6_addr)


if __name__ == "__main__":
  unittest.main()
