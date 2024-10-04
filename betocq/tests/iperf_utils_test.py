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
    """Test get_ifconfig_aware function.

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
    """Test get_ifconfig_aware function.

    This test mocks the adb shell command function to return a sample
    ifconfig output from the no pixel devices and asserts that the parsed
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


if __name__ == "__main__":
  unittest.main()
