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

"""Constants for Nearby Connection."""

import ast
import dataclasses
import datetime
import enum
import logging
from typing import Any

BETOCQ_SUITE_NAME = 'BeToCQ'

SUCCESS_RATE_TARGET = 0.98
BLE_PERFORMANCE_TEST_SUCCESS_RATE_TARGET = 0.98
MCC_PERFORMANCE_TEST_COUNT = 100
MCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR = 5
SCC_PERFORMANCE_TEST_COUNT = 10
SCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR = 2
BT_PERFORMANCE_TEST_COUNT = 100
BT_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR = 5
BT_COEX_PERFORMANCE_TEST_COUNT = 100
BT_COEX_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR = 5
TARGET_POST_WIFI_CONNECTION_IDLE_TIME_SEC = 10

CHANNEL_2G = 6
CHANNEL_5G = 36
CHANNEL_5G_DFS = 52

NEARBY_RESET_WAIT_TIME = datetime.timedelta(seconds=2)
WIFI_DISCONNECTION_DELAY = datetime.timedelta(seconds=1)

FIRST_DISCOVERY_TIMEOUT = datetime.timedelta(seconds=30)
FIRST_CONNECTION_INIT_TIMEOUT = datetime.timedelta(seconds=30)
FIRST_CONNECTION_RESULT_TIMEOUT = datetime.timedelta(seconds=35)
BT_1K_PAYLOAD_TRANSFER_TIMEOUT = datetime.timedelta(seconds=20)
BT_500K_PAYLOAD_TRANSFER_TIMEOUT = datetime.timedelta(seconds=25)
BLE_20K_PAYLOAD_TRANSFER_TIMEOUT = datetime.timedelta(seconds=25)
SECOND_DISCOVERY_TIMEOUT = datetime.timedelta(seconds=35)
SECOND_CONNECTION_INIT_TIMEOUT = datetime.timedelta(seconds=10)
SECOND_CONNECTION_RESULT_TIMEOUT = datetime.timedelta(seconds=25)
CONNECTION_BANDWIDTH_CHANGED_TIMEOUT = datetime.timedelta(seconds=25)
WIFI_1K_PAYLOAD_TRANSFER_TIMEOUT = datetime.timedelta(seconds=20)
WIFI_2G_20M_PAYLOAD_TRANSFER_TIMEOUT = datetime.timedelta(seconds=20)
WIFI_200M_PAYLOAD_TRANSFER_TIMEOUT = datetime.timedelta(seconds=100)
WIFI_500M_PAYLOAD_TRANSFER_TIMEOUT = datetime.timedelta(seconds=250)
WIFI_STA_CONNECTING_TIME_OUT = datetime.timedelta(seconds=25)
DISCONNECTION_TIMEOUT = datetime.timedelta(seconds=15)

MAX_PHY_RATE_PER_STREAM_AC_80_MBPS = 433
MAX_PHY_RATE_PER_STREAM_AC_40_MBPS = 200
MAX_PHY_RATE_PER_STREAM_N_20_MBPS = 72

MCC_THROUGHPUT_MULTIPLIER = 0.25
MAX_PHY_RATE_TO_MIN_THROUGHPUT_RATIO_5G = 0.37
IPERF_TO_NC_THROUGHPUT_RATIO = 0.8
MAX_PHY_RATE_TO_MIN_THROUGHPUT_RATIO_2G = 0.10
WLAN_MEDIUM_THROUGHPUT_CAP_MBPS = (
    15  # cap for WLAN medium due to encryption overhead
)

CLASSIC_BT_MEDIUM_THROUGHPUT_BENCHMARK_MBPS = 0.02
BLE_MEDIUM_THROUGHPUT_BENCHMARK_MBPS = 0.02

KEEP_ALIVE_TIMEOUT_BT_MS = 30000
KEEP_ALIVE_INTERVAL_BT_MS = 5000

KEEP_ALIVE_TIMEOUT_WIFI_MS = 10000
KEEP_ALIVE_INTERVAL_WIFI_MS = 3000

PERCENTILE_50_FACTOR = 0.5
LATENCY_PRECISION_DIGITS = 1

UNSET_LATENCY = datetime.timedelta.max
UNSET_THROUGHPUT_KBPS = -1.0
MAX_NUM_BUG_REPORT = 5
INVALID_INT = -1
INVALID_RSSI = -128
RSSI_HIGH_THRESHOLD = -15

TRANSFER_FILE_SIZE_500MB = 500 * 1024  # kB
TRANSFER_FILE_SIZE_200MB = 200 * 1024  # kB
TRANSFER_FILE_SIZE_20MB = 20 * 1024  # kB
TRANSFER_FILE_SIZE_1MB = 1024  # kB
TRANSFER_FILE_SIZE_500KB = 512  # kB
TRANSFER_FILE_SIZE_1KB = 1  # kB
TRANSFER_FILE_SIZE_20KB = 20  # kB
TRANSFER_FILE_SIZE_10KB = 10  # kB

TRANSFER_FILE_SIZE_FUNC_TEST_KB = 1
TRANSFER_FILE_NUM_DEFAULT = 1
TRANSFER_FILE_NUM_FUNC_TEST = 100
TRANSFER_TIMEOUT_FUNC_TEST_SEC = datetime.timedelta(seconds=100)

TARGET_CUJ_QUICK_START = 'quick_start'
TARGET_CUJ_NEARBY_CONNECTIONS_FUNCTION = 'nearby_connections_function'
TARGET_CUJ_ESIM = 'setting_based_esim_transfer'
TARGET_CUJ_QUICK_SHARE = 'quick_share'


@enum.unique
class PayloadType(enum.IntEnum):
  FILE = 2
  STREAM = 3


@enum.unique
class NearbyMedium(enum.IntEnum):
  """Medium options for discovery, advertising, connection and upgrade."""
  # need to align with MediumSettingsFactory.java in snippet
  AUTO = 0
  BT_ONLY = 1
  BLE_ONLY = 2
  WIFILAN_ONLY = 3
  WIFIAWARE_ONLY = 4  # connect or upgrade to aware medium
  UPGRADE_TO_WEBRTC = 5
  UPGRADE_TO_WIFIHOTSPOT = 6  # connect or upgrade to hotspot medium
  UPGRADE_TO_WIFIDIRECT = 7  # connect or upgrade to wifi direct medium
  BLE_L2CAP_ONLY = 8
  # including WIFI_LAN, WIFI_HOTSPOT, WIFI_DIRECT or WIFI_AWARE
  UPGRADE_TO_ALL_WIFI = 9  # connect or upgrade to any wifi medium


@dataclasses.dataclass(frozen=False)
class TestParameters:
  """Test parameters to be customized for Nearby Connection."""

  target_cuj_name: str = 'unspecified'
  requires_bt_multiplex: bool = False
  requires_3p_api_test: bool = False
  abort_all_tests_on_function_tests_fail: bool = True
  fast_fail_on_any_error: bool = False
  use_auto_controlled_wifi_ap: bool = False
  wifi_2g_ssid: str = ''
  wifi_2g_password: str = ''
  wifi_5g_ssid: str = ''
  wifi_5g_password: str = ''
  wifi_dfs_5g_ssid: str = ''
  wifi_dfs_5g_password: str = ''
  wifi_ssid: str = ''  # optional, for tests which can use any wifi
  wifi_password: str = ''
  advertising_discovery_medium: NearbyMedium = NearbyMedium.BLE_ONLY
  connection_medium: NearbyMedium = NearbyMedium.BT_ONLY
  toggle_airplane_mode_target_side: bool = False
  reset_wifi_connection: bool = True
  disconnect_bt_after_test: bool = False
  disconnect_wifi_after_test: bool = False
  payload_type: PayloadType = PayloadType.FILE
  allow_unrooted_device: bool = False
  keep_alive_timeout_ms: int = KEEP_ALIVE_TIMEOUT_WIFI_MS
  keep_alive_interval_ms: int = KEEP_ALIVE_INTERVAL_WIFI_MS
  enable_2g_ble_scan_throttling: bool = True
  enable_instant_connection: bool = False
  target_post_wifi_connection_idle_time_sec: int = (
      TARGET_POST_WIFI_CONNECTION_IDLE_TIME_SEC
  )

  run_function_tests_with_performance_tests: bool = True
  run_bt_performance_test: bool = True
  run_ble_performance_test: bool = False
  run_bt_coex_test: bool = True
  run_directed_test: bool = True
  run_compound_test: bool = True
  run_aware_test: bool = False
  run_iperf_test: bool = False  # run iperf test for possible mediums
  run_iperf_test_if_nc_speed_is_low: bool = True
  run_iperf_test_wlan: bool = True  # run iperf test for WLAN medium
  check_iperf_speed: bool = True  # check iperf speed if it is available
  run_nearby_connections_function_tests: bool = False
  skip_test_if_wifi_chipset_is_empty: bool = True
  skip_bug_report: bool = False
  force_telephony_cc: bool = False
  bypass_airplane_mode_toggling: bool = False

  @classmethod
  def from_user_params(
      cls,
      user_params: dict[str, Any]) -> 'TestParameters':
    """convert the parameters from the testbed to the test parameter."""

    # Convert G3 user int parameter in str format to int.
    for key, value in user_params.items():
      if key == 'mh_files':
        continue
      logging.info('[Test Parameters] %s: %s', key, value)
      if value in ('true', 'True'):
        user_params[key] = True
      elif value in ('false', 'False'):
        user_params[key] = False
      elif isinstance(value, bool):
        user_params[key] = value
      elif isinstance(value, str) and value.isdigit():
        user_params[key] = ast.literal_eval(value)

    test_parameters_names = {
        field.name for field in dataclasses.fields(cls)
    }
    test_parameters = cls(
        **{
            key: val
            for key, val in user_params.items()
            if key in test_parameters_names
        }
    )

    if test_parameters.target_cuj_name == TARGET_CUJ_QUICK_START:
      test_parameters.requires_bt_multiplex = True

    return test_parameters


@enum.unique
class NearbyConnectionMedium(enum.IntEnum):
  """Copied from com.google.android.gms.nearby.connection."""
  UNKNOWN = 0
  # reserved 1, it's Medium.MDNS, not used now
  BLUETOOTH = 2
  WIFI_HOTSPOT = 3
  BLE = 4
  WIFI_LAN = 5
  WIFI_AWARE = 6
  NFC = 7
  WIFI_DIRECT = 8
  WEB_RTC = 9
  BLE_L2CAP = 10
  USB = 11


def is_high_quality_medium(medium: NearbyMedium) -> bool:
  return medium in {
      NearbyMedium.WIFILAN_ONLY,
      NearbyMedium.WIFIAWARE_ONLY,
      NearbyMedium.UPGRADE_TO_WEBRTC,
      NearbyMedium.UPGRADE_TO_WIFIHOTSPOT,
      NearbyMedium.UPGRADE_TO_WIFIDIRECT,
      NearbyMedium.UPGRADE_TO_ALL_WIFI,
  }


@enum.unique
class MediumUpgradeType(enum.IntEnum):
  DEFAULT = 0
  DISRUPTIVE = 1
  NON_DISRUPTIVE = 2


@enum.unique
class WifiD2DType(enum.IntEnum):
  SCC_2G = 0
  SCC_5G = 1
  MCC_2G_WFD_5G_STA = 2
  MCC_2G_WFD_5G_INDOOR_STA = 3
  MCC_5G_WFD_5G_DFS_STA = 4
  MCC_5G_HS_5G_DFS_STA = 5


@enum.unique
class SingleTestFailureReason(enum.IntEnum):
  """The failure reasons for a nearby connect connection test."""
  UNINITIALIZED = 0
  SOURCE_START_DISCOVERY = 1
  TARGET_START_ADVERTISING = 2
  SOURCE_REQUEST_CONNECTION = 3
  TARGET_ACCEPT_CONNECTION = 4
  WIFI_MEDIUM_UPGRADE = 5
  FILE_TRANSFER_FAIL = 6
  FILE_TRANSFER_THROUGHPUT_LOW = 7
  SOURCE_WIFI_CONNECTION = 8
  TARGET_WIFI_CONNECTION = 9
  AP_IS_NOT_CONFIGURED = 10
  DISCONNECTED_FROM_AP = 11
  WRONG_AP_FREQUENCY = 12
  WRONG_P2P_FREQUENCY = 13
  DEVICE_CONFIG_ERROR = 14
  SUCCESS = 15

COMMON_WIFI_CONNECTION_FAILURE_REASONS = (
    ' 1) Check if the wifi ssid or password is correct;\n',
    ' 2) Try to remove any saved wifi network from wifi settings;\n',
    ' 3) Check if other device can connect to the same AP\n',
    ' 4) Check the wifi connection related log on the device.\n',
    ' 5) Check if RSSI is too high and device is too close to the AP.\n',
)

COMMON_TRIAGE_TIP: dict[SingleTestFailureReason, str] = {
    SingleTestFailureReason.UNINITIALIZED: (
        'not executed, the whole test was exited earlier; the devices may be'
        ' disconnected from the host, abnormal things, such as system crash, '
        ' mobly snippet was killed; Or something wrong with the script, check'
        ' the test running log and the corresponding bugreport log.'
    ),
    SingleTestFailureReason.SUCCESS: 'success!',
    SingleTestFailureReason.SOURCE_START_DISCOVERY: (
        'The source device fails to discover the target device.'
    ),
    SingleTestFailureReason.TARGET_START_ADVERTISING: (
        'The target device can not start advertising.'
    ),
    SingleTestFailureReason.SOURCE_REQUEST_CONNECTION: (
        'The source device fails to connect to the target device'
    ),
    SingleTestFailureReason.TARGET_ACCEPT_CONNECTION: (
        'The target device fails to accept the connection.'
    ),
    SingleTestFailureReason.SOURCE_WIFI_CONNECTION: (
        'The source device can not connect to the wifi AP.\n'
        f'{COMMON_WIFI_CONNECTION_FAILURE_REASONS}'
    ),
    SingleTestFailureReason.TARGET_WIFI_CONNECTION: (
        'The target device can not connect to the wifi AP.\n'
        f'{COMMON_WIFI_CONNECTION_FAILURE_REASONS}'
    ),
    SingleTestFailureReason.AP_IS_NOT_CONFIGURED: (
        'The test AP is not set correctly in the test configuration file.'
    ),
    SingleTestFailureReason.DISCONNECTED_FROM_AP: (
        'The STA is disconnected from the AP. Check AP DHCP config. Check if'
        ' other devices can connect to the same AP.'
    ),
    SingleTestFailureReason.WRONG_AP_FREQUENCY: (
        'Check if the test AP is set to the expected frequency.'
    ),
    SingleTestFailureReason.WRONG_P2P_FREQUENCY: '\n'.join([
        'The test P2P frequency is not set to the expected value.',
        ' Check if device capabilities are set correctly in the config file.',
        ' If it is SCC DBS test case, check if the device does support DBS;',
        (
            ' If it is the SCC indoor or DFS test case, check if the device'
            ' does support indoor/DFS channels in WFD mode;'
        ),
        (
            ' If it is a MCC test, check if devices actually supports DBS,'
            ' indoor or DFS feature  and set device capabilities correctly.'
        ),
    ]),
    SingleTestFailureReason.DEVICE_CONFIG_ERROR: (
        'Check if device capabilities are set correctly in the config file.'
    ),
}

COMMON_WFD_UPGRADE_FAILURE_REASONS = '\n'.join([
    (
        'If WFD group owner fails to start, check your factory build to ensure'
        ' that'
    ),
    (
        ' 1) includes the wpa_supplicant patch to avoid scan before starting GO'
        ' https://w1.fi/cgit/hostap/commit/?id=b18d95759375834b6ca6f864c898f27d161b14ca.'
    ),
    (
        ' 2) includes WiFi mainline module 34.11.10.06.0 or later version which'
        ' fixes the out-of-order message issue between P2P and tethering'
        ' modules'
    ),
    (
        ' 3) HAL getUsableChannels() returns the correct channel list. Run "adb'
        ' shell cmd wifi get-allowed-channel" and ensure it does not include'
        ' DFS channels unless config_wifiEnableStaDfsChannelForPeerNetwork is'
        ' set to true. DFS channels can be found from'
        ' https://en.wikipedia.org/wiki/List_of_WLAN_channels.'
    ),
    (
        'Also check if BT socket is still connected and read/write is normal'
        ' when the upgrade failure happens.'
    ),
    (
        ' If WFD group client fails to connect, check if the devices are too'
        ' close to each other. The recommended minimum device is 10cm (4'
        ' inches).'
    ),
])

MEDIUM_UPGRADE_FAIL_TRIAGE_TIPS: dict[NearbyMedium, str] = {
    NearbyMedium.WIFILAN_ONLY: (
        ' WLAN, check if AP blocks the mDNS traffic. Check if STA is connected'
        ' to AP during WiFi upgrade.'
    ),
    NearbyMedium.UPGRADE_TO_WIFIHOTSPOT: (
        ' HOTSPOT, check the related wifip2p and NearbyConnections logs to see'
        ' if the WFD group owner fails to start on'
        ' the target side or the STA fails to connect on the source side.\n'
        f' {COMMON_WFD_UPGRADE_FAILURE_REASONS}'
    ),
    NearbyMedium.UPGRADE_TO_WIFIDIRECT: (
        ' WFD, check the related wifip2p and NearbyConnections logs if the WFD'
        ' group owner fails to start on the target side or WFD group client'
        ' fails to connect on the source side. \n'
        f' {COMMON_WFD_UPGRADE_FAILURE_REASONS}'
    ),
    NearbyMedium.UPGRADE_TO_ALL_WIFI: (
        ' all WiFI mediums, check NearbyConnections logs to see if WFD, WLAN'
        ' and HOTSPOT mediums are tried and if the failure is on the target or'
        ' source side. Check directed test results to see which medium fails.'
    ),
}


@dataclasses.dataclass(frozen=True)
class ConnectionSetupTimeouts:
  """The timeouts of the nearby connection setup."""
  discovery_timeout: datetime.timedelta | None = None
  connection_init_timeout: datetime.timedelta | None = None
  connection_result_timeout: datetime.timedelta | None = None


@dataclasses.dataclass(frozen=False)
class ConnectionSetupQualityInfo:
  """The quality information of the nearby connection setup."""
  discovery_latency: datetime.timedelta = UNSET_LATENCY
  connection_latency: datetime.timedelta = UNSET_LATENCY
  medium_upgrade_latency: datetime.timedelta = UNSET_LATENCY
  medium_upgrade_expected: bool = False
  upgrade_medium: NearbyConnectionMedium | None = None
  medium_frequency: int = INVALID_INT

  def get_dict(self) -> dict[str, str]:
    dict_repr = {
        'discovery': f'{round(self.discovery_latency.total_seconds(), 1)}s',
        'connection': f'{round(self.connection_latency.total_seconds(), 1)}s'
    }
    if self.medium_upgrade_expected:
      dict_repr['upgrade'] = (
          f'{round(self.medium_upgrade_latency.total_seconds(), 1)}s'
      )
    if self.upgrade_medium:
      dict_repr['medium'] = self.upgrade_medium.name
    return dict_repr

  def get_medium_name(self) -> str:
    if self.upgrade_medium:
      return self.upgrade_medium.name
    return 'na'


@dataclasses.dataclass(frozen=False)
class SingleTestResult:
  """The test result of a single iteration."""

  test_iteration: int = 0
  is_failed_with_prior_bt: bool = False
  failure_reason: SingleTestFailureReason = (
      SingleTestFailureReason.UNINITIALIZED
  )
  result_message: str = ''
  prior_nc_quality_info: ConnectionSetupQualityInfo = dataclasses.field(
      default_factory=ConnectionSetupQualityInfo
  )
  discoverer_sta_latency: datetime.timedelta = UNSET_LATENCY
  quality_info: ConnectionSetupQualityInfo = (
      dataclasses.field(default_factory=ConnectionSetupQualityInfo)
  )
  file_transfer_throughput_kbps: float = UNSET_THROUGHPUT_KBPS
  iperf_throughput_kbps: float = UNSET_THROUGHPUT_KBPS
  advertiser_sta_latency: datetime.timedelta = UNSET_LATENCY
  discoverer_sta_expected: bool = False
  advertiser_wifi_expected: bool = False
  sta_frequency: int = INVALID_INT
  max_sta_link_speed_mbps: int = INVALID_INT
  start_time: datetime.datetime = datetime.datetime.now()


@dataclasses.dataclass(frozen=False)
class NcPerformanceTestMetrics:
  """Metrics data for quick start test."""

  prior_bt_discovery_latencies: list[datetime.timedelta] = dataclasses.field(
      default_factory=list[datetime.timedelta]
  )
  prior_bt_connection_latencies: list[datetime.timedelta] = dataclasses.field(
      default_factory=list[datetime.timedelta]
  )
  discoverer_wifi_sta_latencies: list[datetime.timedelta] = dataclasses.field(
      default_factory=list[datetime.timedelta]
  )
  file_transfer_discovery_latencies: list[datetime.timedelta] = (
      dataclasses.field(default_factory=list[datetime.timedelta])
  )
  file_transfer_connection_latencies: list[datetime.timedelta] = (
      dataclasses.field(default_factory=list[datetime.timedelta])
  )
  medium_upgrade_latencies: list[datetime.timedelta] = dataclasses.field(
      default_factory=list[datetime.timedelta])
  advertiser_wifi_sta_latencies: list[datetime.timedelta] = dataclasses.field(
      default_factory=list[datetime.timedelta])
  file_transfer_throughputs_kbps: list[float] = dataclasses.field(
      default_factory=list[float])
  iperf_throughputs_kbps: list[float] = dataclasses.field(
      default_factory=list[float])
  upgraded_wifi_transfer_mediums: list[NearbyConnectionMedium] = (
      dataclasses.field(default_factory=list[NearbyConnectionMedium]))


@dataclasses.dataclass(frozen=True)
class TestResultStats:
  """The test result stats."""
  success_count: int | None = None
  zero_count: int | None = None
  min_val: float | None = None
  median_val: float | None = None
  max_val: float | None = None


@dataclasses.dataclass(frozen=True)
class SpeedTarget:
  """The speed target in MB/s."""
  iperf_speed_mbtye_per_sec: float
  nc_speed_mbtye_per_sec: float
