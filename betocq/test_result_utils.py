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

"""Utilities for handling test results."""

from __future__ import annotations

import collections
from collections.abc import Sequence
import dataclasses
import datetime
import logging
import typing
from typing import Any

from mobly import asserts
from mobly.controllers import android_device

from betocq import iperf_utils
from betocq import nc_constants
from betocq import setup_utils
from betocq import version

_BITS_PER_BYTE = 8


def _convert_kbps_to_mbps(throughput_kbps: float) -> float:
  """Convert throughput from kbyte/s to mbyte/s."""
  return round(throughput_kbps / 1024, 1)


def _float_to_str(value: float, precision: int) -> str:
  return f'{round(value, precision)}'


def set_and_assert_p2p_frequency(
    ad: android_device.AndroidDevice,
    test_result: SingleTestResult,
    is_mcc: bool,
    is_dbs_mode: bool,
    sta_frequency: int,
    additional_error_message: str = '',
):
  """Asserts the p2p frequency is expected."""
  p2p_frequency = setup_utils.get_wifi_p2p_frequency(ad)
  test_result.quality_info.medium_frequency = p2p_frequency
  if (
      p2p_frequency == nc_constants.INVALID_INT
      or sta_frequency == nc_constants.INVALID_INT
  ):
    ad.log.warning(
        'The P2P frequency ({p2p_frequency}) or STA frequency ({sta_frequency})'
        ' is not available, the test result may not be expected.'
    )
    return

  # Check for MCC.
  if is_mcc:
    if p2p_frequency != sta_frequency:
      return
    test_result.set_active_nc_fail_reason(
        nc_constants.SingleTestFailureReason.WRONG_P2P_FREQUENCY
    )
    asserts.fail(
        f'P2P frequeny ({p2p_frequency}) is same as STA frequency'
        f' ({sta_frequency}) in MCC test case. {additional_error_message}'
    )

  # Check for SCC.
  if (not is_dbs_mode) and (p2p_frequency != sta_frequency):
    test_result.set_active_nc_fail_reason(
        nc_constants.SingleTestFailureReason.WRONG_P2P_FREQUENCY
    )
    asserts.fail(
        f'P2P frequeny ({p2p_frequency}) is different from STA frequency'
        f' ({sta_frequency}) in SCC test case. {additional_error_message}'
    )
  if is_dbs_mode and p2p_frequency == sta_frequency:
    test_result.set_active_nc_fail_reason(
        nc_constants.SingleTestFailureReason.WRONG_P2P_FREQUENCY
    )
    asserts.fail(
        f'P2P frequeny ({p2p_frequency}) is the same as STA frequency'
        f' ({sta_frequency}) in SCC+DBS test case. {additional_error_message}'
    )


# Add back temporarily, will be removed after refractoring refactor DCT tests.
def collect_nc_test_metrics(
    test_result: SingleTestResult,
    nc_test_runtime: nc_constants.NcTestRuntime,
):
  """Collects general test metrics for nearby connection tests."""
  advertiser = nc_test_runtime.advertiser
  sta_frequency, max_link_speed_mbps = (
      setup_utils.get_target_sta_frequency_and_max_link_speed(advertiser)
  )
  test_result.sta_frequency = sta_frequency
  test_result.max_sta_link_speed_mbps = max_link_speed_mbps

  if test_result.quality_info.upgrade_medium in [
      nc_constants.NearbyConnectionMedium.WIFI_DIRECT,
      nc_constants.NearbyConnectionMedium.WIFI_HOTSPOT,
  ]:
    test_result.quality_info.medium_frequency = (
        setup_utils.get_wifi_p2p_frequency(advertiser)
    )


# Add back temporarily, will be removed after refractoring refactor DCT tests.
def assert_sta_frequency(
    test_result: SingleTestResult,
    expected_wifi_type: nc_constants.WifiType,
):
  """Asserts the STA frequency is expected."""
  sta_frequency = test_result.sta_frequency
  # Check whether the device is still connected to the AP.
  if sta_frequency == nc_constants.INVALID_INT:
    test_result.set_active_nc_fail_reason(
        nc_constants.SingleTestFailureReason.DISCONNECTED_FROM_AP
    )
    asserts.fail('Target device is disconnected from AP. Check AP DHCP config.')

  # Check whether the STA frequency is expected.
  match expected_wifi_type:
    case nc_constants.WifiType.FREQ_2G:
      is_valid_freq = sta_frequency <= nc_constants.MAX_FREQ_2G_MHZ
    case nc_constants.WifiType.FREQ_5G:
      is_valid_freq = sta_frequency > nc_constants.MAX_FREQ_2G_MHZ and (
          sta_frequency < nc_constants.MIN_FREQ_5G_DFS_MHZ
          or sta_frequency > nc_constants.MAX_FREQ_5G_DFS_MHZ
      )
    case nc_constants.WifiType.FREQ_5G_DFS:
      is_valid_freq = (
          sta_frequency >= nc_constants.MIN_FREQ_5G_DFS_MHZ
          and sta_frequency <= nc_constants.MAX_FREQ_5G_DFS_MHZ
      )

  if is_valid_freq:
    return

  test_result.set_active_nc_fail_reason(
      nc_constants.SingleTestFailureReason.WRONG_AP_FREQUENCY
  )
  asserts.fail(f'AP is set to a wrong frequency {sta_frequency}')


def set_and_assert_sta_frequency(
    ad: android_device.AndroidDevice,
    test_result: SingleTestResult,
    expected_wifi_type: nc_constants.WifiType,
):
  """Asserts the STA frequency is expected."""

  connection_info = ad.nearby.wifiGetConnectionInfo()
  sta_frequency, max_link_speed_mbps = (
      setup_utils.get_sta_frequency_and_max_link_speed(ad, connection_info)
  )
  test_result.sta_frequency = sta_frequency
  test_result.max_sta_link_speed_mbps = max_link_speed_mbps

  if sta_frequency == nc_constants.INVALID_INT:
    ad.log.warning(
        'The STA frequency is not available, connection_info:'
        f' {connection_info}, the test may not be expected.'
    )
    if (
        connection_info.get('SupplicantState', '')
        != nc_constants.WIFI_SUPPLICANT_STATE_COMPLETED
    ):
      if ad.role == 'target':
        test_result.test_failure_reason = (
            nc_constants.SingleTestFailureReason.TARGET_WIFI_CONNECTION
        )
      else:
        test_result.test_failure_reason = (
            nc_constants.SingleTestFailureReason.SOURCE_WIFI_CONNECTION
        )
      asserts.fail(
          nc_constants.COMMON_TRIAGE_TIP[test_result.test_failure_reason]
      )
    ad.log.warning(
        'The STA frequency is not available, but the STA is'
        ' connected, the test result may not be expected.'
    )
    return

  additional_error_message = ''
  # Check whether the STA frequency is expected.
  match expected_wifi_type:
    case nc_constants.WifiType.FREQ_2G:
      is_valid_freq = sta_frequency <= nc_constants.MAX_FREQ_2G_MHZ
      if not is_valid_freq:
        additional_error_message = (
            ' The channel is expected to be a 2G channel.'
        )
    case nc_constants.WifiType.FREQ_5G:
      is_valid_freq = sta_frequency > nc_constants.MAX_FREQ_2G_MHZ and (
          sta_frequency < nc_constants.MIN_FREQ_5G_DFS_MHZ
          or sta_frequency > nc_constants.MAX_FREQ_5G_DFS_MHZ
      )
      if not is_valid_freq:
        additional_error_message = (
            ' The channel is expected to be a 5G channel.'
        )
    case nc_constants.WifiType.FREQ_5G_DFS:
      is_valid_freq = (
          sta_frequency >= nc_constants.MIN_FREQ_5G_DFS_MHZ
          and sta_frequency <= nc_constants.MAX_FREQ_5G_DFS_MHZ
      )
      if not is_valid_freq:
        additional_error_message = (
            ' The channel is expected to be a 5G DFS channel.'
            ' If the test is not in a shield box or room, the DFS channel may'
            ' be changed by the AP due to radar signals detected, reset the AP'
            ' to a DFS channel and run the test in a shield box or room to'
            ' avoid such an issue in the future.'
        )

  if not is_valid_freq:
    test_result.set_active_nc_fail_reason(
        nc_constants.SingleTestFailureReason.WRONG_AP_FREQUENCY
    )
    # The correct frequency is critical
    asserts.abort_all(
        f'AP is set to a wrong frequency {sta_frequency}, check the AP'
        f' configuration and the test configuration.{additional_error_message}'
    )


def assert_2g_wifi_throughput_and_run_iperf_if_needed(
    test_result: SingleTestResult,
    nc_test_runtime: nc_constants.NcTestRuntime,
    low_throughput_tip: str,
    did_nc_file_transfer: bool = True,
):
  """Checks the throughput for 2G WiFi medium and runs iperf test if needed."""
  speed_target = _get_2g_wifi_throughput_benchmark(
      test_result=test_result,
      nc_test_runtime=nc_test_runtime,
  )
  logging.info('speed target: %s', speed_target)
  assert_throughput_and_run_iperf_if_needed(
      test_result,
      nc_test_runtime,
      speed_target,
      low_throughput_tip,
      did_nc_file_transfer,
  )


def assert_2g_wifi_throughput(
    test_result: SingleTestResult,
    nc_test_runtime: nc_constants.NcTestRuntime,
    low_throughput_tip: str,
):
  """Checks the throughput for 2G WiFi medium."""
  speed_target = _get_2g_wifi_throughput_benchmark(
      test_result=test_result,
      nc_test_runtime=nc_test_runtime,
  )
  logging.info('speed target: %s', speed_target)
  assert_throughput(
      test_result,
      speed_target,
      low_throughput_tip,
  )


def _get_2g_wifi_throughput_benchmark(
    test_result: SingleTestResult,
    nc_test_runtime: nc_constants.NcTestRuntime,
) -> nc_constants.SpeedTarget:
  """Gets the throughput benchmark as MBps."""
  discoverer = nc_test_runtime.discoverer
  advertiser = nc_test_runtime.advertiser
  if nc_test_runtime.wifi_info is None:
    return nc_constants.SpeedTarget(
        nc_constants.INVALID_INT, nc_constants.INVALID_INT
    )

  max_num_streams = min(discoverer.max_num_streams, advertiser.max_num_streams)

  max_phy_rate_mbps = min(
      discoverer.max_phy_rate_2g_mbps,
      advertiser.max_phy_rate_2g_mbps,
  )
  max_phy_rate_mbps = min(
      max_phy_rate_mbps,
      max_num_streams * nc_constants.MAX_PHY_RATE_PER_STREAM_N_20_MBPS,
  )
  min_throughput_mbyte_per_sec = int(
      max_phy_rate_mbps
      * nc_constants.MAX_PHY_RATE_TO_MIN_THROUGHPUT_RATIO_2G
      / _BITS_PER_BYTE
  )
  nc_min_throughput_mbyte_per_sec = min_throughput_mbyte_per_sec

  nc_test_runtime.advertiser.log.info(
      'target STA freq = %d, max STA speed (Mb/s): %d,'
      ' max D2D speed (MB/s): %.2f, min D2D speed (MB/s),'
      ' iperf: %.2f, nc: %.2f',
      test_result.sta_frequency,
      test_result.max_sta_link_speed_mbps,
      max_phy_rate_mbps / _BITS_PER_BYTE,
      min_throughput_mbyte_per_sec,
      nc_min_throughput_mbyte_per_sec,
  )

  return nc_constants.SpeedTarget(
      min_throughput_mbyte_per_sec, nc_min_throughput_mbyte_per_sec
  )


def assert_5g_wifi_throughput_and_run_iperf_if_needed(
    test_result: SingleTestResult,
    nc_test_runtime: nc_constants.NcTestRuntime,
    low_throughput_tip: str,
    did_nc_file_transfer: bool = True,
):
  """Checks the throughput for 5G WiFi medium and runs iperf test if needed."""
  speed_target = _get_5g_wifi_throughput_benchmark(
      test_result=test_result,
      nc_test_runtime=nc_test_runtime,
  )
  logging.info('speed target: %s', speed_target)
  assert_throughput_and_run_iperf_if_needed(
      test_result,
      nc_test_runtime,
      speed_target,
      low_throughput_tip,
      did_nc_file_transfer,
  )


def assert_5g_wifi_throughput(
    test_result: SingleTestResult,
    nc_test_runtime: nc_constants.NcTestRuntime,
    low_throughput_tip: str,
    is_dct: bool = True,
    is_tdls_enabled: bool = True,
):
  """Checks the throughput for 5G medium."""
  speed_target = _get_5g_wifi_throughput_benchmark(
      test_result=test_result,
      nc_test_runtime=nc_test_runtime,
      is_dct=is_dct,
      is_tdls_enabled=is_tdls_enabled,
  )
  logging.info('speed target: %s', speed_target)
  assert_throughput(
      test_result,
      speed_target,
      low_throughput_tip,
  )


def _get_5g_wifi_throughput_benchmark(
    test_result: SingleTestResult,
    nc_test_runtime: nc_constants.NcTestRuntime,
    is_dct: bool = False,
    is_tdls_enabled: bool = True,
):
  """Gets the throughput benchmark as MBps."""
  discoverer = nc_test_runtime.discoverer
  advertiser = nc_test_runtime.advertiser
  if nc_test_runtime.wifi_info is None:
    return nc_constants.SpeedTarget(
        nc_constants.INVALID_INT, nc_constants.INVALID_INT
    )
  is_mcc = nc_test_runtime.wifi_info.is_mcc
  is_dbs_mode = nc_test_runtime.is_dbs_mode
  is_wlan_medium = (
      nc_test_runtime.upgrade_medium_under_test
      == nc_constants.NearbyMedium.WIFILAN_ONLY
  )
  is_wifi_hotspot_medium = (
      nc_test_runtime.upgrade_medium_under_test
      == nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT
  )
  is_tdls_supported = (
      nc_test_runtime.advertiser.nearby.wifiIsTdlsSupported()
      and nc_test_runtime.discoverer.nearby.wifiIsTdlsSupported()
  )

  # Step 1. Calculate max_phy_rate_mbps.
  max_num_streams = _get_max_num_streams(discoverer, advertiser, is_dbs_mode)
  is_ap_bandwidth_less_than_80mhz = _is_5g_ap_bandwidth_less_than_80mhz(
      test_result=test_result, max_num_streams=max_num_streams
  )

  if is_ap_bandwidth_less_than_80mhz:
    max_phy_rate_mbps = min([
        discoverer.max_phy_rate_5g_mbps,
        advertiser.max_phy_rate_5g_mbps,
        max_num_streams * nc_constants.MAX_PHY_RATE_PER_STREAM_AC_40_MBPS,
    ])
  else:
    max_phy_rate_mbps = min([
        discoverer.max_phy_rate_5g_mbps,
        advertiser.max_phy_rate_5g_mbps,
        max_num_streams * nc_constants.MAX_PHY_RATE_PER_STREAM_AC_80_MBPS,
    ])

  # Step 2. Calculate min_throughput_mbyte_per_sec.
  min_throughput_mbyte_per_sec = int(
      max_phy_rate_mbps
      * nc_constants.MAX_PHY_RATE_TO_MIN_THROUGHPUT_RATIO_5G
      / _BITS_PER_BYTE
  )

  # Step 3. Adjust min_throughput_mbyte_per_sec according to medium info.
  if is_mcc:
    min_throughput_mbyte_per_sec = int(
        min_throughput_mbyte_per_sec * nc_constants.MCC_THROUGHPUT_MULTIPLIER
    )
    # MCC hotspot has even lower throughput due to sync issue with STA.
    if is_wifi_hotspot_medium:
      min_throughput_mbyte_per_sec = (
          min_throughput_mbyte_per_sec
          * nc_constants.MCC_HOTSPOT_THROUGHPUT_MULTIPLIER
      )

  # Cut the speed target by half if TDLS is not supported.
  if is_wlan_medium and (not is_tdls_supported or not is_tdls_enabled):
    min_throughput_mbyte_per_sec /= 2.0

  # Step 4. Calculate nc_min_throughput_mbyte_per_sec.
  iperf_to_nc_throughput_ratio = (
      nc_constants.IPERF_TO_NC_THROUGHPUT_RATIO_DCT
      if is_dct
      else nc_constants.IPERF_TO_NC_THROUGHPUT_RATIO
  )
  nc_min_throughput_mbyte_per_sec = (
      min_throughput_mbyte_per_sec * iperf_to_nc_throughput_ratio
  )
  # Limit NC min throughput due to encryption overhead
  if is_wlan_medium and not is_dct:
    nc_min_throughput_mbyte_per_sec = min(
        nc_min_throughput_mbyte_per_sec,
        nc_constants.WLAN_MEDIUM_THROUGHPUT_CAP_MBPS,
    )

  nc_test_runtime.advertiser.log.info(
      'target STA freq = %d, max STA speed (Mb/s): %d,'
      ' max D2D speed (MB/s): %.2f, min D2D speed (MB/s),'
      ' iperf: %.2f, nc: %.2f',
      test_result.sta_frequency,
      test_result.max_sta_link_speed_mbps,
      max_phy_rate_mbps / _BITS_PER_BYTE,
      min_throughput_mbyte_per_sec,
      nc_min_throughput_mbyte_per_sec,
  )

  return nc_constants.SpeedTarget(
      min_throughput_mbyte_per_sec, nc_min_throughput_mbyte_per_sec
  )


def _get_max_num_streams(
    discoverer: android_device.AndroidDevice,
    advertiser: android_device.AndroidDevice,
    is_dbs_mode: bool,
):
  """Gets the max num streams."""
  if is_dbs_mode:
    return advertiser.max_num_streams_dbs
  else:
    return min(discoverer.max_num_streams, advertiser.max_num_streams)


def _is_5g_ap_bandwidth_less_than_80mhz(
    test_result: SingleTestResult,
    max_num_streams: int,
):
  """Returns whether the 5G AP bandwidth is less than 80mhz."""
  max_phy_rate_ac80 = (
      max_num_streams * nc_constants.MAX_PHY_RATE_PER_STREAM_AC_80_MBPS
  )
  return all([
      test_result.sta_frequency > 5000,
      test_result.max_sta_link_speed_mbps > 0,
      test_result.max_sta_link_speed_mbps < max_phy_rate_ac80,
  ])


def assert_throughput(
    test_result: SingleTestResult,
    speed_target: nc_constants.SpeedTarget,
    low_throughput_tip: str,
):
  """Checks the file transfer throughput."""
  nc_speed_min_mbps = speed_target.nc_speed_mbtye_per_sec
  nc_speed_mbps = round(test_result.file_transfer_throughput_kbps / 1024, 3)

  if nc_speed_mbps >= nc_speed_min_mbps:
    return

  low_throughput_info = (
      f'file speed {nc_speed_mbps} < target {nc_speed_min_mbps} MB/s'
  )

  test_result.set_active_nc_fail_reason(
      nc_constants.SingleTestFailureReason.FILE_TRANSFER_THROUGHPUT_LOW,
      result_message=f'{low_throughput_info}. {low_throughput_tip}',
  )
  asserts.fail(low_throughput_info)


def assert_throughput_and_run_iperf_if_needed(
    test_result: SingleTestResult,
    nc_test_runtime: nc_constants.NcTestRuntime,
    speed_target: nc_constants.SpeedTarget,
    low_throughput_tip: str,
    did_nc_file_transfer: bool = True,
):
  """Checks the file transfer throughput and runs iperf test if needed."""
  advertiser = nc_test_runtime.advertiser
  discoverer = nc_test_runtime.discoverer
  upgrade_medium_under_test = nc_test_runtime.upgrade_medium_under_test

  nc_speed_min_mbps = speed_target.nc_speed_mbtye_per_sec
  iperf_speed_min_mbps = speed_target.iperf_speed_mbtye_per_sec
  nc_speed_mbps = round(test_result.file_transfer_throughput_kbps / 1024, 3)
  iperf_speed_mbps = 0

  if any([
      nc_speed_mbps < nc_speed_min_mbps,
      upgrade_medium_under_test == nc_constants.NearbyMedium.WIFILAN_ONLY,
  ]):
    iperf_speed_mbps = _run_iperf_test(
        test_result,
        advertiser,
        discoverer,
        upgrade_medium_under_test,
        nc_test_runtime.wifi_info,
    )

  low_throughput_info = None
  if did_nc_file_transfer and nc_speed_mbps < nc_speed_min_mbps:
    nc_speed_info = (
        f'file speed {nc_speed_mbps} < target {nc_speed_min_mbps} MB/s'
    )
    iperf_speed_info = (
        f' while iperf speed (MB/s) = {iperf_speed_mbps}'
        if iperf_speed_mbps > 0
        else ''
    )
    low_throughput_info = f'{nc_speed_info}{iperf_speed_info}'
  elif iperf_speed_mbps > 0 and iperf_speed_mbps < iperf_speed_min_mbps:
    low_throughput_info = (
        f' iperf speed {iperf_speed_mbps} < target {iperf_speed_min_mbps} MB/s'
    )

  if low_throughput_info is None:
    return

  test_result.set_active_nc_fail_reason(
      nc_constants.SingleTestFailureReason.FILE_TRANSFER_THROUGHPUT_LOW,
      result_message=f'{low_throughput_info}. {low_throughput_tip}',
  )
  asserts.fail(low_throughput_info)


def _run_iperf_test(
    test_result: SingleTestResult,
    advertiser: android_device.AndroidDevice,
    discoverer: android_device.AndroidDevice,
    upgrade_medium_under_test: nc_constants.NearbyMedium,
    wifi_info: nc_constants.WifiInfo | None,
) -> float:
  """Runs iperf test and returns the throughput. Returns 0 if not needed."""
  if wifi_info is None or wifi_info.is_mcc:
    return 0
  if upgrade_medium_under_test not in [
      nc_constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT,
      nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT,
      nc_constants.NearbyMedium.WIFILAN_ONLY,
      nc_constants.NearbyMedium.WIFIAWARE_ONLY,
  ]:
    return 0
  test_result.iperf_throughput_kbps = iperf_utils.run_iperf_test(
      discoverer,
      advertiser,
      test_result.quality_info.upgrade_medium,
  )
  logging.debug(
      'iperf throughput: %d (KB/s)', test_result.iperf_throughput_kbps
  )
  return round(test_result.iperf_throughput_kbps / 1024, 1)


def assert_nc_throughput_meets_target(
    test_result: SingleTestResult,
    nc_speed_min_mbps: float,
    low_throughput_tip: str,
):
  """Checks the Nearby connection throughput meets the target."""
  nc_speed_mbps = round(test_result.file_transfer_throughput_kbps / 1024, 3)
  if nc_speed_mbps >= nc_speed_min_mbps:
    return

  low_throughput_info = (
      f'file speed {nc_speed_mbps} < target {nc_speed_min_mbps} MB/s'
  )
  test_result.set_active_nc_fail_reason(
      nc_constants.SingleTestFailureReason.FILE_TRANSFER_THROUGHPUT_LOW,
      result_message=f'{low_throughput_info}. {low_throughput_tip}',
  )
  asserts.fail(low_throughput_info)


def _get_device_attributes(ad: android_device.AndroidDevice) -> str:
  return '\n'.join([
      f'serial: {ad.serial}',
      f'model: {ad.model}',
      f'android_version: {ad.android_version}\n'
      f'build_info: {ad.build_info}',
      f'gms_version: {setup_utils.dump_gms_version(ad)}',
      f'wifi_chipset: {ad.wifi_chipset}',
      f'wifi_fw: {ad.adb.getprop("vendor.wlan.firmware.version")}',
      f'support_5g: {ad.supports_5g}',
      f'support_dbs_sta_wfd: {ad.supports_dbs_sta_wfd}',
      (
          'enable_sta_dfs_channel_for_peer_network:'
          f' {ad.enable_sta_dfs_channel_for_peer_network}'
      ),
      (
          'enable_sta_indoor_channel_for_peer_network:'
          f' {ad.enable_sta_indoor_channel_for_peer_network}'
      ),
      f'max_num_streams: {ad.max_num_streams}',
      f'max_num_streams_dbs: {ad.max_num_streams_dbs}',
      f'max_phy_rate_5g_mbps: {ad.max_phy_rate_5g_mbps}',
      f'max_phy_rate_2g_mbps: {ad.max_phy_rate_2g_mbps}',
      f'support_aware: {setup_utils.is_wifi_aware_available(ad)}',
  ])


def _summarize_prior_connection_info(
    result: SingleTestResult,
) -> str:
  """Summarizes the prior connection info during a single test iteration."""
  if (
      result.prior_nc_fail_reason
      == nc_constants.SingleTestFailureReason.UNINITIALIZED
  ):
    return ''

  metrics = {
      'discovery_latency': _float_to_str(
          result.prior_nc_quality_info.discovery_latency.total_seconds(), 1
      ),
      'connection_latency': _float_to_str(
          result.prior_nc_quality_info.connection_latency.total_seconds(), 1
      ),
  }
  return '\n'.join([f'{key}: {value}' for key, value in metrics.items()])


def _summarize_transfer_quality_info(
    result: SingleTestResult,
) -> dict[str, str]:
  """Summarizes the transfer quality info during a single test iteration."""
  upgrade_medium = result.quality_info.upgrade_medium
  speed_mbps_fraction_bits = 3
  if upgrade_medium in [
      nc_constants.NearbyConnectionMedium.BLE,
      nc_constants.NearbyConnectionMedium.BLE_L2CAP,
      nc_constants.NearbyConnectionMedium.BLUETOOTH,
  ]:
    speed_mbps_fraction_bits = 1
  metrics = {
      'discovery_latency': _float_to_str(
          result.quality_info.discovery_latency.total_seconds(), 1
      ),
      'connection_latency': _float_to_str(
          result.quality_info.connection_latency.total_seconds(), 1
      ),
      'connection_medium': result.quality_info.get_connection_medium_name(),
      'upgrade_latency': _float_to_str(
          result.quality_info.medium_upgrade_latency.total_seconds(), 1
      ),
      'upgrade_medium': result.quality_info.get_medium_name(),
      'medium_frequency': str(result.quality_info.medium_frequency),
      'speed_mbps': _float_to_str(
          result.file_transfer_throughput_kbps / 1024, speed_mbps_fraction_bits
      ),
  }
  if result.iperf_throughput_kbps > 0:
    metrics['speed_mbps_iperf'] = _float_to_str(
        result.iperf_throughput_kbps / 1024, speed_mbps_fraction_bits
    )
  return metrics


def _summarize_station_connection_info(
    result: SingleTestResult,
) -> str:
  """Summarizes the station connection info during a single test iteration."""
  metrics = {}
  if result.discoverer_sta_latency is not nc_constants.UNSET_LATENCY:
    metrics['source'] = _float_to_str(
        result.discoverer_sta_latency.total_seconds(), 1
    )
  if result.advertiser_sta_latency is not nc_constants.UNSET_LATENCY:
    metrics['target'] = _float_to_str(
        result.advertiser_sta_latency.total_seconds(), 1
    )
  return '\n'.join([f'{key}: {value}s' for key, value in metrics.items()])


def gen_single_test_iter_report(
    result: SingleTestResult,
) -> dict[str, Any]:
  """Generates a test report for the given test results."""
  prior_connection_info = _summarize_prior_connection_info(result)
  if prior_connection_info:
    logging.info('prior connection info: %s', prior_connection_info)
  transfer_quality_info = _summarize_transfer_quality_info(result)
  logging.info('transfer quality info: %s', transfer_quality_info)
  return {
      'result': result.result_message,
      'prior_connection': prior_connection_info,
      'transfer_info': '\n'.join(
          [f'{k}: {v}' for k, v in transfer_quality_info.items()]
      ),
      'wlan_connection_latency': _summarize_station_connection_info(result),
      'debug_reference_info': '\n'.join(
          [f'{k}: {v}' for k, v in result.debug_reference_info.items()]
      ),
  }


@dataclasses.dataclass(frozen=False)
class SingleTestResult:
  """The test result of a single iteration."""

  test_iteration: int = 0
  prior_nc_fail_reason: nc_constants.SingleTestFailureReason = (
      nc_constants.SingleTestFailureReason.UNINITIALIZED
  )
  active_nc_fail_reason: nc_constants.SingleTestFailureReason = (
      nc_constants.SingleTestFailureReason.UNINITIALIZED
  )
  result_message: str = ''
  prior_nc_quality_info: nc_constants.ConnectionSetupQualityInfo = (
      dataclasses.field(default_factory=nc_constants.ConnectionSetupQualityInfo)
  )
  quality_info: nc_constants.ConnectionSetupQualityInfo = dataclasses.field(
      default_factory=nc_constants.ConnectionSetupQualityInfo
  )
  file_transfer_throughput_kbps: float = nc_constants.UNSET_THROUGHPUT_KBPS
  iperf_throughput_kbps: float = nc_constants.UNSET_THROUGHPUT_KBPS
  discoverer_sta_latency: datetime.timedelta = nc_constants.UNSET_LATENCY
  advertiser_sta_latency: datetime.timedelta = nc_constants.UNSET_LATENCY
  sta_frequency: int = nc_constants.INVALID_INT
  max_sta_link_speed_mbps: int = nc_constants.INVALID_INT
  start_time: datetime.datetime = datetime.datetime.now()
  end_time: datetime.datetime | None = None
  debug_reference_info: dict[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self):
    self.start_time = datetime.datetime.now()

  def end_test(self) -> None:
    self.end_time = datetime.datetime.now()

  @property
  def failure_reason(self) -> nc_constants.SingleTestFailureReason:
    if self.prior_nc_fail_reason not in (
        nc_constants.SingleTestFailureReason.UNINITIALIZED,
        nc_constants.SingleTestFailureReason.SUCCESS,
    ):
      return self.prior_nc_fail_reason
    return self.active_nc_fail_reason

  def add_debug_reference_info(
      self, key: str, value: Any
  ) -> None:
    """Adds debug reference info for the current test iteration."""
    self.debug_reference_info[key] = value

  def set_prior_nc_fail_reason(
      self,
      failure_reason: nc_constants.SingleTestFailureReason,
  ) -> None:
    """Sets fail reason related to establishing the prior NC."""
    self.prior_nc_fail_reason = failure_reason
    if failure_reason == nc_constants.SingleTestFailureReason.SUCCESS:
      return
    self.result_message = (
        f'FAIL (The prior BT connection): {failure_reason.name} - '
        f'{nc_constants.COMMON_TRIAGE_TIP.get(failure_reason)}'
    )

  def set_active_nc_fail_reason(
      self,
      failure_reason: nc_constants.SingleTestFailureReason,
      result_message: str | None = None,
  ) -> None:
    """Sets main fail reason and generates result message if not provided."""
    self.active_nc_fail_reason = failure_reason
    if failure_reason == nc_constants.SingleTestFailureReason.SUCCESS:
      self.result_message = result_message or 'PASS'
      return
    if result_message is None:
      result_message = nc_constants.COMMON_TRIAGE_TIP.get(failure_reason)
    result_message = f'{failure_reason.name} - {result_message}'
    self.result_message = result_message


def gen_basic_test_summary(
    discoverer: android_device.AndroidDevice,
    advertiser: android_device.AndroidDevice,
    test_result: str,
) -> collections.OrderedDict[str, str]:
  """Generates a basic test summary with the given test result."""
  basic_test_summary = collections.OrderedDict({
      'test_script_verion': version.TEST_SCRIPT_VERSION,
      'test_result': test_result,
      'device_source': _get_device_attributes(discoverer),
      'device_target': _get_device_attributes(advertiser),
      'target_build_id': f'{advertiser.build_info["build_id"]}',
      'target_model': f'{advertiser.model}',
      'target_gms_version': f'{setup_utils.dump_gms_version(advertiser)}',
      'target_wifi_chipset': f'{advertiser.wifi_chipset}',
  })
  if hasattr(advertiser, 'wifi_env_ssid_count'):
    basic_test_summary['wifi_ap_number'] = f'{advertiser.wifi_env_ssid_count}'
  return basic_test_summary


class PerformanceTestResults:
  """Records all test results of a performance test class."""

  # The test runtime object.
  nc_test_runtime: nc_constants.NcTestRuntime | None = None
  # Expected test iterations.
  test_iterations_expected: int = 1
  # Required success rate, Value range: 0 to 1
  success_rate_target: float = 1

  _results: Sequence[SingleTestResult]
  _start_time: datetime.datetime

  def __init__(self):
    self._results = []
    self._start_time = datetime.datetime.now()

  @property
  def current_test_result(self) -> SingleTestResult:
    """Returns the test result of the current test iteration."""
    if not self._results:
      raise ValueError('No test iteration was started.')
    return self._results[-1]

  def start_new_test_iteration(self) -> SingleTestResult:
    """Starts a new iteration and returns object for recording test result."""
    single_result = SingleTestResult()
    single_result.test_iteration = len(self._results)
    self._results.append(single_result)
    return single_result

  def end_test_iteration(self):
    """Ends the current test iteration."""
    self.current_test_result.end_test()

  def is_any_test_iter_executed(self) -> bool:
    """Returns True if `start_new_test_iteration` is called at least once."""
    return bool(self._results)

  def is_test_class_passed(self) -> bool:
    """Returns True if test iteration success rate meets the target."""
    finished_iteration_count = len(self._results)
    min_success_iterations_required = round(
        finished_iteration_count * self.success_rate_target, 2
    )
    actual_success_count = self._get_success_iteration_count()
    logging.info(
        'min_success_iterations_required: %s, actual_success_count: %s',
        min_success_iterations_required,
        actual_success_count,
    )
    return actual_success_count >= min_success_iterations_required

  def get_test_class_result_message(self) -> str:
    """Gets the test result message for the test class based on result enum."""
    finished_iteration_count = len(self._results)
    if finished_iteration_count == 0:
      return 'FAIL: Test did not execute any iterations. Zero finished tests.'
    if self.is_test_class_passed():
      return 'PASS'
    success_rate = (
        float(self._get_success_iteration_count()) / finished_iteration_count
    )
    logging.info('success rate: %.2f', success_rate)
    str_for_exit_early = ''
    if finished_iteration_count < self.test_iterations_expected:
      str_for_exit_early += (
          'Note: Test exited early, not all iterations are executed.'
      )
    return (
        f'FAIL: Low success rate: {success_rate:.2%} is'
        f' lower than the target {self.success_rate_target:.2%}. '
        f'{str_for_exit_early}'
    )

  def gen_test_summary(self) -> dict[str, Any]:
    """Summarizes test results of all iterations."""
    if (nc_test_runtime := self.nc_test_runtime) is None:
      raise ValueError('nc_test_runtime is None when generating test summary.')
    nc_test_runtime = typing.cast(nc_constants.NcTestRuntime, nc_test_runtime)
    advertiser = nc_test_runtime.advertiser
    discoverer = nc_test_runtime.discoverer

    test_class_result_message = self.get_test_class_result_message()

    test_summary = gen_basic_test_summary(
        discoverer, advertiser, test_class_result_message
    )
    test_stats = [
        f'start_time: {self._start_time}',
        f'end_time: {datetime.datetime.now()}',
        f'required_iterations: {self.test_iterations_expected}',
        f'finished_iterations: {len(self._results)}',
        f'failed_iterations: {self._get_failed_iteration_count()}',
        f'failed_iterations_detail:\n {self._get_failed_iteration_messages()}',
    ]
    test_summary.update({
        'test_config': self._get_test_runtime_info(nc_test_runtime),
        'test_stats': '\n'.join(test_stats),
        'file_transfer_stats': '\n'.join(
            self._get_file_transfer_stats(nc_test_runtime)
        ),
        'wifi_upgrade_stats': self._summary_upgraded_wifi_transfer_mediums(),
        'prior_bt_connection_stats': self._get_prior_bt_connection_stats(),
    })
    test_summary_with_index = {}
    for index, (k, v) in enumerate(test_summary.items()):
      test_summary_with_index[f'{index:02}_{k}'] = v
    return test_summary_with_index

  def _get_success_iteration_count(self) -> int:
    return sum(
        test_result.failure_reason
        is nc_constants.SingleTestFailureReason.SUCCESS
        for test_result in self._results
    )

  def _get_failed_iteration_count(self) -> int:
    return sum(
        test_result.failure_reason
        is not nc_constants.SingleTestFailureReason.SUCCESS
        for test_result in self._results
    )

  def _get_failed_iteration_messages(self) -> str:
    """Summarizes failed iterations with detailed reasons and signatures."""
    messages = []
    for result in self._results:
      if (
          result.failure_reason
          is not nc_constants.SingleTestFailureReason.SUCCESS
      ):
        messages.append(
            f'- Iter: {result.test_iteration}: {result.start_time}'
            f' {result.result_message}\n'
            f' sta freq: {result.sta_frequency},'
            f' sta max link speed: {result.max_sta_link_speed_mbps},'
            f' used medium: {result.quality_info.get_medium_name()},'
            f' medium freq: {result.quality_info.medium_frequency}.'
        )

    if messages:
      return '\n'.join(messages)
    else:
      return 'NA'

  def _get_file_transfer_stats(
      self, nc_test_runtime: nc_constants.NcTestRuntime
  ) -> list[str]:
    """Gets the file transfer connection stats for all iterations."""
    if not self._results:
      return []

    discovery_latency_stats = self._get_latency_stats(
        [result.quality_info.discovery_latency for result in self._results],
    )
    connection_latency_stats = self._get_latency_stats(
        [result.quality_info.connection_latency for result in self._results],
    )
    transfer_stats = self._get_transfer_stats(
        [result.file_transfer_throughput_kbps for result in self._results],
    )
    iperf_stats = self._get_transfer_stats(
        [result.iperf_throughput_kbps for result in self._results],
    )
    stats = [
        f'discovery_count: {discovery_latency_stats.success_count}',
        f'discovery_latency_min: {discovery_latency_stats.min_val}',
        f'discovery_latency_med: {discovery_latency_stats.median_val}',
        f'discovery_latency_max: {discovery_latency_stats.max_val}',
        f'connection_count: {connection_latency_stats.success_count}',
        f'connection_latency_min: {connection_latency_stats.min_val}',
        f'connection_latency_med: {connection_latency_stats.median_val}',
        f'connection_latency_max: {connection_latency_stats.max_val}',
        f'transfer_count: {transfer_stats.success_count}',
        f'speed_mbps_min: {transfer_stats.min_val}',
        f'speed_mbps_med: {transfer_stats.median_val}',
        f'speed_mbps_max: {transfer_stats.max_val}',
    ]

    if self.current_test_result.iperf_throughput_kbps > 0:
      stats.append(f'iperf_count: {iperf_stats.success_count}')
      stats.append(f'iperf_mbps_min: {iperf_stats.min_val}')
      stats.append(f'iperf_mbps_med: {iperf_stats.median_val}')
      stats.append(f'iperf_mbps_max: {iperf_stats.max_val}')

    if nc_constants.is_high_quality_medium(
        nc_test_runtime.upgrade_medium_under_test
    ):
      upgrade_latency_stats = self._get_latency_stats(
          [r.quality_info.medium_upgrade_latency for r in self._results],
      )
      stats.append(f'upgrade_count: {upgrade_latency_stats.success_count}')
      stats.append(
          f'instant_connection_count: {upgrade_latency_stats.zero_count}'
      )
      stats.append(f'upgrade_latency_min: {upgrade_latency_stats.min_val}')
      stats.append(f'upgrade_latency_med: {upgrade_latency_stats.median_val}')
      stats.append(f'upgrade_latency_max: {upgrade_latency_stats.max_val}')

    return stats

  def _get_test_runtime_info(
      self, nc_test_runtime: nc_constants.NcTestRuntime
  ) -> str:
    """Gets the test runtime info for this test class."""
    info = {
        'country_code': nc_test_runtime.country_code,
        'advertising_discovery_medium': (
            nc_test_runtime.advertising_discovery_medium.name
        ),
        'connection_medium': nc_test_runtime.connection_medium.name,
        'upgrade_medium': nc_test_runtime.upgrade_medium_under_test.name,
    }
    if (wifi_info := nc_test_runtime.wifi_info) is not None:
      # If the test could upgrade to either 2G or 5G WiFi mediums, do not show
      # below info in test summary.
      if nc_constants.is_upgrading_to_wifi_of_any_freq(wifi_info.d2d_type):
        info.update(
            {'is_2g_only': 'NA', 'is_dbs_mode': 'NA', 'is_mcc_mode': 'NA'}
        )
      else:
        info.update({
            'is_2g_only': wifi_info.is_2g_d2d_wifi_medium,
            'is_dbs_mode': nc_test_runtime.is_dbs_mode,
            'is_mcc_mode': wifi_info.is_mcc,
        })
      info.update({
          'discoverer_wifi_ssid': wifi_info.discoverer_wifi_ssid,
          'advertiser_wifi_ssid': wifi_info.advertiser_wifi_ssid,
      })
    return '\n'.join([f'{key}: {value}' for key, value in info.items()])

  def _summary_upgraded_wifi_transfer_mediums(self):
    """Summarizes the upgraded wifi transfer mediums."""
    upgrade_mediums = [
        result.quality_info.upgrade_medium.name
        for result in self._results
        if result.quality_info.upgrade_medium is not None
    ]
    if not upgrade_mediums:
      return 'NA'
    return '\n'.join(
        [f'{k}: {v}' for k, v in collections.Counter(upgrade_mediums).items()]
    )

  def _get_prior_bt_connection_stats(self) -> str:
    """Gets the prior BT connection performance stats for all iterations."""
    # No discovery latency means this test does not set up prior BT connection.
    filtered_results = [
        r
        for r in self._results
        if r.prior_nc_quality_info.discovery_latency
        != nc_constants.UNSET_LATENCY
    ]
    if not filtered_results:
      return 'NA'

    discovery_latency_stats = self._get_latency_stats(
        [r.prior_nc_quality_info.discovery_latency for r in filtered_results]
    )
    connection_latency_stats = self._get_latency_stats(
        [r.prior_nc_quality_info.connection_latency for r in filtered_results]
    )
    return '\n'.join([
        f'discovery_count: {discovery_latency_stats.success_count}',
        f'discovery_latency_min: {discovery_latency_stats.min_val:.2f}',
        f'discovery_latency_med: {discovery_latency_stats.median_val:.2f}',
        f'discovery_latency_max: {discovery_latency_stats.max_val:.2f}',
        f'connection_count: {connection_latency_stats.success_count}',
        f'connection_latency_min: {connection_latency_stats.min_val:.2f}',
        f'connection_latency_med: {connection_latency_stats.median_val:.2f}',
        f'connection_latency_max: {connection_latency_stats.max_val:.2f}',
    ])

  def _get_latency_stats(
      self, latency_indicators: list[datetime.timedelta]
  ) -> nc_constants.TestResultStats:
    """Gets the latency stats for all iterations."""
    filtered = [
        latency.total_seconds()
        for latency in latency_indicators
        if latency != nc_constants.UNSET_LATENCY
    ]
    filtered_int = [round(latency) for latency in filtered]
    if not filtered:
      # All test cases are failed.
      return nc_constants.TestResultStats(0, 0, 0, 0, 0)

    filtered.sort()

    percentile_50 = round(
        filtered[int(len(filtered) * nc_constants.PERCENTILE_50_FACTOR)],
        nc_constants.LATENCY_PRECISION_DIGITS,
    )
    return nc_constants.TestResultStats(
        len(filtered),
        filtered_int.count(0),
        round(filtered[0], nc_constants.LATENCY_PRECISION_DIGITS),
        percentile_50,
        round(
            filtered[len(filtered) - 1], nc_constants.LATENCY_PRECISION_DIGITS
        ),
    )

  def _get_transfer_stats(
      self,
      throughput_indicators: list[float],
  ) -> nc_constants.TestResultStats:
    """Get transfer stats.

    The stats include the min, median and max throughput in MB/s from
    iterations which finished file transfer.

    Args:
      throughput_indicators: a list of speed test report in KB/s.

    Returns:
      An instance of TestResultStats.
    """
    filtered = [
        x
        for x in throughput_indicators
        if x != nc_constants.UNSET_THROUGHPUT_KBPS
    ]
    if not filtered:
      # all test cases are failed
      return nc_constants.TestResultStats(0, 0, 0, 0, 0)
    # use the descenting order of the throughput
    filtered.sort(reverse=True)
    return nc_constants.TestResultStats(
        len(filtered),
        0,
        _convert_kbps_to_mbps(filtered[len(filtered) - 1]),
        _convert_kbps_to_mbps(
            filtered[int(len(filtered) * nc_constants.PERCENTILE_50_FACTOR)]
        ),
        _convert_kbps_to_mbps(filtered[0]),
    )
