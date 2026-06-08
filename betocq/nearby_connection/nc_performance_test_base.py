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

"""Base test class for Nearby Connection performance tests with legacy metrics."""

from collections.abc import Mapping

from typing_extensions import override

from betocq import base_test
from betocq import constants
from betocq import performance_test_base_v2
from betocq import setup_utils
from betocq import test_result_utils
from betocq.metrics import formatters as metrics_formatters
from betocq.metrics import metrics_base
from betocq.nearby_connection import nc_group_formatters
from betocq.nearby_connection import nc_metrics_registry


class NcMetricsHelper(metrics_base.MetricsHelper):
  """Metrics helper for Nearby Connection-specific metrics logic."""

  @override
  def record_class_setup_metadata(
      self, class_metrics: metrics_base.MetricsCollector
  ) -> None:
    """Records class setup metadata."""
    class_metrics.record(
        'device_source',
        setup_utils.get_device_attributes(
            self.test.discoverer,
        ),
    )
    class_metrics.record(
        'device_target',
        setup_utils.get_device_attributes(
            self.test.advertiser,
        ),
    )
    class_metrics.record(
        'target_build_id',
        self.test.advertiser.build_info['build_id'],
    )
    class_metrics.record(
        'target_model',
        self.test.advertiser.model,
    )
    class_metrics.record(
        'target_gms_version',
        setup_utils.dump_gms_version(self.test.advertiser),
    )
    class_metrics.record(
        'target_wifi_chipset',
        getattr(self.test.advertiser, 'wifi_chipset', 'NA'),
    )

  @override
  def record_class_teardown_metadata(
      self, class_metrics: metrics_base.MetricsCollector
  ) -> None:
    """Records class teardown metadata."""
    device_specific_info = setup_utils.get_betocq_device_specific_info(
        self.test.advertiser
    )
    if (
        wifi_env_bssid_count := device_specific_info.get('wifi_env_bssid_count')
    ) is not None:
      wifi_ap_number = 0
      if (
          isinstance(wifi_env_bssid_count, str)
          and wifi_env_bssid_count.isdigit()
      ):
        wifi_ap_number = int(wifi_env_bssid_count)
      class_metrics.record(
          'wifi_ap_number',
          wifi_ap_number,
      )

  @override
  def record_scenario_teardown_metrics(
      self, scenario_name: str, metrics_collector: metrics_base.MetricsCollector
  ) -> None:
    """Records scenario teardown metrics."""
    test_runtime = getattr(self.test, 'test_runtime', None)
    if not test_runtime:
      return

    metrics_collector.record_dataclass(
        test_runtime,
        exclude_fields=['advertiser', 'discoverer', 'wifi_info'],
    )
    wifi_info = getattr(test_runtime, 'wifi_info', None)
    if not wifi_info:
      return

    metrics_collector.record_dataclass(
        wifi_info,
        name_mapping={
            'is_mcc': 'is_mcc_mode',
            'is_2g_d2d_wifi_medium': 'is_2g_only',
        },
        exclude_fields=[
            'discoverer_wifi_password',
            'advertiser_wifi_password',
        ],
    )

    # Record concurrency mode dynamically
    concurrency_mode = constants.WifiConcurrencyMode.UNKNOWN
    d2d_type = getattr(wifi_info, 'd2d_type', None)
    if d2d_type and constants.is_xcc_test(d2d_type):
      for col in self.test.metrics_manager.iteration_collectors:
        m = col.get('wifi_concurrency_mode')
        if (
            col.scenario_name == scenario_name
            and m
            and m.value != constants.WifiConcurrencyMode.UNKNOWN
        ):
          concurrency_mode = m.value
          break
    else:
      concurrency_mode = constants.get_wifi_concurrency_mode_from_d2d_type(
          d2d_type
      )

    metrics_collector.record(
        'wifi_concurrency_mode',
        concurrency_mode,
    )

  @override
  def get_failed_iteration_details(
      self, iter_num: int, collector: metrics_base.MetricsCollector
  ) -> str:
    """Gets detailed information for a failed iteration."""
    result_msg = collector.get_value('result_message', '')

    sta_freq = collector.get_value(
        ['advertiser_sta_frequency', 'sta_frequency'], 'NA'
    )
    disc_sta_freq = collector.get_value('discoverer_sta_frequency', 'NA')
    sta_max_speed = collector.get_value(
        ['advertiser_max_sta_link_speed_mbps', 'max_sta_link_speed_mbps'], 'NA'
    )

    used_medium = collector.get_value('upgrade_medium', 'NA')
    if hasattr(used_medium, 'name'):
      used_medium = used_medium.name

    medium_freq = collector.get_value('medium_frequency', 'NA')

    return (
        f'{result_msg}\n adv sta freq: {sta_freq},'
        f' disc sta freq: {disc_sta_freq}, sta max link speed:'
        f' {sta_max_speed}, used medium: {used_medium}, medium freq:'
        f' {medium_freq}.'
    )

  @override
  def record_post_test_diagnostics(
      self, passed: bool, completed_metrics: metrics_base.MetricsCollector
  ) -> None:
    """Records diagnostics after a test iteration."""
    if passed:
      completed_metrics.record(
          'active_nc_fail_reason', constants.SingleTestFailureReason.SUCCESS
      )
      m = completed_metrics.get('result_message')
      if not m or m.value == 'UNINITIALIZED':
        completed_metrics.record('result_message', 'PASS')
    else:
      # Check for GMS PID changes and prepend error to result_message
      pids_changed_error = test_result_utils.check_gms_pids_changed(
          self.test.ads
      )
      if pids_changed_error:
        m = completed_metrics.get('result_message')
        message = m.value if m is not None else ''
        new_message = (
            f'{pids_changed_error}\n{message}'
            if message
            else pids_changed_error
        )
        completed_metrics.record('result_message', new_message)

  @override
  def verify_test_passed(
      self, completed_metrics: metrics_base.MetricsCollector
  ) -> None:
    fail_reason = completed_metrics.get('active_nc_fail_reason')
    if (
        fail_reason
        and hasattr(fail_reason.value, 'name')
        and fail_reason.value.name not in ('SUCCESS', 'UNINITIALIZED')
    ):
      raise RuntimeError(
          'CRITICAL FRAMEWORK BUG: Test returned normally but'
          f' active_nc_fail_reason is set to {fail_reason.value.name}. Helper'
          ' functions must raise explicit exceptions on failure.'
      )

  @override
  def get_mobly_formatter(
      self, include_scenario_metrics: bool
  ) -> metrics_formatters.MoblyPropsFormatter:
    if include_scenario_metrics:
      custom_formatters = {
          'test_config': metrics_formatters.MultiLineStringFormatter(
              key_labels=[
                  ('device_source', 'device_source'),
                  ('device_target', 'device_target'),
                  ('target_build_id', 'target_build_id'),
                  ('target_model', 'target_model'),
                  ('target_gms_version', 'target_gms_version'),
                  ('target_wifi_chipset', 'target_wifi_chipset'),
                  ('wifi_ap_number', 'wifi_ap_number'),
                  ('country_code', 'country_code'),
                  (
                      'advertising_discovery_medium',
                      'advertising_discovery_medium',
                  ),
                  ('connection_medium', 'connection_medium'),
                  ('upgrade_medium_under_test', 'upgrade_medium'),
                  ('is_2g_only', 'is_2g_only'),
                  ('is_dbs_mode', 'is_dbs_mode'),
                  ('is_mcc_mode', 'is_mcc_mode'),
                  ('discoverer_wifi_ssid', 'discoverer_wifi_ssid'),
                  ('advertiser_wifi_ssid', 'advertiser_wifi_ssid'),
              ],
              output_key='test_config',
          ),
          'file_transfer_stats': (
              nc_group_formatters.NcFileTransferStatsFormatter()
          ),
          'wifi_upgrade_stats': metrics_formatters.CounterFormatter(
              metric_key='upgrade_medium', output_key='wifi_upgrade_stats'
          ),
          'prior_bt_connection_stats': metrics_formatters.StatsGroupFormatter(
              config={
                  'prior_discovery_latency': {
                      'count': 'discovery_count',
                      'min': 'discovery_latency_min',
                      'median': 'discovery_latency_med',
                      'max': 'discovery_latency_max',
                  },
                  'prior_connection_latency': {
                      'count': 'connection_count',
                      'min': 'connection_latency_min',
                      'median': 'connection_latency_med',
                      'max': 'connection_latency_max',
                  },
              },
              output_key='prior_bt_connection_stats',
              is_duration=True,
              float_format='{:.2f}',
          ),
      }
      group_order = [
          'test_config',
          'test_stats',
          'file_transfer_stats',
          'wifi_upgrade_stats',
          'prior_bt_connection_stats',
          'wifi_concurrency_mode',
      ]
      return metrics_formatters.MoblyPropsFormatter(
          custom_formatters=custom_formatters,
          group_order=group_order,
          index_prefix=True,
          include_scenario_metrics=True,
      )
    else:
      return metrics_formatters.MoblyPropsFormatter(
          index_prefix=True,
          include_scenario_metrics=False,
      )


class NcPerformanceTestBase(
    performance_test_base_v2.PerformanceTestBase,
    base_test.BaseTestClass,
):
  """Base test class for Nearby Connection performance tests with legacy metrics."""

  metrics_helper_class = NcMetricsHelper

  def __init__(self, configs) -> None:
    super().__init__(configs)
    self.is_using_gms_api = True

  @override
  def get_metric_registry(self) -> Mapping[str, metrics_base.MetricDefinition]:
    return nc_metrics_registry.NC_METRICS_REGISTRY

  def _get_advertiser_sta_frequency(self) -> int:
    """Gets the advertiser STA frequency from the current iteration metrics."""
    sta_freq_metric = self.get_current_iteration_metrics().get(
        'advertiser_sta_frequency'
    )
    return (
        sta_freq_metric.value
        if sta_freq_metric is not None
        else constants.INVALID_INT
    )

  @override
  def get_success_rate(self, scenario_name: str) -> float:
    """Returns the expected success rate target."""
    del self  # Unused in this implementation.
    del scenario_name  # Unused in this implementation.
    return constants.SUCCESS_RATE_TARGET


class NcFunctionTestBase(
    performance_test_base_v2.FunctionTestBase,
    base_test.BaseTestClass,
):
  """Base test class for Nearby Connection function tests with clean metrics."""

  metrics_helper_class = NcMetricsHelper

  def __init__(self, configs) -> None:
    super().__init__(configs)
    self.is_using_gms_api = True

  @override
  def get_metric_registry(self) -> Mapping[str, metrics_base.MetricDefinition]:
    return nc_metrics_registry.NC_METRICS_REGISTRY
