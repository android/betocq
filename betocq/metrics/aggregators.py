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

"""Metrics aggregators for BeToCQ."""

from __future__ import annotations

import collections
from collections.abc import Sequence
import datetime
import statistics
from typing import Any

import immutabledict
from typing_extensions import override

from betocq.metrics import metrics_base


immutabledict = immutabledict.immutabledict
Metric = metrics_base.Metric
AggregatorType = metrics_base.AggregatorType


class Aggregator:
  """Base class for aggregators."""

  def aggregate(self, metrics: Sequence[Metric]) -> Any:
    """Aggregates a list of metrics."""
    raise NotImplementedError


class LastValueAggregator(Aggregator):
  """Returns the last recorded value."""

  @override
  def aggregate(self, metrics: Sequence[Metric]) -> Any:
    del self  # self is unused.
    if not metrics:
      return None
    return metrics[-1].value


class StatsAggregator(Aggregator):
  """Calculates basic statistics for numeric metrics (and timedeltas)."""

  @override
  def aggregate(self, metrics: Sequence[Metric]) -> dict[str, Any]:
    del self  # self is unused.
    values = [m.value for m in metrics if m.value is not None]

    numeric_values = [
        v.total_seconds() if isinstance(v, datetime.timedelta) else float(v)
        for v in values
        if isinstance(v, datetime.timedelta) or isinstance(v, (int, float))
    ]

    if not numeric_values:
      return {}

    return {
        'min': min(numeric_values),
        'max': max(numeric_values),
        'median': statistics.median(numeric_values),
        'mean': statistics.mean(numeric_values),
        'count': len(numeric_values),
    }


class CounterAggregator(Aggregator):
  """Counts occurrences of each unique value."""

  @override
  def aggregate(self, metrics: Sequence[Metric]) -> dict[Any, int]:
    del self  # self is unused.
    values = [m.value for m in metrics if m.value is not None]
    # Convert non-hashable values to string representation if needed
    hashable_values = (
        tuple(v) if isinstance(v, list) else
        frozenset(v.items()) if isinstance(v, dict) else
        v
        for v in values
    )
    return dict(collections.Counter(hashable_values))


class FirstValidValueAggregator(Aggregator):
  """Returns the first valid value encountered."""

  def __init__(
      self,
      invalid_values: Sequence[Any] = (
          None,
          '',
          -1,
      ),
  ):
    self.invalid_values = invalid_values

  @override
  def aggregate(self, metrics: Sequence[Metric]) -> Any:
    for m in metrics:
      val = m.value
      if val is None:
        continue
      # Check if the value itself is in invalid_values
      if val in self.invalid_values:
        continue
      # Check if it's an Enum and its name or value is invalid
      if hasattr(val, 'name') and val.name in self.invalid_values:
        continue
      if hasattr(val, 'value') and val.value in self.invalid_values:
        continue
      return val
    return None


class PassRateAggregator(Aggregator):
  """Calculates the pass rate (ratio of SUCCESS/PASS/True to total)."""

  @override
  def aggregate(self, metrics: Sequence[Metric]) -> float:
    del self  # self is unused.
    values = [m.value for m in metrics if m.value is not None]
    if not values:
      return 0.0
    passes = sum(
        1
        for v in values
        if (isinstance(v, bool) and v)
        or v in ('PASS', 'SUCCESS')
        or (hasattr(v, 'name') and v.name == 'SUCCESS')
    )
    return passes / len(values)


_AGGREGATOR_BY_TYPE = immutabledict({
    AggregatorType.LAST: LastValueAggregator(),
    AggregatorType.STATS: StatsAggregator(),
    AggregatorType.COUNTER: CounterAggregator(),
    AggregatorType.FIRST_VALID: FirstValidValueAggregator(),
    AggregatorType.PASS_RATE: PassRateAggregator(),
    AggregatorType.EXCLUDE_AGGREGATING: LastValueAggregator(),
    AggregatorType.EXCLUDE_ALL: LastValueAggregator(),
})


def get_aggregator(agg_type: AggregatorType | str) -> Aggregator:
  """Gets an aggregator instance by type or string name."""
  agg_type_enum = agg_type
  if isinstance(agg_type, str):
    try:
      agg_type_enum = AggregatorType(agg_type)
    except ValueError as exc:
      raise ValueError(f'Unknown aggregator type: {agg_type}') from exc

  aggregator = _AGGREGATOR_BY_TYPE.get(agg_type_enum)
  if not aggregator:
    raise ValueError(f'Unknown aggregator: {agg_type_enum}')
  return aggregator
