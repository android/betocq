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

"""Unit tests for nearby_connection/nc_test_result_utils.py."""

from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from mobly import signals
from mobly.controllers import android_device

from betocq import constants
from betocq import setup_utils
from betocq.metrics import metrics_base
from betocq.nearby_connection import nc_metrics_registry
from betocq.nearby_connection import nc_test_result_utils

MetricsCollector = metrics_base.MetricsCollector


class NcTestResultUtilsTest(parameterized.TestCase):

  @parameterized.named_parameters(
      dict(
          testcase_name='scc_pass',
          p2p_freq=2437,
          is_mcc=False,
          sta_frequency=2437,
          expect_failure=False,
      ),
      dict(
          testcase_name='scc_fail',
          p2p_freq=5180,
          is_mcc=False,
          sta_frequency=2437,
          expect_failure=True,
      ),
      dict(
          testcase_name='mcc_pass',
          p2p_freq=2437,
          is_mcc=True,
          sta_frequency=5180,
          expect_failure=False,
      ),
      dict(
          testcase_name='mcc_fail',
          p2p_freq=2437,
          is_mcc=True,
          sta_frequency=2437,
          expect_failure=True,
      ),
  )
  @mock.patch.object(setup_utils, 'get_wifi_p2p_frequency', autospec=True)
  def test_set_and_assert_p2p_frequency(
      self, mock_get_p2p_freq, p2p_freq, is_mcc, sta_frequency, expect_failure
  ):
    mock_get_p2p_freq.return_value = p2p_freq
    ad = mock.create_autospec(
        android_device.AndroidDevice, instance=True, spec_set=False
    )
    metrics = MetricsCollector(
        metric_registry=nc_metrics_registry.NC_METRICS_REGISTRY
    )

    if expect_failure:
      with self.assertRaises(signals.TestFailure):
        nc_test_result_utils.set_and_assert_p2p_frequency(
            ad,
            metrics,
            is_mcc=is_mcc,
            is_dbs_mode=False,
            sta_frequency=sta_frequency,
        )
      m = metrics.get('medium_frequency')
      self.assertIsNotNone(m)
      self.assertEqual(m.value, p2p_freq)
      fail_reason = metrics.get('active_nc_fail_reason')
      self.assertIsNotNone(fail_reason)
      self.assertEqual(
          fail_reason.value,
          constants.SingleTestFailureReason.WRONG_P2P_FREQUENCY,
      )
    else:
      nc_test_result_utils.set_and_assert_p2p_frequency(
          ad,
          metrics,
          is_mcc=is_mcc,
          is_dbs_mode=False,
          sta_frequency=sta_frequency,
      )
      m = metrics.get('medium_frequency')
      self.assertIsNotNone(m)
      self.assertEqual(m.value, p2p_freq)

  @mock.patch.object(
      setup_utils, 'get_sta_frequency_and_max_link_speed', autospec=True
  )
  def test_set_and_assert_sta_frequency_pass(self, mock_get_sta_info):
    mock_get_sta_info.return_value = (2437, 72)
    ad = mock.create_autospec(
        android_device.AndroidDevice, instance=True, spec_set=False
    )
    ad.nearby = mock.MagicMock()
    ad.nearby.wifiGetConnectionInfo.return_value = {}
    metrics = MetricsCollector(
        metric_registry=nc_metrics_registry.NC_METRICS_REGISTRY
    )

    nc_test_result_utils.set_and_assert_sta_frequency(
        ad, metrics, constants.WifiType.FREQ_2G, prefix='advertiser_'
    )

    sta_freq = metrics.get('advertiser_sta_frequency')
    self.assertIsNotNone(sta_freq)
    self.assertEqual(sta_freq.value, 2437)
    max_speed = metrics.get('advertiser_max_sta_link_speed_mbps')
    self.assertIsNotNone(max_speed)
    self.assertEqual(max_speed.value, 72)

  @mock.patch.object(
      setup_utils, 'get_sta_frequency_and_max_link_speed', autospec=True
  )
  def test_set_and_assert_sta_frequency_fail(self, mock_get_sta_info):
    mock_get_sta_info.return_value = (5180, 433)
    ad = mock.create_autospec(
        android_device.AndroidDevice, instance=True, spec_set=False
    )
    ad.nearby = mock.MagicMock()
    ad.nearby.wifiGetConnectionInfo.return_value = {}
    metrics = MetricsCollector(
        metric_registry=nc_metrics_registry.NC_METRICS_REGISTRY
    )

    # Expected 2G but got 5G
    with self.assertRaises(signals.TestAbortAll):
      nc_test_result_utils.set_and_assert_sta_frequency(
          ad, metrics, constants.WifiType.FREQ_2G, prefix='advertiser_'
      )

    fail_reason = metrics.get('active_nc_fail_reason')
    self.assertIsNotNone(fail_reason)
    self.assertEqual(
        fail_reason.value,
        constants.SingleTestFailureReason.WRONG_AP_FREQUENCY,
    )

  @mock.patch.object(
      nc_test_result_utils,
      'assert_throughput_and_run_iperf_if_needed',
      autospec=True,
  )
  @mock.patch.object(
      nc_test_result_utils, '_get_2g_wifi_throughput_benchmark', autospec=True
  )
  def test_assert_2g_wifi_throughput_and_run_iperf_if_needed(
      self, mock_get_benchmark, mock_assert_iperf
  ):
    mock_get_benchmark.return_value = constants.SpeedTarget(10.0, 10.0)
    metrics = MetricsCollector(
        metric_registry=nc_metrics_registry.NC_METRICS_REGISTRY
    )
    rt = constants.NcTestRuntime(
        advertiser=mock.create_autospec(
            android_device.AndroidDevice, instance=True, spec_set=False
        ),
        discoverer=mock.create_autospec(
            android_device.AndroidDevice, instance=True, spec_set=False
        ),
        upgrade_medium_under_test=constants.NearbyMedium.WIFILAN_ONLY,
    )

    nc_test_result_utils.assert_2g_wifi_throughput_and_run_iperf_if_needed(
        metrics, rt, 'tip'
    )

    mock_assert_iperf.assert_called_once_with(
        metrics, rt, constants.SpeedTarget(10.0, 10.0), 'tip', True
    )


if __name__ == '__main__':
  absltest.main()
