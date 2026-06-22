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

"""Utilities for handling Nearby Connection test results."""

from __future__ import annotations

from collections.abc import Sequence
import logging

from mobly import asserts
from mobly.controllers import android_device

from betocq import constants
from betocq import iperf_utils
from betocq import setup_utils
from betocq.metrics import metrics_base

MetricsCollector = metrics_base.MetricsCollector
_BITS_PER_BYTE = 8


def _convert_kbps_to_mbps(throughput_kbps: float) -> float:
  """Converts throughput from kbyte/s to mbyte/s."""
  return round(throughput_kbps / 1024, 1)


def set_prior_nc_fail_reason(
    metrics: MetricsCollector,
    failure_reason: constants.SingleTestFailureReason,
) -> None:
  """Sets fail reason related to establishing the prior NC."""
  metrics.record('prior_nc_fail_reason', failure_reason)
  if failure_reason == constants.SingleTestFailureReason.SUCCESS:
    return
  result_message = (
      f'FAIL (The prior BT connection): {failure_reason.name} - '
      f'{constants.COMMON_TRIAGE_TIP.get(failure_reason)}'
  )
  metrics.record('result_message', result_message)


def set_active_nc_fail_reason(
    metrics: MetricsCollector,
    failure_reason: constants.SingleTestFailureReason,
    result_message: str | None = None,
) -> None:
  """Sets main fail reason and generates result message if not provided."""
  metrics.record('active_nc_fail_reason', failure_reason)
  if failure_reason == constants.SingleTestFailureReason.SUCCESS:
    metrics.record('result_message', result_message or 'PASS')
    return
  if result_message is None:
    result_message = constants.COMMON_TRIAGE_TIP.get(failure_reason)
  result_message = f'{failure_reason.name} - {result_message}'
  metrics.record('result_message', result_message)


def set_and_assert_p2p_frequency(
    ad: android_device.AndroidDevice,
    metrics: MetricsCollector,
    *,
    is_mcc: bool,
    is_dbs_mode: bool,
    sta_frequency: int,
    additional_error_message: str = '',
) -> None:
  """Asserts the p2p frequency is expected."""
  p2p_frequency = setup_utils.get_wifi_p2p_frequency(ad)
  metrics.record('medium_frequency', p2p_frequency)
  if (
      p2p_frequency == constants.INVALID_INT
      or sta_frequency == constants.INVALID_INT
  ):
    ad.log.warning(
        'The P2P frequency (%s) or STA frequency (%s) is not available, the'
        ' test result may not be expected.',
        p2p_frequency,
        sta_frequency,
    )
    return

  # Check for MCC.
  if is_mcc:
    if p2p_frequency != sta_frequency:
      return
    set_active_nc_fail_reason(
        metrics, constants.SingleTestFailureReason.WRONG_P2P_FREQUENCY
    )
    asserts.fail(
        f'P2P frequency ({p2p_frequency}) is same as STA frequency'
        f' ({sta_frequency}) in MCC test case. {additional_error_message}'
    )

  # Check for SCC.
  if (not is_dbs_mode) and (p2p_frequency != sta_frequency):
    set_active_nc_fail_reason(
        metrics, constants.SingleTestFailureReason.WRONG_P2P_FREQUENCY
    )
    asserts.fail(
        f'P2P frequency ({p2p_frequency}) is different from STA frequency'
        f' ({sta_frequency}) in SCC test case. {additional_error_message}'
    )
  if is_dbs_mode and p2p_frequency == sta_frequency:
    set_active_nc_fail_reason(
        metrics, constants.SingleTestFailureReason.WRONG_P2P_FREQUENCY
    )
    asserts.fail(
        f'P2P frequency ({p2p_frequency}) is the same as STA frequency'
        f' ({sta_frequency}) in SCC+DBS test case. {additional_error_message}'
    )


def populate_medium_frequency(
    target_ad: android_device.AndroidDevice,
    metrics: MetricsCollector,
) -> None:
  """Sets the medium frequency for the test result."""
  metrics.record(
      'medium_frequency', setup_utils.get_wifi_p2p_frequency(target_ad)
  )


def set_and_assert_concurrency_mode(
    current_concurrency_mode: constants.WifiConcurrencyMode,
    valid_concurrency_modes: Sequence[constants.WifiConcurrencyMode],
    metrics: MetricsCollector,
    additional_error_message: str = '',
) -> None:
  """Sets the concurrency mode for the test result."""
  metrics.record(
      'wifi_concurrency_mode',
      current_concurrency_mode,
  )
  if current_concurrency_mode not in valid_concurrency_modes:
    set_active_nc_fail_reason(
        metrics, constants.SingleTestFailureReason.INVALID_WIFI_CONCURRENCY_MODE
    )
    asserts.fail(
        f'Concurrency mode: {current_concurrency_mode} is not expected.'
        f' {additional_error_message}'
    )


def collect_nc_test_metrics(
    metrics: MetricsCollector,
    nc_test_runtime: constants.NcTestRuntime,
) -> None:
  """Collects general test metrics for nearby connection tests."""
  advertiser = nc_test_runtime.advertiser
  sta_frequency, max_link_speed_mbps = (
      setup_utils.get_target_sta_frequency_and_max_link_speed(advertiser)
  )
  metrics.record('advertiser_sta_frequency', sta_frequency)
  metrics.record('advertiser_max_sta_link_speed_mbps', max_link_speed_mbps)

  if nc_test_runtime.upgrade_medium_under_test.to_connection_medium() in [
      constants.NearbyConnectionMedium.WIFI_DIRECT,
      constants.NearbyConnectionMedium.WIFI_HOTSPOT,
  ]:
    metrics.record(
        'medium_frequency', setup_utils.get_wifi_p2p_frequency(advertiser)
    )


def assert_sta_frequency(
    metrics: MetricsCollector,
    expected_wifi_type: constants.WifiType,
) -> None:
  """Asserts the STA frequency is expected."""
  sta_frequency_metric = metrics.get('advertiser_sta_frequency')
  sta_frequency = (
      sta_frequency_metric.value
      if sta_frequency_metric
      else constants.INVALID_INT
  )
  # Check whether the device is still connected to the AP.
  if sta_frequency == constants.INVALID_INT:
    set_active_nc_fail_reason(
        metrics, constants.SingleTestFailureReason.DISCONNECTED_FROM_AP
    )
    asserts.fail('Target device is disconnected from AP. Check AP DHCP config.')

  # Check whether the STA frequency is expected.
  match expected_wifi_type:
    case constants.WifiType.FREQ_2G:
      is_valid_freq = setup_utils.is_valid_wifi_2g_freq(sta_frequency)
    case constants.WifiType.FREQ_5G:
      is_valid_freq = setup_utils.is_valid_wifi_5g_freq(sta_frequency)
    case constants.WifiType.FREQ_5G_DFS:
      is_valid_freq = setup_utils.is_valid_wifi_5g_dfs_freq(sta_frequency)
    case _:
      is_valid_freq = False

  if is_valid_freq:
    return

  set_active_nc_fail_reason(
      metrics, constants.SingleTestFailureReason.WRONG_AP_FREQUENCY
  )
  asserts.fail(f'AP is set to a wrong frequency {sta_frequency}')


def set_and_assert_sta_frequency(
    ad: android_device.AndroidDevice,
    metrics: MetricsCollector,
    expected_wifi_type: constants.WifiType,
    prefix: str,
) -> None:
  """Asserts the STA frequency is expected."""

  connection_info = ad.nearby.wifiGetConnectionInfo()
  sta_frequency, max_link_speed_mbps = (
      setup_utils.get_sta_frequency_and_max_link_speed(ad, connection_info)
  )
  metrics.record(f'{prefix}sta_frequency', sta_frequency)
  metrics.record(f'{prefix}max_sta_link_speed_mbps', max_link_speed_mbps)

  if sta_frequency == constants.INVALID_INT:
    ad.log.warning(
        'The STA frequency is not available, connection_info: %s, the test may'
        ' not be expected.',
        connection_info,
    )
    if (
        connection_info.get('SupplicantState', '')
        != constants.WIFI_SUPPLICANT_STATE_COMPLETED
    ):
      if ad.role == 'target':
        fail_reason = constants.SingleTestFailureReason.TARGET_WIFI_CONNECTION
      else:
        fail_reason = constants.SingleTestFailureReason.SOURCE_WIFI_CONNECTION
      set_active_nc_fail_reason(metrics, fail_reason)
      asserts.fail(constants.COMMON_TRIAGE_TIP[fail_reason])
    ad.log.warning(
        'The STA frequency is not available, but the STA is connected, the test'
        ' result may not be expected.'
    )
    return

  additional_error_message = ''
  # Check whether the STA frequency is expected.
  match expected_wifi_type:
    case constants.WifiType.FREQ_2G:
      is_valid_freq = setup_utils.is_valid_wifi_2g_freq(sta_frequency)
      if not is_valid_freq:
        additional_error_message = (
            ' The channel is expected to be a 2G channel.'
        )
    case constants.WifiType.FREQ_5G:
      is_valid_freq = setup_utils.is_valid_wifi_5g_freq(sta_frequency)
      if not is_valid_freq:
        additional_error_message = (
            ' The channel is expected to be a 5G channel.'
        )
    case constants.WifiType.FREQ_5G_DFS:
      is_valid_freq = setup_utils.is_valid_wifi_5g_dfs_freq(sta_frequency)
      if not is_valid_freq:
        additional_error_message = (
            ' The channel is expected to be a 5G DFS channel. If the test is'
            ' not in a shield box or room, the DFS channel may be changed by'
            ' the AP due to radar signals detected, reset the AP to a DFS'
            ' channel and run the test in a shield box or room to avoid such an'
            ' issue in the future.'
        )
    case _:
      is_valid_freq = False

  if not is_valid_freq:
    set_active_nc_fail_reason(
        metrics, constants.SingleTestFailureReason.WRONG_AP_FREQUENCY
    )
    # The correct frequency is critical
    asserts.abort_all(
        f'AP is set to a wrong frequency {sta_frequency}, check the AP'
        f' configuration and the test configuration.{additional_error_message}'
    )


def assert_2g_wifi_throughput_and_run_iperf_if_needed(
    metrics: MetricsCollector,
    nc_test_runtime: constants.NcTestRuntime,
    low_throughput_tip: str,
    did_nc_file_transfer: bool = True,
) -> None:
  """Checks the throughput for 2G WiFi medium and runs iperf test if needed."""
  speed_target = _get_2g_wifi_throughput_benchmark(
      metrics=metrics,
      nc_test_runtime=nc_test_runtime,
  )
  logging.info('speed target: %s', speed_target)
  assert_throughput_and_run_iperf_if_needed(
      metrics,
      nc_test_runtime,
      speed_target,
      low_throughput_tip,
      did_nc_file_transfer,
  )


def assert_2g_wifi_throughput(
    metrics: MetricsCollector,
    nc_test_runtime: constants.NcTestRuntime,
    low_throughput_tip: str,
) -> None:
  """Checks the throughput for 2G WiFi medium."""
  speed_target = _get_2g_wifi_throughput_benchmark(
      metrics=metrics,
      nc_test_runtime=nc_test_runtime,
  )
  logging.info('speed target: %s', speed_target)
  assert_throughput(
      metrics,
      speed_target,
      low_throughput_tip,
  )


def _get_2g_wifi_throughput_benchmark(
    metrics: MetricsCollector,
    nc_test_runtime: constants.NcTestRuntime,
) -> constants.SpeedTarget:
  """Gets the throughput benchmark as MBps."""
  discoverer = nc_test_runtime.discoverer
  advertiser = nc_test_runtime.advertiser
  if nc_test_runtime.wifi_info is None:
    return constants.SpeedTarget(constants.INVALID_INT, constants.INVALID_INT)

  max_num_streams = min(discoverer.max_num_streams, advertiser.max_num_streams)

  max_phy_rate_mbps = min(
      discoverer.max_phy_rate_2g_mbps,
      advertiser.max_phy_rate_2g_mbps,
  )
  max_phy_rate_mbps = min(
      max_phy_rate_mbps,
      max_num_streams * constants.MAX_PHY_RATE_PER_STREAM_N_20_MBPS,
  )
  min_throughput_mbyte_per_sec = int(
      max_phy_rate_mbps
      * constants.MAX_PHY_RATE_TO_MIN_THROUGHPUT_RATIO_2G
      / _BITS_PER_BYTE
  )
  nc_min_throughput_mbyte_per_sec = min_throughput_mbyte_per_sec

  sta_freq_metric = metrics.get('advertiser_sta_frequency')
  sta_frequency = (
      sta_freq_metric.value if sta_freq_metric else constants.INVALID_INT
  )
  max_sta_speed_metric = metrics.get('advertiser_max_sta_link_speed_mbps')
  max_sta_speed = (
      max_sta_speed_metric.value
      if max_sta_speed_metric
      else constants.INVALID_INT
  )

  nc_test_runtime.advertiser.log.info(
      'target STA freq = %d, max STA speed (Mb/s): %d, max D2D speed (MB/s):'
      ' %.2f, iperf min throughput (MB/s): %.2f, nc min throughput (MB/s):'
      ' %.2f',
      sta_frequency,
      max_sta_speed,
      max_phy_rate_mbps / _BITS_PER_BYTE,
      min_throughput_mbyte_per_sec,
      nc_min_throughput_mbyte_per_sec,
  )

  return constants.SpeedTarget(
      min_throughput_mbyte_per_sec, nc_min_throughput_mbyte_per_sec
  )


def assert_5g_wifi_throughput_and_run_iperf_if_needed(
    metrics: MetricsCollector,
    nc_test_runtime: constants.NcTestRuntime,
    low_throughput_tip: str,
    did_nc_file_transfer: bool = True,
    is_tdls_enabled: bool = True,
) -> None:
  """Checks the throughput for 5G WiFi medium and runs iperf test if needed."""
  speed_target = _get_5g_wifi_throughput_benchmark(
      metrics=metrics,
      nc_test_runtime=nc_test_runtime,
      is_tdls_enabled=is_tdls_enabled,
  )
  logging.info('speed target: %s', speed_target)
  assert_throughput_and_run_iperf_if_needed(
      metrics,
      nc_test_runtime,
      speed_target,
      low_throughput_tip,
      did_nc_file_transfer,
  )


def assert_5g_wifi_throughput(
    metrics: MetricsCollector,
    nc_test_runtime: constants.NcTestRuntime,
    low_throughput_tip: str,
    is_tdls_enabled: bool = True,
) -> None:
  """Checks the throughput for 5G medium."""
  speed_target = _get_5g_wifi_throughput_benchmark(
      metrics=metrics,
      nc_test_runtime=nc_test_runtime,
      is_tdls_enabled=is_tdls_enabled,
  )
  logging.info('speed target: %s', speed_target)
  assert_throughput(
      metrics,
      speed_target,
      low_throughput_tip,
  )


def _get_5g_wifi_throughput_benchmark(
    metrics: MetricsCollector,
    nc_test_runtime: constants.NcTestRuntime,
    is_tdls_enabled: bool = True,
) -> constants.SpeedTarget:
  """Gets the throughput benchmark as MBps."""
  discoverer = nc_test_runtime.discoverer
  advertiser = nc_test_runtime.advertiser
  if nc_test_runtime.wifi_info is None:
    return constants.SpeedTarget(constants.INVALID_INT, constants.INVALID_INT)
  is_mcc = nc_test_runtime.wifi_info.is_mcc
  is_dbs_mode = nc_test_runtime.is_dbs_mode
  is_wlan_medium = (
      nc_test_runtime.upgrade_medium_under_test
      == constants.NearbyMedium.WIFILAN_ONLY
  )
  is_wifi_hotspot_medium = (
      nc_test_runtime.upgrade_medium_under_test
      == constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT
  )
  is_tdls_supported = (
      nc_test_runtime.advertiser.nearby.wifiIsTdlsSupported()
      and nc_test_runtime.discoverer.nearby.wifiIsTdlsSupported()
  )

  # Step 1. Calculate max_phy_rate_mbps.
  max_num_streams = _get_max_num_streams(discoverer, advertiser, is_dbs_mode)
  is_ap_bandwidth_less_than_80mhz = _is_5g_ap_bandwidth_less_than_80mhz(
      metrics=metrics, max_num_streams=max_num_streams
  )

  if is_ap_bandwidth_less_than_80mhz:
    max_phy_rate_mbps = min(
        discoverer.max_phy_rate_5g_mbps,
        advertiser.max_phy_rate_5g_mbps,
        max_num_streams * constants.MAX_PHY_RATE_PER_STREAM_AC_40_MBPS,
    )
  else:
    max_phy_rate_mbps = min(
        discoverer.max_phy_rate_5g_mbps,
        advertiser.max_phy_rate_5g_mbps,
        max_num_streams * constants.MAX_PHY_RATE_PER_STREAM_AC_80_MBPS,
    )

  # Step 2. Calculate min_throughput_mbyte_per_sec.
  min_throughput_mbyte_per_sec = int(
      max_phy_rate_mbps
      * constants.MAX_PHY_RATE_TO_MIN_THROUGHPUT_RATIO_5G
      / _BITS_PER_BYTE
  )

  # Step 3. Adjust min_throughput_mbyte_per_sec according to medium info.
  if is_mcc:
    min_throughput_mbyte_per_sec = int(
        min_throughput_mbyte_per_sec * constants.MCC_THROUGHPUT_MULTIPLIER
    )
    # MCC hotspot has even lower throughput due to sync issue with STA.
    if is_wifi_hotspot_medium:
      min_throughput_mbyte_per_sec = (
          min_throughput_mbyte_per_sec
          * constants.MCC_HOTSPOT_THROUGHPUT_MULTIPLIER
      )

  # Cut the speed target by half if TDLS is not supported.
  if is_wlan_medium and (not is_tdls_supported or not is_tdls_enabled):
    min_throughput_mbyte_per_sec /= 2.0

  # Step 4. Calculate nc_min_throughput_mbyte_per_sec.
  iperf_to_nc_throughput_ratio = nc_test_runtime.iperf_to_d2d_throughput_ratio
  nc_min_throughput_mbyte_per_sec = (
      min_throughput_mbyte_per_sec * iperf_to_nc_throughput_ratio
  )
  # Limit NC min throughput due to encryption overhead
  if is_wlan_medium:
    nc_min_throughput_mbyte_per_sec = min(
        nc_min_throughput_mbyte_per_sec,
        nc_test_runtime.wlan_throughput_cap_mbps,
    )

  sta_freq_metric = metrics.get('advertiser_sta_frequency')
  sta_frequency = (
      sta_freq_metric.value if sta_freq_metric else constants.INVALID_INT
  )
  max_sta_speed_metric = metrics.get('advertiser_max_sta_link_speed_mbps')
  max_sta_speed = (
      max_sta_speed_metric.value
      if max_sta_speed_metric
      else constants.INVALID_INT
  )

  nc_test_runtime.advertiser.log.info(
      'target STA freq = %d, max STA speed (Mb/s): %d, max D2D speed (MB/s):'
      ' %.2f, iperf min throughput (MB/s): %.2f, nc min throughput (MB/s):'
      ' %.2f',
      sta_frequency,
      max_sta_speed,
      max_phy_rate_mbps / _BITS_PER_BYTE,
      min_throughput_mbyte_per_sec,
      nc_min_throughput_mbyte_per_sec,
  )

  return constants.SpeedTarget(
      min_throughput_mbyte_per_sec, nc_min_throughput_mbyte_per_sec
  )


def _get_max_num_streams(
    discoverer: android_device.AndroidDevice,
    advertiser: android_device.AndroidDevice,
    is_dbs_mode: bool,
) -> int:
  """Gets the max num streams."""
  if is_dbs_mode:
    return advertiser.max_num_streams_dbs
  else:
    return min(discoverer.max_num_streams, advertiser.max_num_streams)


def _is_5g_ap_bandwidth_less_than_80mhz(
    metrics: MetricsCollector,
    max_num_streams: int,
) -> bool:
  """Returns whether the 5G AP bandwidth is less than 80mhz."""
  max_phy_rate_ac80 = (
      max_num_streams * constants.MAX_PHY_RATE_PER_STREAM_AC_80_MBPS
  )
  sta_freq_metric = metrics.get('advertiser_sta_frequency')
  sta_frequency = (
      sta_freq_metric.value if sta_freq_metric else constants.INVALID_INT
  )
  max_sta_speed_metric = metrics.get('advertiser_max_sta_link_speed_mbps')
  max_sta_speed = (
      max_sta_speed_metric.value
      if max_sta_speed_metric
      else constants.INVALID_INT
  )

  return (
      sta_frequency > 5000
      and max_sta_speed > 0
      and max_sta_speed < max_phy_rate_ac80
  )


def assert_throughput(
    metrics: MetricsCollector,
    speed_target: constants.SpeedTarget,
    low_throughput_tip: str,
) -> None:
  """Checks the file transfer throughput."""
  nc_speed_min_mbps = speed_target.nc_speed_mbtye_per_sec
  metrics.record('speed_target', speed_target)

  throughput_metric = metrics.get('file_transfer_throughput_kbps')
  throughput = throughput_metric.value if throughput_metric else 0.0
  nc_speed_mbps = round(throughput / 1024, 3)

  if nc_speed_mbps >= nc_speed_min_mbps:
    return

  low_throughput_info = (
      f'file speed {nc_speed_mbps} < target {nc_speed_min_mbps} MB/s'
  )

  set_active_nc_fail_reason(
      metrics,
      constants.SingleTestFailureReason.FILE_TRANSFER_THROUGHPUT_LOW,
      result_message=f'{low_throughput_info}. {low_throughput_tip}',
  )
  asserts.fail(low_throughput_info)


def assert_throughput_and_run_iperf_if_needed(
    metrics: MetricsCollector,
    nc_test_runtime: constants.NcTestRuntime,
    speed_target: constants.SpeedTarget,
    low_throughput_tip: str,
    did_nc_file_transfer: bool = True,
) -> None:
  """Checks the file transfer throughput and runs iperf test if needed."""
  upgrade_medium_under_test = nc_test_runtime.upgrade_medium_under_test

  nc_speed_min_mbps = speed_target.nc_speed_mbtye_per_sec
  metrics.record('speed_target', speed_target)
  iperf_speed_min_mbps = speed_target.iperf_speed_mbtye_per_sec

  throughput_metric = metrics.get('file_transfer_throughput_kbps')
  throughput = throughput_metric.value if throughput_metric else 0.0
  nc_speed_mbps = round(throughput / 1024, 3)
  iperf_speed_mbps = 0.0

  if (
      nc_speed_mbps < nc_speed_min_mbps
      or upgrade_medium_under_test == constants.NearbyMedium.WIFILAN_ONLY
  ):
    iperf_speed_mbps = _run_iperf_test(
        metrics,
        nc_test_runtime,
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
    logging.warning(
        'iperf speed %s < target %s MB/s, but NC speed passed.',
        iperf_speed_mbps,
        iperf_speed_min_mbps,
    )
    low_throughput_info = None

  if low_throughput_info is None:
    return

  set_active_nc_fail_reason(
      metrics,
      constants.SingleTestFailureReason.FILE_TRANSFER_THROUGHPUT_LOW,
      result_message=f'{low_throughput_info}. {low_throughput_tip}',
  )
  asserts.fail(low_throughput_info)


def _run_iperf_test(
    metrics: MetricsCollector,
    nc_test_runtime: constants.NcTestRuntime,
) -> float:
  """Runs iperf test and returns the throughput. Returns 0 if not needed."""
  wifi_info = nc_test_runtime.wifi_info
  if wifi_info is None or wifi_info.is_mcc:
    return 0
  upgrade_medium_under_test = nc_test_runtime.upgrade_medium_under_test
  if upgrade_medium_under_test not in [
      constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT,
      constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT,
      constants.NearbyMedium.WIFILAN_ONLY,
      constants.NearbyMedium.WIFIAWARE_ONLY,
  ]:
    return 0
  advertiser = nc_test_runtime.advertiser
  discoverer = nc_test_runtime.discoverer
  is_discoverer_network_owner = nc_test_runtime.is_discoverer_network_owner

  upgrade_medium_val = metrics.get('upgrade_medium')
  upgrade_medium = None
  if upgrade_medium_val:
    upgrade_medium = upgrade_medium_val.value
  if not upgrade_medium:
    upgrade_medium = upgrade_medium_under_test.to_connection_medium()

  iperf_throughput = iperf_utils.run_iperf_test(
      ad_network_client=(
          advertiser if is_discoverer_network_owner else discoverer
      ),
      ad_network_owner=(
          discoverer if is_discoverer_network_owner else advertiser
      ),
      medium=upgrade_medium,
  )
  metrics.record('iperf_throughput_kbps', iperf_throughput)
  logging.info('iperf throughput: %d (KB/s)', iperf_throughput)
  return round(iperf_throughput / 1024, 1)


def assert_nc_throughput_meets_target(
    metrics: MetricsCollector,
    nc_speed_min_mbps: float,
    low_throughput_tip: str,
) -> None:
  """Checks the Nearby connection throughput meets the target."""
  metrics.record(
      'speed_target',
      constants.SpeedTarget(
          nc_speed_mbtye_per_sec=nc_speed_min_mbps,
          iperf_speed_mbtye_per_sec=constants.INVALID_INT,
      ),
  )
  throughput_metric = metrics.get('file_transfer_throughput_kbps')
  throughput = throughput_metric.value if throughput_metric else 0.0
  nc_speed_mbps = round(throughput / 1024, 3)
  if nc_speed_mbps >= nc_speed_min_mbps:
    return

  low_throughput_info = (
      f'file speed {nc_speed_mbps} < target {nc_speed_min_mbps} MB/s'
  )
  set_active_nc_fail_reason(
      metrics,
      constants.SingleTestFailureReason.FILE_TRANSFER_THROUGHPUT_LOW,
      result_message=f'{low_throughput_info}. {low_throughput_tip}',
  )
  asserts.fail(low_throughput_info)
