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

from absl.testing import absltest
from betocq.metrics import formatters
from betocq.metrics import metrics_base as metrics


class MetricsTest(absltest.TestCase):

  def test_collector_record_retrieves_metric(self):
    col = metrics.MetricsCollector()
    col.record(
        'my_metric', 42, unit='ms', aggregator='stats', bypass_registry=True
    )
    m = col.get('my_metric')
    self.assertIsNotNone(m)

  def test_collector_recorded_metric_has_correct_value(self):
    col = metrics.MetricsCollector()
    col.record(
        'my_metric', 42, unit='ms', aggregator='stats', bypass_registry=True
    )
    m = col.get('my_metric')
    self.assertIsNotNone(m)
    self.assertEqual(m.value, 42)

  def test_collector_recorded_metric_has_correct_unit(self):
    col = metrics.MetricsCollector()
    col.record(
        'my_metric', 42, unit='ms', aggregator='stats', bypass_registry=True
    )
    m = col.get('my_metric')
    self.assertIsNotNone(m)
    self.assertEqual(m.unit, 'ms')

  def test_collector_recorded_metric_has_correct_aggregator(self):
    col = metrics.MetricsCollector()
    col.record(
        'my_metric', 42, unit='ms', aggregator='stats', bypass_registry=True
    )
    m = col.get('my_metric')
    self.assertIsNotNone(m)
    self.assertEqual(m.aggregator, 'stats')

  def test_manager_start_iteration_creates_collector(self):
    mgr = metrics.MetricsManager('TestClass')
    self.assertIsNone(mgr.current_iteration_collector)
    mgr.start_iteration()
    self.assertIsNotNone(mgr.current_iteration_collector)

  def test_manager_end_iteration_stores_collector(self):
    mgr = metrics.MetricsManager('TestClass')
    mgr.start_iteration()
    mgr.end_iteration()
    self.assertLen(mgr.iteration_collectors, 1)
    self.assertIsNone(mgr.current_iteration_collector)

  def test_manager_multiple_iterations_creates_multiple_collectors(self):
    mgr = metrics.MetricsManager('TestClass')
    mgr.start_iteration()
    mgr.end_iteration()
    mgr.start_iteration()
    mgr.end_iteration()
    self.assertLen(mgr.iteration_collectors, 2)

  def test_manager_metrics_isolated_across_iterations(self):
    mgr = metrics.MetricsManager('TestClass')
    mgr.start_iteration()
    col0 = mgr.current_iteration_collector
    self.assertIsNotNone(col0)
    col0.record('latency', 10, unit='ms', bypass_registry=True)
    mgr.end_iteration()
    mgr.start_iteration()
    col1 = mgr.current_iteration_collector
    self.assertIsNotNone(col1)
    col1.record('latency', 20, unit='ms', bypass_registry=True)
    mgr.end_iteration()

    m0 = mgr.iteration_collectors[0].get('latency')
    self.assertIsNotNone(m0)
    self.assertEqual(m0.value, 10)

    m1 = mgr.iteration_collectors[1].get('latency')
    self.assertIsNotNone(m1)
    self.assertEqual(m1.value, 20)

  def test_mobly_props_formatter_does_not_overwrite_class_metrics_in_shared_groups(
      self,
  ):
    registry = {
        'class_val': metrics.MetricDefinition(
            mobly_display_group='shared_group'
        ),
        'scenario_val': metrics.MetricDefinition(
            mobly_display_group='shared_group'
        ),
    }
    mgr = metrics.MetricsManager('TestClass', metric_registry=registry)
    mgr.class_metrics.record('class_val', 'class_data_value')

    mgr.start_iteration(scenario_name='scenario_1')
    collector = mgr.current_iteration_collector
    self.assertIsNotNone(collector)
    collector.record('scenario_val', 'scenario_data_value')
    mgr.end_iteration()

    formatter = formatters.MoblyPropsFormatter(
        group_order=['shared_group'],
        index_prefix=False,
        include_scenario_metrics=True,
    )

    result = formatter.format(mgr)

    self.assertIn('shared_group', result)
    formatted_value = result['shared_group']
    self.assertIn('class_val: class_data_value', formatted_value)
    self.assertIn('scenario_val: scenario_data_value', formatted_value)


if __name__ == '__main__':
  absltest.main()
