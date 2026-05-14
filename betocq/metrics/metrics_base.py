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

"""Core metrics classes for BeToCQ."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
import dataclasses
import datetime
import enum
import logging
from typing import Any

import immutabledict


@enum.unique
class AggregatorType(str, enum.Enum):
  """Supported aggregator types for metrics aggregation."""

  LAST = 'last'
  STATS = 'stats'
  COUNTER = 'counter'
  FIRST_VALID = 'first_valid'

  PASS_RATE = 'pass_rate'
  EXCLUDE_AGGREGATING = 'exclude_aggregating'
  EXCLUDE_ALL = 'exclude_all'


@dataclasses.dataclass
class Metric:
  """Represents a single metric value with metadata."""

  value: Any
  unit: str = ''
  aggregator: AggregatorType | str = AggregatorType.LAST
  mobly_display_group: str | None = None
  timestamp: datetime.datetime = dataclasses.field(
      default_factory=datetime.datetime.now
  )


@dataclasses.dataclass(frozen=True)
class MetricDefinition:
  """Defines the schema and default behavior for a metric."""

  aggregator: AggregatorType | str = AggregatorType.LAST
  mobly_display_group: str | None = None


def _is_supported_metric_value(val: Any) -> bool:
  """Checks if a value is of a supported metric type."""
  if val is None:
    return True
  if isinstance(
      val, (int, float, str, bool, datetime.datetime, datetime.timedelta)
  ):
    return True
  if isinstance(val, enum.Enum):
    return True
  if isinstance(val, (list, tuple, set)):
    return all(_is_supported_metric_value(x) for x in val)
  if isinstance(val, dict):
    return all(
        isinstance(k, str) and _is_supported_metric_value(v)
        for k, v in val.items()
    )
  return False


FRAMEWORK_METRICS_REGISTRY: immutabledict.immutabledict[
    str, MetricDefinition
] = immutabledict.immutabledict({
    'success_rate_target': MetricDefinition(AggregatorType.FIRST_VALID, None),
    'test_iteration': MetricDefinition(
        AggregatorType.EXCLUDE_AGGREGATING, None
    ),
    'mobly_iteration_result': MetricDefinition(
        AggregatorType.EXCLUDE_ALL, None
    ),
    'test_script_version': MetricDefinition(AggregatorType.LAST, None),
    'test_result': MetricDefinition(AggregatorType.LAST, None),
    'start_time': MetricDefinition(AggregatorType.EXCLUDE_AGGREGATING, None),
    'end_time': MetricDefinition(AggregatorType.EXCLUDE_AGGREGATING, None),
    'required_iterations': MetricDefinition(AggregatorType.LAST, 'test_stats'),
    'finished_iterations': MetricDefinition(AggregatorType.LAST, 'test_stats'),
    'failed_iterations': MetricDefinition(AggregatorType.LAST, 'test_stats'),
    'failed_iterations_detail': MetricDefinition(
        AggregatorType.LAST, 'test_stats'
    ),
})


class MetricsCollector:
  """A collector for metrics within a specific scope (e.g., iteration or class)."""

  def __init__(
      self,
      scenario_name: str = '',
      metric_registry: Mapping[str, MetricDefinition] | None = None,
      test_name: str = '',
  ) -> None:
    self.scenario_name = scenario_name
    self.test_name = test_name
    self.metric_registry = dict(FRAMEWORK_METRICS_REGISTRY)
    if metric_registry:
      self.metric_registry.update(metric_registry)
    self._metrics: dict[str, Metric] = {}

  def record(
      self,
      key: str,
      value: Any,
      *,
      unit: str = '',
      aggregator: AggregatorType | str | None = None,
      mobly_display_group: str | None = None,
      bypass_registry: bool = False,
  ) -> None:
    """Records a metric.

    Args:
      key: The name of the metric.
      value: The value of the metric.
      unit: The unit of the metric value.
      aggregator: The aggregator type to use for this metric. If None, it will
        be looked up in the registry or default to STATS/LAST.
      mobly_display_group: An optional group name for Mobly display.
      bypass_registry: If True, allows recording metrics not present in the
        metric registry.

    Raises:
      KeyError: If `bypass_registry` is False and the metric `key` is not found
        in the `metric_registry`.
    """
    if not bypass_registry and key not in self.metric_registry:
      raise KeyError(
          f"Metric '{key}' is not registered! Register it in metric_registry "
          'or pass bypass_registry=True to suppress this error.'
      )

    if aggregator is None:
      if key in self.metric_registry:
        aggregator = self.metric_registry[key].aggregator
      else:
        # bypass_registry is True and the metric is not registered.
        # Default to STATS for numeric types, otherwise LAST.
        if isinstance(value, (int, float)):
          aggregator = AggregatorType.STATS
        else:
          aggregator = AggregatorType.LAST

    if mobly_display_group is None:
      mobly_display_group = self.metric_registry.get(
          key, MetricDefinition()
      ).mobly_display_group
    copied_value = copy.deepcopy(value)

    self._metrics[key] = Metric(
        copied_value, unit, aggregator, mobly_display_group
    )

  def record_dataclass(
      self,
      obj: Any,
      *,
      prefix: str = '',
      name_mapping: Mapping[str, str | None] | None = None,
      mobly_display_group: str | None = None,
      exclude_fields: Sequence[str] = (),
      bypass_registry: bool = False,
  ) -> None:
    """Records all fields (and mapped properties) from a dataclass object.

    Args:
      obj: The dataclass instance to record metrics from.
      prefix: A prefix to add to each metric name.
      name_mapping: A dictionary to map dataclass field/property names to
        metric names. A value of None means the field/property should not be
        recorded.
      mobly_display_group: An optional group name for Mobly display, applied to
        all metrics recorded from this dataclass.
      exclude_fields: A sequence of field names to exclude from recording.
      bypass_registry: If True, allows recording metrics not present in the
        metric registry.

    Raises:
      KeyError: If `bypass_registry` is False and a metric derived from the
        dataclass fields or `name_mapping` is not found in the
        `metric_registry`.
    """
    if not dataclasses.is_dataclass(obj):
      return
    name_mapping = name_mapping or {}

    recorded_keys = set()
    # 1. Record fields
    for field in dataclasses.fields(obj):
      if field.name in exclude_fields:
        continue
      recorded_keys.add(field.name)
      val = getattr(obj, field.name)
      metric_name = name_mapping.get(field.name, field.name)
      if metric_name is None:
        continue
      metric_name = prefix + metric_name

      if not _is_supported_metric_value(val):
        continue
      if not bypass_registry and metric_name not in self.metric_registry:
        raise KeyError(
            f"Dataclass field '{metric_name}' is not registered! Add it to"
            ' metric_registry, add it to exclude_fields, or pass'
            ' bypass_registry=True.'
        )
      self.record(
          metric_name,
          val,
          mobly_display_group=mobly_display_group,
          bypass_registry=bypass_registry,
      )

    # 2. Record extra attributes from name_mapping (e.g., properties)
    for key, metric_name in name_mapping.items():
      if key in exclude_fields:
        continue
      if key in recorded_keys:
        continue
      if metric_name is None:
        continue
      if hasattr(obj, key):
        try:
          val = getattr(obj, key)
        except (AttributeError, TypeError):
          logging.exception(
              'Failed to fetch property %s from %s', key, obj
          )
          continue
        if callable(val):
          continue
        metric_name = prefix + metric_name

        if not _is_supported_metric_value(val):
          continue
        if not bypass_registry and metric_name not in self.metric_registry:
          raise KeyError(
              f"Dataclass mapping '{metric_name}' is not registered! Add it to"
              ' metric_registry, add it to exclude_fields, or pass'
              ' bypass_registry=True.'
          )
        self.record(
            metric_name,
            val,
            mobly_display_group=mobly_display_group,
            bypass_registry=bypass_registry,
        )

  def get(self, key: str) -> Metric | None:
    """Gets a metric by key."""
    return self._metrics.get(key)

  def get_value(self, keys: str | Sequence[str], default: Any = None) -> Any:
    """Returns the value of the first matching key, or the default."""
    if isinstance(keys, str):
      keys_list = [keys]
    else:
      keys_list = keys
    for k in keys_list:
      if k in self._metrics:
        return self._metrics[k].value
    return default

  @property
  def metrics(self) -> dict[str, Metric]:
    """All collected metrics."""
    return self._metrics


class MetricsManager:
  """A manager for metrics collection across a test run (class and iterations)."""

  def __init__(
      self,
      test_class_tag: str,
      metric_registry: Mapping[str, MetricDefinition] | None = None,
  ) -> None:
    self.test_class_tag = test_class_tag
    self.metric_registry = dict(FRAMEWORK_METRICS_REGISTRY)
    if metric_registry:
      self.metric_registry.update(metric_registry)
    self.class_metrics = MetricsCollector(metric_registry=self.metric_registry)
    self.scenario_metrics: dict[str, MetricsCollector] = {}
    self.iteration_collectors: list[MetricsCollector] = []
    self.current_iteration_collector: MetricsCollector | None = None
    self.start_time = datetime.datetime.now()
    self.end_time: datetime.datetime | None = None

  def start_iteration(
      self, scenario_name: str = '', test_name: str = ''
  ) -> None:
    """Starts a new test iteration."""
    self.current_iteration_collector = MetricsCollector(
        scenario_name, metric_registry=self.metric_registry, test_name=test_name
    )
    self.iteration_collectors.append(self.current_iteration_collector)

  def end_iteration(self) -> None:
    """Ends the current test iteration."""
    self.current_iteration_collector = None

  def stop(self) -> None:
    """Stops metrics collection and records end time."""
    self.end_time = datetime.datetime.now()
