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

import dataclasses
import datetime
import enum

from betocq import constants

# MCC hotspot test is more flaky than other MCC tests due to the sync issue.
MCC_HOTSPOT_TEST_SUCCESS_RATE_TARGET = 0.90

MCC_PERFORMANCE_TEST_COUNT = 50
MCC_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR = 5
BT_PERFORMANCE_TEST_COUNT = 20
BT_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR = 5
BT_COEX_PERFORMANCE_TEST_COUNT = 100
BT_COEX_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR = 5
LOHS_PERFORMANCE_TEST_COUNT = 100
LOHS_PERFORMANCE_TEST_MAX_CONSECUTIVE_ERROR = 5

BT_1K_PAYLOAD_TRANSFER_TIMEOUT = datetime.timedelta(seconds=20)
BT_500K_PAYLOAD_TRANSFER_TIMEOUT = datetime.timedelta(seconds=35)
WIFI_1K_PAYLOAD_TRANSFER_TIMEOUT = datetime.timedelta(seconds=20)

CLASSIC_BT_MEDIUM_THROUGHPUT_BENCHMARK_MBPS = 0.02
BLE_MEDIUM_THROUGHPUT_BENCHMARK_MBPS = 0.02

KEEP_ALIVE_TIMEOUT_BT_MS = 30000
KEEP_ALIVE_INTERVAL_BT_MS = 5000
KEEP_ALIVE_TIMEOUT_WIFI_MS = 10000
KEEP_ALIVE_INTERVAL_WIFI_MS = 3000

TRANSFER_FILE_SIZE_500KB = 512  # kB
NC_MCC_2G_D2D_5G_STA_TRANSFER_FILE_SIZE_KB = 20 * 1024  # kB
NC_MCC_5G_D2D_2G_STA_TRANSFER_FILE_SIZE_KB = 120 * 1024  # kB
NC_MCC_5G_D2D_5G_STA_TRANSFER_FILE_SIZE_KB = 120 * 1024  # kB
NC_SCC_2G_TRANSFER_FILE_SIZE_KB = 20 * 1024  # kB
NC_SCC_5G_TRANSFER_FILE_SIZE_KB = 500 * 1024  # kB


@enum.unique
class NcBandwidthUpgradeStatus(enum.IntEnum):
  UNKNOWN = 0
  # The upgrade is successful.
  SUCCESS = 1
  # The connection is lost, attempting to reconnect.
  SUSPENDED = 2
  # The upgrade is timed out.
  TIMED_OUT = 3


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
      default_factory=list[datetime.timedelta]
  )
  advertiser_wifi_sta_latencies: list[datetime.timedelta] = dataclasses.field(
      default_factory=list[datetime.timedelta]
  )
  file_transfer_throughputs_kbps: list[float] = dataclasses.field(
      default_factory=list[float]
  )
  iperf_throughputs_kbps: list[float] = dataclasses.field(
      default_factory=list[float]
  )
  upgraded_wifi_transfer_mediums: list[constants.NearbyConnectionMedium] = (
      dataclasses.field(default_factory=list[constants.NearbyConnectionMedium])
  )
