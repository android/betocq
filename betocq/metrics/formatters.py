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

"""Metrics formatters for BeToCQ."""

from __future__ import annotations

import collections
from collections import abc
from collections.abc import Mapping, Sequence
import contextlib
import datetime
import json
import logging
import os
import time
from typing import Any

import yaml

from betocq.metrics import aggregators
from betocq.metrics import metrics_base


try:
  import fcntl  # pylint: disable=g-import-not-at-top
except ImportError:
  logging.info('fcntl is not available on this platform.')
  pass

try:
  import msvcrt  # pylint: disable=g-import-not-at-top
except ImportError:
  logging.info('msvcrt is not available on this platform.')
  pass


MetricsManager = metrics_base.MetricsManager
MetricsCollector = metrics_base.MetricsCollector
Metric = metrics_base.Metric


def sanitize_for_mobly(val: Any) -> Any:
  """Sanitizes a value to make it safe for Mobly/YAML serialization."""
  if val is None:
    return None
  if hasattr(val, 'name'):
    return val.name
  if isinstance(val, (int, float, str, bool)):
    return val
  if isinstance(val, datetime.datetime):
    return val.isoformat()
  if isinstance(val, datetime.timedelta):
    return round(val.total_seconds(), 2)
  if isinstance(val, dict):
    return {k: sanitize_for_mobly(v) for k, v in val.items()}
  if isinstance(val, (list, tuple, set)):
    return [sanitize_for_mobly(x) for x in val]
  return str(val)


def _get_base_scenario_name(name: str) -> str:
  """Strips trailing repeated indices (e.g. '_0') from a scenario name."""
  if name is None:
    return ''
  parts = name.rsplit('_', 1)
  if len(parts) > 1 and parts[-1].isdigit():
    return parts[0]
  return name


class CrossPlatformFileLock:
  """Atomic file locking supported across Linux, Mac, and Windows."""

  def __init__(self, file_path: str, timeout_sec: int = 10) -> None:
    """Initializes the instance."""
    self.lockfile = file_path + '.lock'
    self.timeout_sec = timeout_sec
    self.fd = None

  def __enter__(self) -> CrossPlatformFileLock:
    start_time = time.time()
    while True:
      try:
        if self.fd is None:
          self.fd = open(self.lockfile, 'a')
        if os.name == 'nt':
          self.fd.seek(0)
          msvcrt.locking(self.fd.fileno(), msvcrt.LK_NBLCK, 1)  # pytype: disable=module-attr
        else:
          fcntl.flock(self.fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return self
      except (IOError, OSError) as exc:
        if time.time() - start_time >= self.timeout_sec:
          if self.fd is not None:
            try:
              self.fd.close()
            except OSError:
              pass
          self.fd = None
          raise TimeoutError(
              f'Timeout waiting for lock: {self.lockfile}'
          ) from exc
        time.sleep(0.1)

  def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
    if self.fd is not None:
      try:
        if os.name == 'nt':
          self.fd.seek(0)
          msvcrt.locking(self.fd.fileno(), msvcrt.LK_UNLCK, 1)  # pytype: disable=module-attr
        else:
          fcntl.flock(self.fd.fileno(), fcntl.LOCK_UN)
      except (IOError, OSError):
        pass
      finally:
        try:
          self.fd.close()
        except OSError:
          pass
        self.fd = None


def _locked_update_file(
    file_path: str,
    update_key: str,
    update_data: dict[str, Any],
    *,
    is_yaml: bool,
) -> None:
  """Safely updates a shared file concurrently across platforms."""
  with CrossPlatformFileLock(file_path):
    global_dict = {}
    try:
      with open(file_path, 'r') as f:
        content = f.read()
        if content:
          if is_yaml:
            global_dict = yaml.safe_load(content)
          else:
            global_dict = json.loads(content)
    except FileNotFoundError:
      pass
    except (OSError, json.JSONDecodeError, yaml.YAMLError):
      logging.exception(
          'Failed to load existing metrics file %s', file_path
      )

    global_dict = global_dict or {}
    global_dict[update_key] = update_data

    tmp_file = file_path + '.tmp'
    try:
      with open(tmp_file, 'w') as f:
        if is_yaml:
          yaml.dump(global_dict, f, default_flow_style=False)
        else:
          json.dump(global_dict, f, indent=2, default=str)

      # Atomically swap the temporary file into the final path
      os.replace(tmp_file, file_path)
    except (OSError, TypeError, yaml.YAMLError) as e:
      logging.exception('Failed to update metrics file %s: %s', file_path, e)
      with contextlib.suppress(FileNotFoundError):
        os.remove(tmp_file)


def export_manager_to_files(
    manager: MetricsManager, log_path: str, user_params: Mapping[str, Any]
) -> None:
  """Exports metrics to a global JSON and YAML file under the global run path."""
  global_log_path = os.path.dirname(log_path)

  json_filename = user_params.get('metrics_json_filename')
  if json_filename and isinstance(json_filename, str):
    json_formatter = JsonFormatter()
    current_dict = sanitize_for_mobly(json_formatter.to_dict(manager))

    json_file_path = os.path.join(global_log_path, json_filename)
    logging.info('Writing global JSON metrics to %s', json_file_path)
    _locked_update_file(
        json_file_path, manager.test_class_tag, current_dict, is_yaml=False
    )

  yaml_filename = user_params.get('metrics_yaml_filename')
  if yaml_filename and isinstance(yaml_filename, str):
    yaml_formatter = YamlFormatter()
    current_dict = sanitize_for_mobly(yaml_formatter.to_dict(manager))

    yaml_file_path = os.path.join(global_log_path, yaml_filename)
    logging.info('Writing global YAML metrics to %s', yaml_file_path)
    _locked_update_file(
        yaml_file_path, manager.test_class_tag, current_dict, is_yaml=True
    )


class MetricsFormatter:
  """Base class for metrics formatters."""

  def format(self, manager: MetricsManager) -> Any:
    """Formats metrics from MetricsManager."""
    raise NotImplementedError

  def _aggregate_by_scenario(
      self,
      manager: MetricsManager,
      exclude_aggregators: abc.Sequence[aggregators.AggregatorType] = (),
  ) -> dict[str, dict[str, Any]]:
    """Aggregates iteration metrics grouped by scenario name."""
    by_scenario = collections.defaultdict(list)
    for col in manager.iteration_collectors:
      base_name = _get_base_scenario_name(col.scenario_name)
      by_scenario[base_name].append(col)

    aggregated = {}
    for scenario_name, collectors in by_scenario.items():
      by_key = collections.defaultdict(list)
      for col in collectors:
        for k, m in col.metrics.items():
          if m.aggregator in exclude_aggregators:
            continue
          by_key[k].append(m)

      scenario_agg = {}
      for k, metrics in by_key.items():
        first_metric, *_ = metrics
        agg_name = first_metric.aggregator
        agg = aggregators.get_aggregator(agg_name)
        scenario_agg[k] = agg.aggregate(metrics)
      aggregated[scenario_name] = scenario_agg
    return aggregated


class JsonFormatter(MetricsFormatter):
  """Formats metrics into a structured JSON string."""

  def _format_scenarios(self, manager: MetricsManager) -> dict[str, Any]:
    """Formats scenario-based metrics for JSON output.

    Args:
      manager: The MetricsManager instance containing all metrics data.

    Returns:
      A dictionary where keys are scenario names and values are dictionaries
      containing aggregated metrics, scenario-level metrics, and iteration data.
    """
    aggregated = self._aggregate_by_scenario(
        manager,
        exclude_aggregators=(
            aggregators.AggregatorType.EXCLUDE_AGGREGATING,
            aggregators.AggregatorType.EXCLUDE_ALL,
        ),
    )

    scenarios = {}
    for scenario_name, agg_data in aggregated.items():
      scenario_iters = []
      for col in manager.iteration_collectors:
        if col.scenario_name == scenario_name:
          scenario_iters.append({
              'test_name': col.test_name,
              'metrics': {
                  k: m.value
                  for k, m in col.metrics.items()
                  if m.aggregator != aggregators.AggregatorType.EXCLUDE_ALL
              },
          })
      scenario_metrics = {}
      if scenario_name in manager.scenario_metrics:
        scenario_metrics = {
            k: m.value
            for k, m in manager.scenario_metrics[scenario_name].metrics.items()
            if m.aggregator != aggregators.AggregatorType.EXCLUDE_ALL
        }

      scenarios[scenario_name] = {
          'scenario_metrics': scenario_metrics,
          'aggregated_metrics': agg_data,
          'iterations': scenario_iters,
      }
    return scenarios

  def to_dict(self, manager: MetricsManager) -> dict[str, Any]:
    """Converts MetricsManager data to a structured dictionary."""
    return {
        'test_info': {
            'test_class': manager.test_class_tag,
            'start_time': manager.start_time.isoformat(),
            'end_time': (
                manager.end_time.isoformat() if manager.end_time else None
            ),
        },
        'class_metrics': {
            k: m.value
            for k, m in manager.class_metrics.metrics.items()
            if m.aggregator != aggregators.AggregatorType.EXCLUDE_ALL
        },
        'scenarios': self._format_scenarios(manager),
    }

  def format(self, manager: MetricsManager) -> str:
    """Formats metrics from MetricsManager into a JSON string."""
    return json.dumps(self.to_dict(manager), indent=2, default=str)


class YamlFormatter(JsonFormatter):
  """Formats metrics into a structured YAML string."""

  def format(self, manager: MetricsManager) -> str:
    """Formats metrics from MetricsManager into a YAML string."""
    data = self.to_dict(manager)
    # Convert datetime objects to strings for YAML serialization
    data = json.loads(json.dumps(data, default=str))
    return yaml.dump(data, default_flow_style=False)


class MoblyGroupFormatter:
  """Interface for custom Mobly group formatters."""

  def format_group(
      self,
      group_name: str,
      group_data: Mapping[str, Any],
      manager: MetricsManager,
      scenario_name: str = '',
  ) -> Mapping[str, Any]:
    """Formats a group of metrics.

    Args:
      group_name: The name of the group.
      group_data: Dictionary of metrics in this group.
      manager: The MetricsManager.
      scenario_name: The name of the current scenario.

    Returns:
      Dictionary of key-value pairs to merge into Mobly properties.
    """
    raise NotImplementedError


class DefaultGroupFormatter(MoblyGroupFormatter):
  """Default formatter for groups without custom formatters."""

  def format_group(
      self,
      group_name: str,
      group_data: Mapping[str, Any],
      manager: MetricsManager,
      scenario_name: str = '',
  ) -> Mapping[str, Any]:
    """Formats a group of metrics using a default representation."""
    if len(group_data) == 1 and group_name in group_data:
      return group_data

    lines = []
    for k, v in group_data.items():
      # Apply precision to floats
      if isinstance(v, float):
        lines.append(f'{k}: {round(v, 2)}')
      elif isinstance(v, dict):
        # If the value is a dictionary (e.g., Counter aggregated counts),
        # format it cleanly, extracting Enum names if present.
        def get_key_name(x: Any) -> str:
          return x.name if hasattr(x, 'name') else str(x)

        dict_str = ', '.join(
            f'{get_key_name(ki)}:'
            f' {round(vi, 2) if isinstance(vi, float) else vi}'
            for ki, vi in v.items()
        )
        lines.append(f'{k}: {dict_str}')
      else:
        # Cleanly resolve Enums to their string names
        val_str = v.name if hasattr(v, 'name') else str(v)
        lines.append(f'{k}: {val_str}')

    return {group_name: '\n'.join(lines)}


class MultiLineStringFormatter(MoblyGroupFormatter):
  """Generic formatter to format multiple keys into a single multi-line string."""

  def __init__(
      self,
      key_labels: Sequence[tuple[str, str]],
      output_key: str,
      formats: Mapping[str, str] | None = None,
  ) -> None:
    """Initializes the instance."""
    self.key_labels = key_labels
    self.output_key = output_key
    self.formats = formats or {}

  def format_group(
      self,
      group_name: str,
      group_data: Mapping[str, Any],
      manager: MetricsManager,
      scenario_name: str = '',
  ) -> Mapping[str, Any]:
    """Formats specified keys from a group into a single multi-line string."""
    lines = []
    for k, label in self.key_labels:
      if k in group_data:
        v = group_data[k]
        val_str = v if not hasattr(v, 'name') else v.name
        fmt = self.formats.get(k, '{label}: {value}')
        lines.append(fmt.format(label=label, value=val_str))
    return {self.output_key: '\n'.join(lines)}


class CounterFormatter(MoblyGroupFormatter):
  """Generic formatter for metric occurrences/counters."""

  def __init__(self, metric_key: str, output_key: str) -> None:
    """Initializes the instance."""
    self.metric_key = metric_key
    self.output_key = output_key

  def format_group(
      self,
      group_name: str,
      group_data: Mapping[str, Any],
      manager: MetricsManager,
      scenario_name: str = '',
  ) -> Mapping[str, Any]:
    """Formats metric occurrences/counters into a readable string."""
    freqs = group_data.get(self.metric_key, {})
    if not freqs:
      return {self.output_key: 'NA'}

    def get_key_name(k: Any) -> str:
      if hasattr(k, 'name'):
        return k.name
      return str(k)

    stats_str = '\n'.join(f'{get_key_name(k)}: {v}' for k, v in freqs.items())
    return {self.output_key: stats_str}


class StatsGroupFormatter(MoblyGroupFormatter):
  """Generic formatter to format multiple stats metrics into a legacy string."""

  def __init__(
      self,
      config: dict[str, str | dict[str, str]],
      output_key: str,
      is_duration: bool = False,
      float_format: str = '{:.2f}',
  ) -> None:
    """Initializes the instance."""
    self.config = config
    self.output_key = output_key
    self.is_duration = is_duration
    self.float_format = float_format

  def format_group(
      self,
      group_name: str,
      group_data: Mapping[str, Any],
      manager: MetricsManager,
      scenario_name: str = '',
  ) -> Mapping[str, Any]:
    """Formats multiple stats metrics into a legacy string format."""
    lines = []
    for metric_key in self.config:
      if (
          metric_key in group_data
          and group_data[metric_key].get('count', 0) > 0
      ):
        break
    else:
      return {self.output_key: 'NA'}

    def to_sec(v: Any) -> float | str:
      if isinstance(v, datetime.timedelta):
        return v.total_seconds()
      return float(v) if v is not None else 0.0

    for metric_key, mapping in self.config.items():
      m_data = group_data.get(
          metric_key, {'count': 0, 'min': 0.0, 'median': 0.0, 'max': 0.0}
      )
      if m_data.get('count', 0) == 0:
        continue

      if isinstance(mapping, str):
        labels = {
            'count': f'{mapping}_count',
            'min': f'{mapping}_min',
            'median': f'{mapping}_med',
            'max': f'{mapping}_max',
        }
      else:
        labels = mapping

      val_min = (
          to_sec(m_data.get('min')) if self.is_duration else m_data.get('min')
      )
      val_med = (
          to_sec(m_data.get('median'))
          if self.is_duration
          else m_data.get('median')
      )
      val_max = (
          to_sec(m_data.get('max')) if self.is_duration else m_data.get('max')
      )

      fmt_min = (
          self.float_format.format(val_min)
          if isinstance(val_min, (int, float))
          else str(val_min)
      )
      fmt_med = (
          self.float_format.format(val_med)
          if isinstance(val_med, (int, float))
          else str(val_med)
      )
      fmt_max = (
          self.float_format.format(val_max)
          if isinstance(val_max, (int, float))
          else str(val_max)
      )

      if 'count' in labels:
        lines.append(f"{labels['count']}: {m_data.get('count')}")
      if 'min' in labels:
        lines.append(f"{labels['min']}: {fmt_min}")
      if 'median' in labels or 'med' in labels:
        med_key = 'median' if 'median' in labels else 'med'
        lines.append(f'{labels[med_key]}: {fmt_med}')
      if 'max' in labels:
        lines.append(f"{labels['max']}: {fmt_max}")

    return {self.output_key: '\n'.join(lines)}


class MoblyPropsFormatter(MetricsFormatter):
  """Formats metrics to match legacy Mobly properties using mobly_display_group tags."""

  def __init__(
      self,
      custom_formatters: dict[str, MoblyGroupFormatter] | None = None,
      group_order: Sequence[str] | None = None,
      index_prefix: bool = False,
      include_scenario_metrics: bool = True,
  ) -> None:
    self.custom_formatters = custom_formatters or {}
    self.group_order = group_order or []
    self.index_prefix = index_prefix
    self.include_scenario_metrics = include_scenario_metrics

  def _get_mobly_display_group(
      self, manager: MetricsManager, key: str
  ) -> str | None:
    """Gets the `mobly_display_group` for a given metric key.

    It checks class, scenario, and iteration metrics in that order.

    Args:
      manager: The MetricsManager instance.
      key: The metric key to look up.

    Returns:
      The `mobly_display_group` string if found, otherwise None.
    """
    # Check class metrics first
    m = manager.class_metrics.get(key)
    if m:
      return m.mobly_display_group
    # Check scenario metrics
    for col in manager.scenario_metrics.values():
      m = col.get(key)
      if m:
        return m.mobly_display_group
    # Check iteration metrics
    for col in manager.iteration_collectors:
      m = col.get(key)
      if m:
        return m.mobly_display_group
    return None

  def _get_scenario_metric_values(
      self, scenario_metrics: MetricsCollector
  ) -> dict[str, Any]:
    """Extracts metric values from a scenario collector, excluding certain aggregators."""
    return {
        k: m.value
        for k, m in scenario_metrics.metrics.items()
        if m.aggregator not in (
            aggregators.AggregatorType.EXCLUDE_AGGREGATING,
            aggregators.AggregatorType.EXCLUDE_ALL,
        )
    }

  def _format_scenario_metrics(
      self,
      manager: MetricsManager,
      scenario_aggregated: Mapping[str, dict[str, Any]],
      class_data: dict[str, Any],
      format_flat_set_fn,
  ) -> dict[str, Any]:
    """Formats scenario-specific metrics based on the number of scenarios."""
    formatted_scenario_summary = collections.OrderedDict()

    if not self.include_scenario_metrics:
      return formatted_scenario_summary

    if len(scenario_aggregated) <= 1:
      # Single scenario (default): merge raw data and write flat,
      # overwriting baseline.
      flat_aggregated = {}
      scenario_data = {}
      for scenario_name, agg_data in scenario_aggregated.items():
        flat_aggregated.update(agg_data)
        if scenario_name in manager.scenario_metrics:
          scenario_data.update(
              self._get_scenario_metric_values(
                  manager.scenario_metrics[scenario_name]
              )
          )

      combined_data = class_data.copy()
      combined_data.update(scenario_data)
      combined_data.update(flat_aggregated)
      formatted_scenario_summary.update(format_flat_set_fn(combined_data))
    else:
      # Multiple scenarios: merge raw data per-scenario and write
      # scenario-prefixed summaries
      for scenario_name, agg_data in scenario_aggregated.items():
        scenario_data = {}
        if scenario_name in manager.scenario_metrics:
          scenario_data.update(
              self._get_scenario_metric_values(
                  manager.scenario_metrics[scenario_name]
              )
          )

        combined_data = scenario_data.copy()
        combined_data.update(agg_data)

        formatted_agg = format_flat_set_fn(combined_data)
        for k, v in formatted_agg.items():
          formatted_scenario_summary[f'{scenario_name}_{k}'] = v

    return formatted_scenario_summary

  def format(self, manager: MetricsManager) -> dict[str, Any]:
    """Formats metrics to match legacy Mobly properties."""
    # 1. Get all flat class data (common for all scenarios)
    class_data = {
        k: m.value
        for k, m in manager.class_metrics.metrics.items()
        if m.aggregator
        not in (
            aggregators.AggregatorType.EXCLUDE_AGGREGATING,
            aggregators.AggregatorType.EXCLUDE_ALL,
        )
    }

    # 2. Get aggregated metrics grouped by scenario
    scenario_aggregated = self._aggregate_by_scenario(
        manager,
        exclude_aggregators=(
            aggregators.AggregatorType.EXCLUDE_AGGREGATING,
            aggregators.AggregatorType.EXCLUDE_ALL,
        ),
    )

    # 3. Helper to format a flat set of metrics using display groups
    def format_flat_set(
        flat_data: dict[str, Any], scenario_name: str = ''
    ) -> dict[str, Any]:
      groups = collections.defaultdict(dict)
      ungrouped = {}

      for key, value in flat_data.items():
        group_name = self._get_mobly_display_group(manager, key)
        if group_name:
          groups[group_name][key] = value
        else:
          ungrouped[key] = value

      summary = collections.OrderedDict()
      summary.update(ungrouped)

      # Render groups in specified order
      for g_name in self.group_order:
        if g_name in groups:
          if g_name in self.custom_formatters:
            summary.update(
                self.custom_formatters[g_name].format_group(
                    g_name, groups[g_name], manager, scenario_name
                )
            )
          else:
            summary.update(
                DefaultGroupFormatter().format_group(
                    g_name, groups[g_name], manager
                )
            )

      # Render other groups
      for g_name, g_data in groups.items():
        if g_name not in self.group_order:
          if g_name in self.custom_formatters:
            summary.update(
                self.custom_formatters[g_name].format_group(
                    g_name, g_data, manager, scenario_name
                )
            )
          else:
            summary.update(
                DefaultGroupFormatter().format_group(
                    g_name, g_data, manager, scenario_name
                )
            )

      return dict(summary)

    final_summary = collections.OrderedDict()

    # Format class level data first (acts as fallback baseline)
    formatted_class = format_flat_set(class_data)
    final_summary.update(formatted_class)

    # Consolidate and format scenario-specific metrics
    formatted_scenario_summary = self._format_scenario_metrics(
        manager, scenario_aggregated, class_data, format_flat_set
    )
    final_summary.update(formatted_scenario_summary)

    # Sanitize all values to make them safe for Mobly/YAML serialization
    sanitized_summary = {
        k: sanitize_for_mobly(v) for k, v in final_summary.items()
    }

    if not self.index_prefix:
      return sanitized_summary

    # 4. Apply legacy indexing
    legacy_summary = {}
    for index, (k, v) in enumerate(sanitized_summary.items()):
      legacy_summary[f'{index:02}_{k}'] = v
    return legacy_summary
