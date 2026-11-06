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
import types
from typing import NoReturn

from mobly import asserts
from mobly import base_suite
from mobly import base_test
from mobly import records
from mobly import signals
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

  metrics_helper_class = metrics.MetricsHelper
  script_version: str = version.TEST_SCRIPT_VERSION
  _registered_test_classes: set[str] = set()

  @classmethod
  def register_test_class(
      cls, test_class: type[base_test.BaseTestClass] | str
  ) -> None:
    """Registers a test class in the suite-wide registry."""
    name = test_class if isinstance(test_class, str) else test_class.__name__
    cls._registered_test_classes.add(name)

  @classmethod
  def is_test_class_registered(
      cls, test_class: type[base_test.BaseTestClass] | str
  ) -> bool:
    """Returns whether `test_class` is registered in the current test run."""
    name = test_class if isinstance(test_class, str) else test_class.__name__
    return name in cls._registered_test_classes

  @classmethod
  def clear_registered_test_classes(cls) -> None:
    """Clears all registered test classes."""
    cls._registered_test_classes.clear()

  # Configuration parameters

  # instance variables
  metrics_manager: metrics.MetricsManager
  _scenario_configs: dict[str, ScenarioConfig]
  metrics_helper: metrics.MetricsHelper

  def get_metric_registry(self) -> Mapping[str, metrics.MetricDefinition]:
    """Returns the domain-specific metric registry. Subclasses MUST override."""
    raise NotImplementedError('Subclasses must implement get_metric_registry.')

  def __init__(self, configs) -> None:
    """Initializes the instance.

    Args:
      configs: Mobly configs for the test.
    """
    self._metric_registry = self.get_metric_registry()
    iterations_override = configs.user_params.get('test_iterations_override')
    max_error_override = configs.user_params.get(
        'max_consecutive_error_override'
    )

    for attr_name in dir(self):
      if not attr_name.startswith('test_'):
        continue
      func = getattr(self, attr_name)
      if not callable(func):
        continue
      underlying_func = getattr(func, '__func__', func)
      # Only override if the test method was decorated with betocq_repeat
      if not hasattr(underlying_func, 'expected_iterations'):
        continue

      if iterations_override is not None:
        setattr(underlying_func, '_repeat_count', int(iterations_override))
        setattr(
            underlying_func,
            'expected_iterations',
            int(iterations_override),
        )
      if max_error_override is not None:
        setattr(
            underlying_func,
            '_max_consecutive_error',
            int(max_error_override),
        )
    super().__init__(configs)
    self.is_using_gms_api = False
    self.metrics_helper = self.metrics_helper_class(self)
    # Populated by `setup_class`, but initialized here so that the teardown
    # path can rely on it even when `setup_class` aborted before reaching it.
    self._scenario_configs = {}
    # Scenarios (i.e. test methods) that decided at runtime that their
    # remaining iterations must not be executed, mapped to the skip reason.
    # See `skip_remaining_iterations`.
    self._skip_reason_by_scenario: dict[str, str] = {}

  @property
  def skipped_scenarios(self) -> Mapping[str, str]:
    """Scenarios that asked to skip their remaining iterations, and why."""
    return types.MappingProxyType(self._skip_reason_by_scenario)

  def _get_base_scenario_name(self, test_name: str) -> str:
    """Maps a Mobly test name to its scenario (i.e. test method) name.

    Repeated tests are reported by Mobly as `<test_method>_<iteration>`, while
    the scenario bookkeeping is keyed by the test method name.

    Args:
      test_name: The Mobly test name, with or without a repeat suffix.

    Returns:
      The test method name the given test name belongs to.
    """
    if test_name in self._scenario_configs:
      return test_name
    base, _, suffix = test_name.rpartition('_')
    if base and suffix.isdigit():
      return base
    return test_name

  def skip_remaining_iterations(self, reason: str) -> NoReturn:
    """Skips the current iteration and every iteration of the same test method.

    Use this when a condition discovered *during* a test proves that the
    scenario must not be executed on this testbed at all, e.g. the scenario
    turns out to be a duplicate of another test case. The framework then:

    -   marks the current iteration as SKIP (via the standard Mobly skip
        signal);
    -   short-circuits every subsequent iteration of the *same* test method in
        `setup_test`, so no device interaction happens;
    -   reports the scenario as skipped in `teardown_class` and bypasses its
        success-rate assertion.

    Only the calling test method is affected. Other test methods of the same
    class keep running and are still judged on their own results.

    Because the decision is about the scenario itself and not about the device
    under test, it intentionally overrides the BeToCQ verdict of iterations of
    that scenario that already ran, including failed ones.

    Note that only the BeToCQ verdict is overridden. Mobly has already written
    the record of each finished iteration to its summary file by the time the
    skip is requested, so an iteration that failed before the request keeps
    being reported as failed by Mobly and in Sponge, and the runner still
    exits non-zero. Only the class-level assertion in `teardown_class` is
    bypassed.

    Args:
      reason: Human readable explanation, reported as the skip reason.

    Raises:
      ValueError: If called outside of a test method, where the scenario to
        skip cannot be determined. Use `abort_class`/`skip_if` instead.
      signals.TestSkip: Otherwise, to end the current iteration as skipped.
    """
    if self.current_test_info is None:
      raise ValueError(
          'skip_remaining_iterations must be called from a test method; use'
          ' abort_class or skip_if to bypass the whole class.'
      )
    scenario_name = self._get_base_scenario_name(self.current_test_info.name)
    self._skip_reason_by_scenario[scenario_name] = reason
    raise signals.TestSkip(reason)

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
    self.register_test_class(self.__class__)
    self.metrics_manager = metrics.MetricsManager(
        self.TAG, metric_registry=self._metric_registry  # pyrefly: ignore[bad-argument-type]
    )
    try:
      super().setup_class()
      self._class_metadata_recorded = False
      self._scenario_configs = {}

      for attr_name in dir(self):
        if not attr_name.startswith('test_'):
          continue
        func = getattr(self, attr_name)
        if not callable(func):
          continue

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
        self.metrics_helper.record_scenario_setup_metrics(attr_name, collector)

      # Record basic class level info
      self.metrics_manager.class_metrics.record(
          'test_script_version',
          self.script_version,
      )
      self.metrics_manager.class_metrics.record('test_result', 'UNINITIALIZED')

      self._framework_setup_class_completed = True
    except signals.TestAbortClass:
      logging.info('setup_class aborted, attempting to record metadata anyway.')
      self._try_record_class_setup_metadata(self.metrics_manager.class_metrics)
      raise

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
    return self.metrics_helper.get_mobly_formatter(
        include_scenario_metrics=True
    )

  @override
  def setup_test(self) -> None:
    if self.current_test_info is None:
      raise ValueError('current_test_info is None')
    test_name = self.current_test_info.name
    base_scenario_name = self._get_base_scenario_name(test_name)
    skip_reason = self._skip_reason_by_scenario.get(base_scenario_name)
    if skip_reason is not None:
      # A previous iteration of this test method determined that the scenario
      # must not run. Skip before any device interaction happens. `on_skip`
      # creates the iteration collector for the record.
      logging.info('Skipping %s: %s', test_name, skip_reason)
      raise signals.TestSkip(skip_reason)
    self.metrics_manager.start_iteration(
        base_scenario_name, test_name=test_name
    )
    self.get_current_iteration_metrics().record(
        'start_time', datetime.datetime.now()
    )
    if not getattr(self, '_class_metadata_recorded', False):
      self._try_record_class_setup_metadata(self.metrics_manager.class_metrics)
      self._class_metadata_recorded = True
    super().setup_test()

  def teardown_test(self) -> None:
    self.metrics_manager.end_iteration()
    super().teardown_test()

  def _get_active_collector(
      self, record: records.TestResultRecord
  ) -> metrics.MetricsCollector | None:
    """Returns the collector matching the current test record, or None if bypassed."""
    metrics_mgr = getattr(self, 'metrics_manager', None)
    if not metrics_mgr or not getattr(
        metrics_mgr, 'iteration_collectors', None
    ):
      return None
    col = metrics_mgr.iteration_collectors[-1]
    if getattr(col, 'test_name', '') == getattr(record, 'test_name', ''):
      return col
    return None

  def on_pass(self, record: records.TestResultRecord) -> None:
    logging.info('on_pass called for %s', record.test_name)
    completed_metrics = self._get_active_collector(record)
    if completed_metrics is not None:
      try:
        self.metrics_helper.verify_test_passed(completed_metrics)
      except RuntimeError:
        logging.warning(
            'CRITICAL: Test returned normally but safety check failed!'
        )
        completed_metrics.record('mobly_iteration_result', 'FAIL')
        self.metrics_helper.record_post_test_diagnostics(
            False, completed_metrics
        )
        self._record_single_test_iter_report(completed_metrics)
        raise

      completed_metrics.record('mobly_iteration_result', 'PASS')
      logging.info(
          'Recorded mobly_iteration_result=PASS for %s', record.test_name
      )
      self.metrics_helper.record_post_test_diagnostics(True, completed_metrics)

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
        self.metrics_helper.record_post_test_diagnostics(
            False, completed_metrics
        )
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
    self.metrics_helper.record_customized_single_test_iter_report(
        completed_metrics
    )

  def is_test_class_passed(self) -> bool:
    """Checks if every executed scenario meets its local success rate target.

    This method iterates through all collected scenario results. For each
    scenario, it compares the number of successful iterations against the
    configured target success rate, adjusted for any skipped iterations.
    If any single scenario fails to meet its success rate target, the entire
    test class is considered failed. Scenarios with zero adjusted iterations
    (i.e., all iterations were skipped) are bypassed.

    If a scenario requested `skip_remaining_iterations`, it is not applicable
    to this testbed and is excluded from the verdict. Other scenarios of the
    same class are still evaluated.

    Returns:
      True if all scenarios that had executed iterations meet their configured
      success rate targets, False otherwise.
    """
    # Group iteration collectors by scenario name
    scenario_collectors = collections.defaultdict(list)
    metrics_mgr = getattr(self, 'metrics_manager', None)
    if not metrics_mgr or not getattr(
        metrics_mgr, 'iteration_collectors', None
    ):
      logging.info('is_test_class_passed: False (No iterations executed)')
      return False
    for col in metrics_mgr.iteration_collectors:
      scenario_name = col.scenario_name
      if scenario_name:
        scenario_collectors[scenario_name].append(col)

    if not scenario_collectors:
      logging.info('is_test_class_passed: False (No iterations executed)')
      return False

    # Verify each scenario independently
    for scenario_name, collectors in scenario_collectors.items():
      if scenario_name in self._skip_reason_by_scenario:
        logging.info(
            'is_test_class_passed - Scenario "%s": SKIP (skip requested: %s)',
            scenario_name,
            self._skip_reason_by_scenario[scenario_name],
        )
        continue

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
    metrics_mgr = getattr(self, 'metrics_manager', None)
    if not metrics_mgr or not getattr(
        metrics_mgr, 'iteration_collectors', None
    ):
      logging.info('get_test_class_result_message: FAIL (Zero finished tests)')
      return 'FAIL: Test did not execute any iterations. Zero finished tests.'
    for col in metrics_mgr.iteration_collectors:
      if col.scenario_name:
        scenario_collectors[col.scenario_name].append(col)

    if not scenario_collectors:
      logging.info('get_test_class_result_message: FAIL (Zero finished tests)')
      return 'FAIL: Test did not execute any iterations. Zero finished tests.'

    scenario_messages = []
    all_passed = True

    for scenario_name, collectors in scenario_collectors.items():
      skip_reason = self._skip_reason_by_scenario.get(scenario_name)
      if skip_reason is not None:
        scenario_messages.append(f'[{scenario_name}] SKIP: {skip_reason}')
        continue

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

    if all_skipped and not self._skip_reason_by_scenario:
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
      base_scenario_name = self._get_base_scenario_name(record.test_name)
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

  def _is_full_class_skipped(self) -> bool:
    """Whether every test of the class was bypassed without ever running.

    This is the shape produced by an intentional class-level bypass, e.g.
    `abort_class_if` in `setup_class`. The caller additionally requires an
    intentional TestAbortClass or TestSkip termination signal, to distinguish
    this from an unexpected crash.

    Comparing the number of skipped records against the number of requested
    tests is not sufficient, for two reasons.

    First, `requested` holds one entry per test *method*, while `skipped` holds
    one record per *iteration*, so in a class with several test methods the two
    counts can match by pure coincidence: one method skipping all of its
    iterations while another one genuinely fails would be read as a full class
    bypass and hide the failure. Requiring every requested test method to own a
    skipped record rules that out, as a method that ran is not covered by a
    skipped record.

    Second, Mobly also generates skipped records for the remaining tests when a
    test aborts the run mid-flight, e.g. `abort_all` raised from a running
    iteration. Iterations did run then and produced real results, so the class
    must be judged on those results rather than reported as skipped. Requiring
    an empty `executed` list keeps this limited to classes that never started
    an iteration.

    Returns:
      True if the class was bypassed in full before any iteration ran.
    """
    requested_tests = self.results.requested
    scenarios_with_skipped_records = {
        self._get_base_scenario_name(record.test_name)
        for record in self.results.skipped
    }
    logging.info('requested_tests: %s', requested_tests)
    logging.info('skipped_tests: %s', self.results.skipped)
    return (
        bool(requested_tests)
        and not self.results.executed
        and len(self.results.skipped) == len(requested_tests)
        and set(requested_tests).issubset(scenarios_with_skipped_records)
    )

  @override
  def teardown_class(self) -> None:
    try:
      if getattr(self, 'metrics_manager', None) is None:
        logging.info(
            'metrics_manager is missing, returning early from teardown_class.'
        )
        return

      # Subclass hook to record dynamic teardown metadata
      if getattr(self, '_framework_setup_class_completed', False):
        self._try_record_class_teardown_metadata(
            self.metrics_manager.class_metrics
        )
      else:
        logging.info(
            'Framework setup_class did not complete, skipping teardown'
            ' metadata.'
        )

      is_full_class_skipped = self._is_full_class_skipped()
      has_errors = len(getattr(self.results, 'error', [])) > 0
      logging.info('results: %s', self.results)
      logging.info('is_full_class_skipped: %s', is_full_class_skipped)
      logging.info('has_errors: %s', has_errors)

      # Test methods can dynamically request that their remaining iterations
      # be skipped (e.g. the scenario turned out to be a duplicate of another
      # test case). This is a deliberate bypass of the scenario itself, so it
      # takes precedence over any iteration results collected before the
      # request, including failures. The per-scenario flags are recorded on
      # the scenario collectors further below.
      if self._skip_reason_by_scenario:
        logging.info(
            'Scenarios requested to skip their remaining iterations: %s.'
            ' Bypassing their assertions.',
            self._skip_reason_by_scenario,
        )
      all_scenarios_skipped = bool(self._skip_reason_by_scenario) and all(
          scenario_name in self._skip_reason_by_scenario
          for scenario_name in self.metrics_manager.scenario_metrics
      )

      intentional_skip_or_abort = False
      if not all_scenarios_skipped and is_full_class_skipped and not has_errors:
        for r in self.results.skipped:
          logging.info('skipped record: %s', r.__dict__)
          result_str = getattr(r, 'result', '')
          if result_str == 'SKIP':
            intentional_skip_or_abort = True
            break

      if intentional_skip_or_abort:
        logging.info(
            'Class setup intentionally bypassed via abort_if/skip_if.'
            ' Bypassing scenario assertions.'
        )
        self.metrics_manager.class_metrics.record('test_result', 'SKIP')

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
        self.metrics_helper.record_scenario_teardown_metrics(
            scenario_name, collector
        )
        scenario_skip_reason = self._skip_reason_by_scenario.get(scenario_name)
        collector.record('scenario_skipped', scenario_skip_reason is not None)
        if scenario_skip_reason is not None:
          collector.record('scenario_skip_reason', scenario_skip_reason)
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

            detail_msg = self.metrics_helper.get_failed_iteration_details(
                i, col
            )
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

      # Format final detailed result message. Scenarios that requested a skip
      # are reported as `SKIP: <reason>` by the summary builder itself.
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

  def _try_record_class_setup_metadata(
      self, class_metrics: metrics.MetricsCollector
  ) -> None:
    """Safely attempts to record class setup metadata, warning on failure."""
    try:
      self.metrics_helper.record_class_setup_metadata(class_metrics)
    except Exception as e:  # pylint: disable=broad-except
      logging.warning('Failed to record class setup metadata: %s', e)

  def _try_record_class_teardown_metadata(
      self, class_metrics: metrics.MetricsCollector
  ) -> None:
    """Safely attempts to record class teardown metadata, warning on failure."""
    try:
      self.metrics_helper.record_class_teardown_metadata(class_metrics)
    except Exception as e:  # pylint: disable=broad-except
      logging.warning('Failed to record teardown metadata: %s', e)


class FunctionTestBase(PerformanceTestBase):
  """Base test class for non-repeated function tests with clean metrics.

  This class inherits from PerformanceTestBase but configures the formatter
  to exclude scenario-specific metrics from the class-level Mobly properties,
  as function tests are run only once and do not require aggregated statistics.
  Instead, metrics are recorded only as per-test properties.
  """

  @property
  @override
  def mobly_formatter(self) -> metrics_formatters.MoblyPropsFormatter:
    """The configured MoblyPropsFormatter for function tests."""
    return self.metrics_helper.get_mobly_formatter(
        include_scenario_metrics=False
    )


class BaseTestSuite(base_suite.BaseSuite):
  """Base suite class that registers active test classes in the registry."""

  def __init__(self, runner, config) -> None:
    super().__init__(runner, config)
    PerformanceTestBase.clear_registered_test_classes()

  @override
  def add_test_class(
      self, clazz, config=None, tests=None, name_suffix=None
  ) -> None:
    super().add_test_class(
        clazz, config=config, tests=tests, name_suffix=name_suffix
    )
    if (
        not self._test_selector
        or (clazz.__name__, name_suffix) in self._test_selector
        or clazz.__name__ in self._test_selector
    ):
      PerformanceTestBase.register_test_class(clazz)
