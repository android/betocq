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

"""Custom Mobly group formatters for Nearby Connection metrics."""

from __future__ import annotations

from collections.abc import Mapping
import datetime
from typing import Any

from betocq.metrics import formatters
from betocq.metrics import metrics_base

MetricsManager = metrics_base.MetricsManager
MoblyGroupFormatter = formatters.MoblyGroupFormatter


class NcFileTransferStatsFormatter(MoblyGroupFormatter):
  """Formats file transfer statistics into a complex multi-line string."""

  def format_group(
      self,
      group_name: str,
      group_data: Mapping[str, Any],
      manager: MetricsManager,
      scenario_name: str = '',
  ) -> Mapping[str, Any]:
    disc = group_data.get(
        'discovery_latency', {'count': 0, 'min': 0.0, 'median': 0.0, 'max': 0.0}
    )
    conn = group_data.get(
        'connection_latency',
        {'count': 0, 'min': 0.0, 'median': 0.0, 'max': 0.0},
    )
    transfer = group_data.get(
        'file_transfer_throughput_kbps',
        {'count': 0, 'min': 0.0, 'median': 0.0, 'max': 0.0},
    )
    iperf = group_data.get(
        'iperf_throughput_kbps',
        {'count': 0, 'min': 0.0, 'median': 0.0, 'max': 0.0},
    )
    upgrade = group_data.get(
        'upgrade_latency', {'count': 0, 'min': 0.0, 'median': 0.0, 'max': 0.0}
    )

    benchmark_nc_speed_mbps = 'NA'
    benchmark_iperf_speed_mbps = 'NA'

    # Try scenario group data first, fallback to class metrics
    target = group_data.get('speed_target')
    if not target:
      speed_target_metric = manager.class_metrics.get('speed_target')
      if speed_target_metric and speed_target_metric.value:
        target = speed_target_metric.value

    if target:
      if (
          hasattr(target, 'nc_speed_mbtye_per_sec')
          and target.nc_speed_mbtye_per_sec > 0
      ):
        benchmark_nc_speed_mbps = target.nc_speed_mbtye_per_sec
        benchmark_iperf_speed_mbps = target.iperf_speed_mbtye_per_sec

    def to_sec(v: Any) -> float | str:
      if isinstance(v, datetime.timedelta):
        return round(v.total_seconds(), 2)
      if isinstance(v, (int, float)):
        return round(float(v), 2)
      return v

    def to_mb(v: Any) -> float | str:
      if isinstance(v, (int, float)) and v > 0:
        return round(v / 1024, 1)
      return v

    stats = [
        f"discovery_count: {disc.get('count')}",
        f"discovery_latency_min: {to_sec(disc.get('min'))}",
        f"discovery_latency_med: {to_sec(disc.get('median'))}",
        f"discovery_latency_max: {to_sec(disc.get('max'))}",
        f"connection_count: {conn.get('count')}",
        f"connection_latency_min: {to_sec(conn.get('min'))}",
        f"connection_latency_med: {to_sec(conn.get('median'))}",
        f"connection_latency_max: {to_sec(conn.get('max'))}",
        f"transfer_count: {transfer.get('count')}",
        f"speed_mbps_min: {to_mb(transfer.get('min'))}",
        f"speed_mbps_med: {to_mb(transfer.get('median'))}",
        f"speed_mbps_max: {to_mb(transfer.get('max'))}",
        f'benchmark_nc_speed_mbps: {benchmark_nc_speed_mbps}',
        f'benchmark_iperf_speed_mbps: {benchmark_iperf_speed_mbps}',
    ]

    if iperf.get('count', 0) > 0:
      stats.extend([
          f"iperf_count: {iperf.get('count')}",
          f"iperf_mbps_min: {to_mb(iperf.get('min'))}",
          f"iperf_mbps_med: {to_mb(iperf.get('median'))}",
          f"iperf_mbps_max: {to_mb(iperf.get('max'))}",
      ])

    if upgrade.get('count', 0) > 0:
      zero_count = 0
      if scenario_name:
        scenario_collectors = (
            col
            for col in manager.iteration_collectors
            if col.scenario_name == scenario_name
        )
      else:
        scenario_collectors = manager.iteration_collectors
      for col in scenario_collectors:
        m = col.get('upgrade_latency')
        if m and m.value == datetime.timedelta(0):
          zero_count += 1

      stats.extend([
          f"upgrade_count: {upgrade.get('count')}",
          f'instant_connection_count: {zero_count}',
          f"upgrade_latency_min: {to_sec(upgrade.get('min'))}",
          f"upgrade_latency_med: {to_sec(upgrade.get('median'))}",
          f"upgrade_latency_max: {to_sec(upgrade.get('max'))}",
      ])

    return {'file_transfer_stats': '\n'.join(stats)}
