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

"""Base test class for nearby connection E2E performance tests."""

from __future__ import annotations

import collections
from collections.abc import Mapping
import dataclasses
import datetime
import logging

from mobly import asserts
from mobly import base_test
from mobly import records
from mobly.controllers.android_device_lib import adb
from typing_extensions import override
from betocq import setup_utils
from betocq import version
from betocq.metrics import formatters as metrics_formatters
from betocq.metrics import metrics_base as metrics


@dataclasses.dataclass
class ScenarioConfig:
  """Configuration parameters for a single test scenario.

  Attributes:
    iterations: The number of iterations expected for this scenario.
    target: The minimum success rate (0.0 to 1.0) required for the scenario to
      be considered passing.
  """

  iterations: int
  target: float


def _is_scenario_passed(
    config: ScenarioConfig, *, success_count: int, skip_count: int = 0
) -> bool:
  """Computes whether a scenario meets its pass/fail threshold."""
  adjusted_iterations = max(0, config.iterations - skip_count)
  if adjusted_iterations == 0:
    return True
  return success_count >= round(adjusted_iterations * config.target, 2)


class PerformanceTestBase(base_test.BaseTestClass):
  """Base test class for nearby connection E2E performance tests."""

  # Configuration parameters

  # instance variables
  metrics_manager: metrics.MetricsManager
  _scenario_configs: dict[str, ScenarioConfig]

  def get_metric_registry(self) -> Mapping[str, metrics.MetricDefinition]:
    """Returns the domain-specific metric registry. Subclasses MUST override."""
    raise NotImplementedError('Subclasses must implement get_metric_registry.')

  def __init__(self, configs) -> None:
    """Initializes the instance.

    Args:
      configs: Mobly configs for the test.
    """
    self._metric_registry = self.get_metric_registry()
    self.is_using_gms_api = False
    iterations_override = configs.user_params.get('test_iterations_override')
    max_error_override = configs.user_params.get(
        'max_consecutive_error_override'
    )

    for attr_name in dir(self):
      if attr_name.startswith('test_'):
        func = getattr(self, attr_name)
        if callable(func):
          underlying_func = getattr(func, '__func__', func)
          if iterations_override is not None:
            setattr(underlying_func, '_repeat_count', int(iterations_override))
            setattr(
                underlying_func, 'expected_iterations', int(iterations_override)
            )
          if max_error_override is not None:
            setattr(
                underlying_func,
                '_max_consecutive_error',
                int(max_error_override),
            )
    super().__init__(configs)

  def get_success_rate(self, scenario_name: str) -> float:
    """Returns the success rate target for a scenario.

    Subclasses can override.

    Args:
      scenario_name: The name of the test scenario.
    """
    del self  # Unused in base class.
    del scenario_name  # Unused in base class.
    return 1.0

  def setup_class(self) -> None:
    self.metrics_manager = metrics.MetricsManager(
        self.TAG, metric_registry=self._metric_registry
    )
    super().setup_class()
    self._scenario_configs = {}

    # 1. Auto-discover test methods and expected iterations
    for attr_name in dir(self):
      if attr_name.startswith('test_'):
        func = getattr(self, attr_name)
        if callable(func):
          underlying_func = getattr(func, '__func__', func)
          iterations = getattr(
              underlying_func,
              'expected_iterations',
              getattr(underlying_func, '_repeat_count', 1),
          )
          self._scenario_configs[attr_name] = ScenarioConfig(
              iterations=iterations,
              target=self.get_success_rate(attr_name),
          )

          # Initialize scenario-scoped metric collectors
          collector = metrics.MetricsCollector(
              attr_name, metric_registry=self._metric_registry
          )
          self.metrics_manager.scenario_metrics[attr_name] = collector
          collector.record(
              'success_rate_target', self.get_success_rate(attr_name)
          )
          self._record_scenario_setup_metrics(attr_name, collector)

    # Record basic class level info
    self.metrics_manager.class_metrics.record(
        'test_script_version',
        version.TEST_SCRIPT_VERSION,
    )
    self.metrics_manager.class_metrics.record('test_result', 'UNINITIALIZED')

    self._record_class_setup_metadata(self.metrics_manager.class_metrics)

  def get_current_iteration_metrics(self) -> metrics.MetricsCollector:
    """Returns the metrics collector for the current iteration.

    Raises:
      ValueError: If no iteration is currently active.
    """
    if self.metrics_manager.current_iteration_collector is None:
      raise ValueError('No active iteration')
    return self.metrics_manager.current_iteration_collector

  @property
  def mobly_formatter(self) -> metrics_formatters.MoblyPropsFormatter:
    """The configured MoblyPropsFormatter for this test class."""
    del self  # Unused in base class.
    return metrics_formatters.MoblyPropsFormatter(index_prefix=True)

  @override
  def setup_test(self) -> None:
    scenario_name = self.current_test_info.name  # pytype: disable=attribute-error
    # Strip Mobly repeat suffix if present
    parts = scenario_name.rsplit('_', 1)
    base_scenario_name = scenario_name
    if (scenario_name not in self._scenario_configs
        and len(parts) == 2
        and parts[1].isdigit()
        and parts[0] in self._scenario_configs):
      base_scenario_name = parts[0]
    self.metrics_manager.start_iteration(
        base_scenario_name, test_name=scenario_name
    )
    self.get_current_iteration_metrics().record(
        'start_time', datetime.datetime.now()
    )
    super().setup_test()

  def teardown_test(self) -> None:
    self.metrics_manager.end_iteration()
    super().teardown_test()

  def _get_active_collector(
      self, record: records.TestResultRecord
  ) -> metrics.MetricsCollector | None:
    """Returns the collector matching the current test record, or None if bypassed."""
    if not self.metrics_manager.iteration_collectors:
      return None
    col = self.metrics_manager.iteration_collectors[-1]
    if getattr(col, 'test_name', '') == getattr(record, 'test_name', ''):
      return col
    return None

  def on_pass(self, record: records.TestResultRecord) -> None:
    logging.info('on_pass called for %s', record.test_name)
    completed_metrics = self._get_active_collector(record)
    if completed_metrics is not None:
      completed_metrics.record('mobly_iteration_result', 'PASS')
      logging.info(
          'Recorded mobly_iteration_result=PASS for %s', record.test_name
      )
      self._record_post_test_diagnostics(True, completed_metrics)

      self._record_single_test_iter_report(completed_metrics)
    super().on_pass(record)

  @override
  def on_fail(self, record: records.TestResultRecord) -> None:
    logging.info('on_fail called for %s', record.test_name)
    completed_metrics = self._get_active_collector(record)
    if completed_metrics is not None:
      # Distinguish between an assertion failure and an unexpected runtime
      # crash. Standard Mobly routes both ERROR and FAIL records into this
      # on_fail hook.
      result_str = 'FAIL'
      if hasattr(record, 'result'):
        if 'ERROR' in str(record.result).upper():
          result_str = 'ERROR'

      completed_metrics.record('mobly_iteration_result', result_str)
      logging.info(
          'Recorded mobly_iteration_result=%s for %s',
          result_str,
          record.test_name,
      )
      try:
        self._record_device_thermals(completed_metrics)
        self._record_post_test_diagnostics(False, completed_metrics)
        self._record_single_test_iter_report(completed_metrics)
      except (ValueError, TypeError, KeyError, AttributeError):
        logging.exception('Diagnostics collection failed.')
    super().on_fail(record)

  def _record_device_thermals(
      self, completed_metrics: metrics.MetricsCollector
  ) -> None:
    """Dynamically discovers loaded Android devices and logs their thermals."""

    devices = getattr(self, 'ads', [])
    for ad in devices:
      try:
        completed_metrics.record(
            f'thermal_zone_data_{ad.serial}',
            setup_utils.get_thermal_zone_data(ad),
            aggregator=metrics.AggregatorType.EXCLUDE_AGGREGATING,
            bypass_registry=True,
        )
      except adb.AdbError:
        logging.warning(
            'Failed to record thermal data for device %s.',
            ad.serial,
            exc_info=True,
        )

  def _record_single_test_iter_report(
      self, completed_metrics: metrics.MetricsCollector
  ) -> None:
    # Sanitize V2 iteration metrics for Mobly test case properties
    iteration_data = {
        k: metrics_formatters.sanitize_for_mobly(m.value)
        for k, m in completed_metrics.metrics.items()
        if m.aggregator != metrics.AggregatorType.EXCLUDE_ALL
    }
    self.record_data({
        'Test Class': self.TAG,
        'Test Name': completed_metrics.test_name,
        'properties': iteration_data,
    })
    self.record_customized_single_test_iter_report(completed_metrics)

  def record_customized_single_test_iter_report(
      self, completed_metrics: metrics.MetricsCollector
  ) -> None:
    """Writes custom proto diagnostics to disk.

    Subclasses should override this method.

    Args:
      completed_metrics: The metrics collector for the completed iteration.
    """
    del self  # Unused in base class.
    del completed_metrics  # Unused in base class.

  def is_test_class_passed(self) -> bool:
    """Checks if every executed scenario meets its local success rate target.

    This method iterates through all collected scenario results. For each
    scenario, it compares the number of successful iterations against the
    configured target success rate, adjusted for any skipped iterations.
    If any single scenario fails to meet its success rate target, the entire
    test class is considered failed. Scenarios with zero adjusted iterations
    (i.e., all iterations were skipped) are bypassed.

    Returns:
      True if all scenarios that had executed iterations meet their configured
      success rate targets, False otherwise.
    """
    # Group iteration collectors by scenario name
    scenario_collectors = collections.defaultdict(list)
    for col in self.metrics_manager.iteration_collectors:
      scenario_name = col.scenario_name
      if scenario_name:
        scenario_collectors[scenario_name].append(col)

    if not scenario_collectors:
      logging.info('is_test_class_passed: False (No iterations executed)')
      return False

    # Verify each scenario independently
    for scenario_name, collectors in scenario_collectors.items():
      config = self._scenario_configs.get(scenario_name)
      if config is None:
        continue

      success_count = 0
      skip_count = 0
      for col in collectors:
        result_metric = col.get('mobly_iteration_result')
        if result_metric and result_metric.value == 'PASS':
          success_count += 1
        elif result_metric and result_metric.value == 'SKIP':
          skip_count += 1

      # Local scenario success rate check
      adjusted_iterations = max(0, config.iterations - skip_count)
      min_required = round(adjusted_iterations * config.target, 2)

      logging.info(
          'is_test_class_passed - Scenario "%s": success_count=%d,'
          ' min_required=%.2f',
          scenario_name,
          success_count,
          min_required,
      )

      if adjusted_iterations == 0:
        logging.info(
            'is_test_class_passed - Scenario "%s": SKIP', scenario_name
        )
        continue

      if not _is_scenario_passed(
          config, success_count=success_count, skip_count=skip_count
      ):
        logging.info(
            'is_test_class_passed: False (Scenario "%s" failed)', scenario_name
        )
        return False  # Any single scenario failure fails the entire class!

    logging.info('is_test_class_passed: True')
    return True

  def get_test_class_result_message(self) -> str:
    """Returns a detailed pass/fail summary string isolating each scenario.

    This method aggregates the results from all individual test iterations,
    groups them by scenario, and generates a summary message for each scenario.
    The summary for each scenario indicates whether it PASSED, FAILED, or was
    SKIPPED based on the success rate compared to the `ScenarioConfig.target`.

    The final returned string is:
    -   'FAIL: ...' if no iterations were finished.
    -   'SKIP' if all scenarios were fully skipped.
    -   'PASS' if all scenarios with executed iterations met their targets.
    -   A comma-separated string of per-scenario summaries (e.g.,
        '[scenario1] PASS', '[scenario2] FAIL: ...') if there's a mix of
        results or a single scenario failed.

    Returns:
      A string providing a summary of the test class execution status.
    """
    scenario_collectors = collections.defaultdict(list)
    for col in self.metrics_manager.iteration_collectors:
      if col.scenario_name:
        scenario_collectors[col.scenario_name].append(col)

    if not scenario_collectors:
      logging.info('get_test_class_result_message: FAIL (Zero finished tests)')
      return 'FAIL: Test did not execute any iterations. Zero finished tests.'

    scenario_messages = []
    all_passed = True

    for scenario_name, collectors in scenario_collectors.items():
      config = self._scenario_configs.get(scenario_name)
      if config is None:
        scenario_messages.append(f'[{scenario_name}] PASS')
        continue

      success_count = sum(
          1
          for col in collectors
          if (m := col.get('mobly_iteration_result')) and m.value == 'PASS'
      )
      skip_count = sum(
          1
          for col in collectors
          if (m := col.get('mobly_iteration_result')) and m.value == 'SKIP'
      )
      finished_count = len(collectors)
      adjusted_iterations = max(0, config.iterations - skip_count)
      success_rate = (
          float(success_count) / adjusted_iterations
          if adjusted_iterations
          else 1.0
      )

      if adjusted_iterations == 0:
        scenario_messages.append(f'[{scenario_name}] SKIP')
      elif _is_scenario_passed(
          config, success_count=success_count, skip_count=skip_count
      ):
        scenario_messages.append(f'[{scenario_name}] PASS')
      else:
        all_passed = False
        early_exit = (
            ' Note: Test exited early, not all iterations are executed.'
            if finished_count < config.iterations
            else ''
        )
        scenario_messages.append(
            f'[{scenario_name}] FAIL: Low success rate: {success_rate:.2%} is '
            f'lower than the target {config.target:.2%}.{early_exit}'
        )

    any_skipped = any('SKIP' in msg for msg in scenario_messages)
    all_skipped = all('SKIP' in msg for msg in scenario_messages)

    if all_skipped:
      logging.info('get_test_class_result_message: SKIP')
      return 'SKIP'

    if all_passed and not any_skipped:
      logging.info('get_test_class_result_message: PASS')
      return 'PASS'

    final_msg = ', '.join(scenario_messages)
    if len(scenario_collectors) == 1:
      final_msg = final_msg.split('] ', 1)[-1]

    logging.info('get_test_class_result_message: %s', final_msg)
    return final_msg

  @override
  def on_skip(self, record: records.TestResultRecord) -> None:
    completed_metrics = self._get_active_collector(record)
    if completed_metrics is None:
      scenario_name = record.test_name
      parts = scenario_name.rsplit('_', 1)
      base_scenario_name = (
          parts[0] if len(parts) == 2 and parts[1].isdigit() else scenario_name
      )
      self.metrics_manager.start_iteration(
          scenario_name=base_scenario_name, test_name=record.test_name
      )
      completed_metrics = self.metrics_manager.current_iteration_collector

    if completed_metrics is not None:
      completed_metrics.record('mobly_iteration_result', 'SKIP')

      # Extract failure string to determine skip reason
      reason = (
          record.details if record.details else 'Test was skipped explicitly.'
      )
      completed_metrics.record('result_message', f'SKIP: {reason}')

      logging.info(
          'Recorded mobly_iteration_result=SKIP for %s', record.test_name
      )

      self._record_single_test_iter_report(completed_metrics)
      self.metrics_manager.end_iteration()
    super().on_skip(record)

  @override
  def teardown_class(self) -> None:
    try:
      self.metrics_manager.stop()

      # Subclass hook to record dynamic teardown metadata
      self._record_class_teardown_metadata(self.metrics_manager.class_metrics)

      # Verify if the entire class execution was bypassed intentionally.
      # If the number of skipped tests equals the total requested tests, it
      # definitively proves a full-class bypass. Additionally, ensure at least
      # one skipped record carries an intentional TestAbortClass or TestSkip
      # termination signal (or details string) to distinguish from unexpected
      # crashes.
      requested_tests = getattr(self.results, 'requested', [])
      is_full_class_skipped = (
          requested_tests and
          len(self.results.skipped) == len(requested_tests)
      )
      logging.info('results: %s', self.results)
      logging.info('requested_tests: %s', requested_tests)
      logging.info('skipped_tests: %s', self.results.skipped)
      logging.info('is_full_class_skipped: %s', is_full_class_skipped)
      intentional_skip_or_abort = False
      if is_full_class_skipped:
        for r in self.results.skipped:
          logging.info('skipped record: %s', r.__dict__)
          result_str = getattr(r, 'result', '')
          if result_str == 'SKIP':
            intentional_skip_or_abort = True
            break

      if intentional_skip_or_abort:
        logging.info(
            'Class setup intentionally bypassed via abort_if/skip_if. Bypassing'
            ' scenario assertions.'
        )
        self.metrics_manager.class_metrics.record(
            'test_result', 'SKIP'
        )

        legacy_summary = self.mobly_formatter.format(self.metrics_manager)
        self.record_data({'Test Class': self.TAG, 'properties': legacy_summary})

        metrics_formatters.export_manager_to_files(
            self.metrics_manager, self.log_path, self.user_params
        )
        return

      # Generate generic scenario test_stats

      for (
          scenario_name,
          collector,
      ) in self.metrics_manager.scenario_metrics.items():
        self._record_scenario_teardown_metrics(scenario_name, collector)
        failed_count = 0
        failed_details = []

        scenario_collectors = [
            col
            for col in self.metrics_manager.iteration_collectors
            if col.scenario_name == scenario_name
        ]
        finished_iterations = len(scenario_collectors)

        for i, col in enumerate(scenario_collectors):
          res = col.get('mobly_iteration_result')
          if res is None or res.value not in ('PASS', 'SKIP'):
            failed_count += 1
            start_time_metric = col.get('start_time')
            start_time = (
                f'{start_time_metric.value} ' if start_time_metric else ''
            )

            detail_msg = self._get_failed_iteration_details(i, col)
            if not detail_msg:
              result_message_metric = col.get('result_message')
              detail_msg = (
                  result_message_metric.value
                  if result_message_metric
                  else 'N/A'
              )
            failed_details.append(f'- Iter: {i}: {start_time}{detail_msg}')

        start_metric = (
            scenario_collectors[0].get('start_time')
            if scenario_collectors
            else None
        )
        scenario_start_time = (
            start_metric.value
            if start_metric is not None
            else self.metrics_manager.start_time
        )

        scenario_end_time = datetime.datetime.now()

        config = self._scenario_configs.get(scenario_name)
        req_iters = config.iterations if config else 0

        collector.record(
            'start_time',
            scenario_start_time,
            mobly_display_group='test_stats',
        )
        collector.record(
            'end_time',
            scenario_end_time,
            mobly_display_group='test_stats',
        )
        collector.record(
            'required_iterations',
            req_iters,
            mobly_display_group='test_stats',
        )
        collector.record(
            'finished_iterations',
            finished_iterations,
            mobly_display_group='test_stats',
        )
        collector.record(
            'failed_iterations',
            failed_count,
            mobly_display_group='test_stats',
        )

        failed_details_str = (
            '\n '.join(failed_details) if failed_details else 'NA'
        )
        collector.record(
            'failed_iterations_detail',
            f'\n {failed_details_str}',
            mobly_display_group='test_stats',
        )

      # Format final detailed result message
      final_result_message = self.get_test_class_result_message()

      # Record the complete detailed result message string inside 'test_result'
      # class metric!
      self.metrics_manager.class_metrics.record(
          'test_result', final_result_message
      )

      # Legacy summary and file exports
      legacy_summary = self.mobly_formatter.format(self.metrics_manager)
      self.record_data({'Test Class': self.TAG, 'properties': legacy_summary})

      metrics_formatters.export_manager_to_files(
          self.metrics_manager, self.log_path, self.user_params
      )

      self.record_data({
          'properties': {
              self.TAG: final_result_message,
          },
      })
      asserts.assert_true(self.is_test_class_passed(), final_result_message)
    finally:
      super().teardown_class()

  # --- Abstract lifecycle hooks overridden by feature-specific subclasses ---

  def _record_scenario_setup_metrics(
      self, scenario_name: str, metrics_collector: metrics.MetricsCollector
  ) -> None:
    """Subclasses override this to record scenario-specific metrics before execution."""

  def _record_scenario_teardown_metrics(
      self, scenario_name: str, metrics_collector: metrics.MetricsCollector
  ) -> None:
    """Subclasses override this to record scenario-specific metrics after execution."""

  def _record_class_setup_metadata(
      self, class_metrics: metrics.MetricsCollector
  ) -> None:
    """Subclasses override this to record custom class setup metadata."""

  def _record_class_teardown_metadata(
      self, class_metrics: metrics.MetricsCollector
  ) -> None:
    """Subclasses override this to record dynamic class metadata at teardown."""

  def _get_failed_iteration_details(
      self, iter_num: int, collector: metrics.MetricsCollector
  ) -> str:
    """Subclasses override this to return a detailed failure string for the iteration."""
    del iter_num, collector
    return ''

  def _record_post_test_diagnostics(
      self, passed: bool, metrics_collector: metrics.MetricsCollector
  ) -> None:
    """Subclasses override this to record custom diagnostics (success or failure)."""
    pass
