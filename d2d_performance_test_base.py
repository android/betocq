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

"""Nearby Connection E2E stress tests for D2D wifi performance."""

import abc
import datetime
import logging
import time
from typing import Any

from mobly import asserts
from mobly.controllers import android_device

from betocq import iperf_utils
from betocq import nc_base_test
from betocq import nc_constants
from betocq import nearby_connection_wrapper
from betocq import setup_utils


_DELAY_BETWEEN_EACH_TEST_CYCLE = datetime.timedelta(seconds=0)
_BITS_PER_BYTE = 8
_MAX_FREQ_2G_MHZ = 2500
_MIN_FREQ_5G_DFS_MHZ = 5260
_MAX_FREQ_5G_DFS_MHZ = 5720


class D2dPerformanceTestBase(nc_base_test.NCBaseTestClass, abc.ABC):
  """Abstract class for D2D performance test for different connection meidums."""

  performance_test_iterations: int

  # @typing.override
  def __init__(self, configs):
    super().__init__(configs)
    self._is_mcc: bool = False
    self._is_2g_d2d_wifi_medium: bool = False
    self._is_dbs_mode: bool = False
    self._throughput_low_string: str = ''
    self._upgrade_medium_under_test: nc_constants.NearbyMedium = None
    self._connection_medium: nc_constants.NearbyMedium = None
    self._advertising_discovery_medium: nc_constants.NearbyMedium = None
    self._current_test_result: nc_constants.SingleTestResult = (
        nc_constants.SingleTestResult()
    )
    self._performance_test_metrics: nc_constants.NcPerformanceTestMetrics = (
        nc_constants.NcPerformanceTestMetrics()
    )
    self._prior_bt_nc_fail_reason: nc_constants.SingleTestFailureReason = (
        nc_constants.SingleTestFailureReason.UNINITIALIZED
    )
    self._active_nc_fail_reason: nc_constants.SingleTestFailureReason = (
        nc_constants.SingleTestFailureReason.UNINITIALIZED
    )
    self._finished_test_iteration: int = 0
    self._use_prior_bt: bool = False
    self._start_time: datetime.datetime = datetime.datetime.now()
    self._wifi_ssid: str = ''
    self._test_results: list[nc_constants.SingleTestResult] = []

  # @typing.override
  def setup_test(self):
    self._current_test_result: nc_constants.SingleTestResult = (
        nc_constants.SingleTestResult()
    )
    self._prior_bt_nc_fail_reason = (
        nc_constants.SingleTestFailureReason.UNINITIALIZED
    )
    self._active_nc_fail_reason = (
        nc_constants.SingleTestFailureReason.UNINITIALIZED
    )
    super().setup_test()

  def teardown_test(self):
    self._write_current_test_report()
    self._collect_current_test_metrics()
    super().teardown_test()
    time.sleep(_DELAY_BETWEEN_EACH_TEST_CYCLE.total_seconds())

  @property
  def _devices_capabilities_definition(self) -> dict[str, dict[str, bool]]:
    """Returns the definition of devices capabilities."""
    return {}

  # @typing.override
  def _get_skipped_test_class_reason(self) -> str | None:
    if not self._is_wifi_ap_ready():
      return 'Wifi AP is not ready for this test.'
    skip_reason = self._check_devices_capabilities()
    if skip_reason is not None:
      return (
          f'The test is not required per the device capabilities. {skip_reason}'
      )
    return None

  @abc.abstractmethod
  def _is_wifi_ap_ready(self) -> bool:
    pass

  def _check_devices_capabilities(self) -> str | None:
    """Checks if all devices capabilities meet requirements."""
    for ad_role, capabilities in self._devices_capabilities_definition.items():
      for key, value in capabilities.items():
        ad = getattr(self, ad_role)
        capability = getattr(ad, key)
        if capability != value:
          return (
              f'{ad} {ad_role}.{key} is'
              f' {"enabled" if capability else "disabled"}'
          )
    return None

  def _get_target_sta_frequency_and_max_link_speed(self) -> tuple[int, int]:
    """Gets the STA frequency and max link speed."""
    connection_info = self.advertiser.nearby.wifiGetConnectionInfo()
    sta_frequency = int(
        connection_info.get('mFrequency', nc_constants.INVALID_INT)
    )

    sta_max_link_speed_mbps = int(
        connection_info.get(
            'mMaxSupportedTxLinkSpeed', nc_constants.INVALID_INT
        )
    )
    if sta_frequency == nc_constants.INVALID_INT:
      sta_frequency = setup_utils.get_wifi_sta_frequency(self.advertiser)
      sta_max_link_speed_mbps = setup_utils.get_wifi_sta_max_link_speed(
          self.advertiser
      )
    return (sta_frequency, sta_max_link_speed_mbps)

  def _get_throughput_benchmark(
      self, sta_frequency: int, sta_max_link_speed_mbps: int
  ) -> tuple[float, float]:
    """Gets the throughput benchmark as MBps."""
    max_num_streams = min(
        self.discoverer.max_num_streams, self.advertiser.max_num_streams
    )

    if self._is_2g_d2d_wifi_medium:
      max_phy_rate_mbps = min(
          self.discoverer.max_phy_rate_2g_mbps,
          self.advertiser.max_phy_rate_2g_mbps,
      )
      max_phy_rate_mbps = min(
          max_phy_rate_mbps,
          max_num_streams * nc_constants.MAX_PHY_RATE_PER_STREAM_N_20_MBPS,
      )
      min_throughput_mbyte_per_sec = int(
          max_phy_rate_mbps
          * nc_constants.MAX_PHY_RATE_TO_MIN_THROUGHPUT_RATIO_2G
          / _BITS_PER_BYTE
      )
      nc_min_throughput_mbyte_per_sec = min_throughput_mbyte_per_sec
    else:  # 5G wifi medium
      max_phy_rate_mbps = min(
          self.discoverer.max_phy_rate_5g_mbps,
          self.advertiser.max_phy_rate_5g_mbps,
      )
      # max_num_streams could be smaller in DBS mode
      if self._is_dbs_mode:
        max_num_streams = self.advertiser.max_num_streams_dbs

      max_phy_rate_ac80 = (
          max_num_streams * nc_constants.MAX_PHY_RATE_PER_STREAM_AC_80_MBPS
      )
      max_phy_rate_mbps = min(max_phy_rate_mbps, max_phy_rate_ac80)

      # if STA is connected to 5G AP with channel BW < 80,
      # limit the max phy rate to AC 40.
      if (
          sta_frequency > 5000
          and sta_max_link_speed_mbps > 0
          and sta_max_link_speed_mbps < max_phy_rate_ac80
      ):
        max_phy_rate_mbps = min(
            max_phy_rate_mbps,
            max_num_streams * nc_constants.MAX_PHY_RATE_PER_STREAM_AC_40_MBPS,
        )

      min_throughput_mbyte_per_sec = int(
          max_phy_rate_mbps
          * nc_constants.MAX_PHY_RATE_TO_MIN_THROUGHPUT_RATIO_5G
          / _BITS_PER_BYTE
      )
      if self._is_mcc:
        min_throughput_mbyte_per_sec = int(
            min_throughput_mbyte_per_sec
            * nc_constants.MCC_THROUGHPUT_MULTIPLIER
        )

      nc_min_throughput_mbyte_per_sec = min_throughput_mbyte_per_sec
      if (
          self._current_test_result.quality_info.upgrade_medium
          == nc_constants.NearbyConnectionMedium.WIFI_LAN
      ):
        nc_min_throughput_mbyte_per_sec = min(
            nc_min_throughput_mbyte_per_sec,
            nc_constants.WLAN_THROUGHPUT_CAP_MBPS,
        )


    self.advertiser.log.info(
        f'target STA freq = {sta_frequency}, '
        f'max STA speed (Mb/s): {sta_max_link_speed_mbps}, '
        f'max D2D speed (MB/s): {max_phy_rate_mbps / _BITS_PER_BYTE}, '
        f'min D2D speed (MB/s), iperf: {min_throughput_mbyte_per_sec}, '
        f'nc: {nc_min_throughput_mbyte_per_sec}'
    )
    return (min_throughput_mbyte_per_sec, nc_min_throughput_mbyte_per_sec)

  def _test_connection_medium_performance(
      self,
      upgrade_medium_under_test: nc_constants.NearbyMedium,
      wifi_ssid: str = '',  # used by discoverer and possibly advertiser
      wifi_password: str = '',  # used by discoverer and advertiser
      force_disable_bt_multiplex: bool = False,
      connection_medium: nc_constants.NearbyMedium = nc_constants.NearbyMedium.BT_ONLY,
      wifi_ssid2: str = '',  # used by advertiser if not empty
  ) -> None:
    """Test the D2D performance with the specified upgrade medium."""
    self._upgrade_medium_under_test = upgrade_medium_under_test
    self._connection_medium = connection_medium
    self._wifi_ssid = wifi_ssid

    if self.test_parameters.toggle_airplane_mode_target_side:
      setup_utils.toggle_airplane_mode(self.advertiser)
    advertising_discovery_medium = nc_constants.NearbyMedium(
        self.test_parameters.advertising_discovery_medium
    )
    self._advertising_discovery_medium = advertising_discovery_medium
    if self.test_parameters.reset_wifi_connection:
      self._reset_wifi_connection()
    # 1. discoverer connect to wifi STA/AP
    self._current_test_result = nc_constants.SingleTestResult()
    if wifi_ssid:
      self._active_nc_fail_reason = (
          nc_constants.SingleTestFailureReason.SOURCE_WIFI_CONNECTION
      )
      discoverer_wifi_sta_latency = (
          setup_utils.connect_to_wifi_sta_till_success(
              self.discoverer, wifi_ssid, wifi_password
          )
      )
      self._active_nc_fail_reason = nc_constants.SingleTestFailureReason.SUCCESS
      self.discoverer.log.info(
          'connecting to wifi in '
          f'{round(discoverer_wifi_sta_latency.total_seconds())} s'
      )
      self._current_test_result.discoverer_sta_expected = True
      self._current_test_result.discoverer_sta_latency = (
          discoverer_wifi_sta_latency
      )

    # 2. set up BT connection if required
    # Because target STA is not yet connected, discovery is done over BLE only.
    advertising_discovery_medium = nc_constants.NearbyMedium.BLE_ONLY

    connection_setup_timeouts = nc_constants.ConnectionSetupTimeouts(
        nc_constants.FIRST_DISCOVERY_TIMEOUT,
        nc_constants.FIRST_CONNECTION_INIT_TIMEOUT,
        nc_constants.FIRST_CONNECTION_RESULT_TIMEOUT,
    )
    prior_bt_snippet = None
    if (
        not force_disable_bt_multiplex
        and self.test_parameters.requires_bt_multiplex
    ):
      logging.info('set up a prior BT connection.')
      self._use_prior_bt = True
      prior_bt_snippet = nearby_connection_wrapper.NearbyConnectionWrapper(
          self.advertiser,
          self.discoverer,
          self.advertiser.nearby2,
          self.discoverer.nearby2,
          advertising_discovery_medium=nc_constants.NearbyMedium.BLE_ONLY,
          connection_medium=nc_constants.NearbyMedium.BT_ONLY,
          upgrade_medium=nc_constants.NearbyMedium.BT_ONLY,
      )

      try:
        prior_bt_snippet.start_nearby_connection(
            timeouts=connection_setup_timeouts,
            medium_upgrade_type=nc_constants.MediumUpgradeType.NON_DISRUPTIVE,
        )
      finally:
        self._prior_bt_nc_fail_reason = prior_bt_snippet.test_failure_reason
        self._current_test_result.prior_nc_quality_info = (
            prior_bt_snippet.connection_quality_info
        )

    # set up Wifi connection and transfer
    # 3. advertiser connect to wifi STA/AP
    wifi_ssid_advertiser = wifi_ssid
    if wifi_ssid2:
      wifi_ssid_advertiser = wifi_ssid2
    if wifi_ssid_advertiser:
      self._active_nc_fail_reason = (
          nc_constants.SingleTestFailureReason.TARGET_WIFI_CONNECTION
      )
      advertiser_wifi_sta_latency = (
          setup_utils.connect_to_wifi_sta_till_success(
              self.advertiser, wifi_ssid_advertiser, wifi_password
          )
      )
      self.advertiser.log.info(
          'connecting to wifi in '
          f'{round(advertiser_wifi_sta_latency.total_seconds())} s'
      )
      self.advertiser.log.info(
          self.advertiser.nearby.wifiGetConnectionInfo().get('mFrequency')
      )
      self._current_test_result.advertiser_wifi_expected = True
      self._current_test_result.advertiser_sta_latency = (
          advertiser_wifi_sta_latency
      )
      # Let scan, DHCP and internet validation complete before NC.
      # This is important especially for the transfer speed test.
      time.sleep(self.test_parameters.target_post_wifi_connection_idle_time_sec)

    # 4. set up the D2D nearby connection
    logging.info('set up a nearby connection for file transfer.')
    active_snippet = nearby_connection_wrapper.NearbyConnectionWrapper(
        self.advertiser,
        self.discoverer,
        self.advertiser.nearby,
        self.discoverer.nearby,
        advertising_discovery_medium=advertising_discovery_medium,
        connection_medium=connection_medium,
        upgrade_medium=upgrade_medium_under_test,
    )
    if prior_bt_snippet:
      connection_setup_timeouts = nc_constants.ConnectionSetupTimeouts(
          nc_constants.SECOND_DISCOVERY_TIMEOUT,
          nc_constants.SECOND_CONNECTION_INIT_TIMEOUT,
          nc_constants.SECOND_CONNECTION_RESULT_TIMEOUT,
      )
    try:
      active_snippet.start_nearby_connection(
          timeouts=connection_setup_timeouts,
          medium_upgrade_type=nc_constants.MediumUpgradeType.DISRUPTIVE,
          keep_alive_timeout_ms=self.test_parameters.keep_alive_timeout_ms,
          keep_alive_interval_ms=self.test_parameters.keep_alive_interval_ms,
      )
    finally:
      self._active_nc_fail_reason = active_snippet.test_failure_reason
      self._current_test_result.quality_info = (
          active_snippet.connection_quality_info
      )

    # 5. transfer file through the nearby connection and optionally run iperf
    try:
      self._current_test_result.file_transfer_throughput_kbps = (
          active_snippet.transfer_file(
              self._get_transfer_file_size(),
              self._get_file_transfer_timeout(),
              self.test_parameters.payload_type,
          )
      )
      if (
          self.test_parameters.run_iperf_test
          and not self._is_mcc
          and upgrade_medium_under_test
          in [
              nc_constants.NearbyMedium.UPGRADE_TO_WIFIDIRECT,
              nc_constants.NearbyMedium.UPGRADE_TO_WIFIHOTSPOT,
              nc_constants.NearbyMedium.WIFILAN_ONLY,
              nc_constants.NearbyMedium.WIFIAWARE_ONLY,
          ]
      ):
        # TODO: b/338094399 - update this part for the connection over WFD.
        self._current_test_result.iperf_throughput_kbps = (
            iperf_utils.run_iperf_test(
                self.discoverer,
                self.advertiser,
                self._current_test_result.quality_info.upgrade_medium,
            )
        )

    finally:
      self._active_nc_fail_reason = active_snippet.test_failure_reason
      self._check_ap_connection_and_speed(wifi_ssid_advertiser)

    # 6. disconnect prior BT connection if required
    if prior_bt_snippet:
      prior_bt_snippet.disconnect_endpoint()
    # 7. disconnect D2D active connection
    active_snippet.disconnect_endpoint()

  def _check_ap_connection_and_speed(self, wifi_ssid: str) -> None:
    (sta_frequency, max_link_speed_mbps) = (
        self._get_target_sta_frequency_and_max_link_speed()
    )
    self._current_test_result.sta_frequency = sta_frequency
    self._current_test_result.max_sta_link_speed_mbps = max_link_speed_mbps
    if wifi_ssid and(
        sta_frequency == nc_constants.INVALID_INT
        or max_link_speed_mbps == nc_constants.INVALID_INT
    ):
      self._active_nc_fail_reason = (
          nc_constants.SingleTestFailureReason.DISCONNECTED_FROM_AP
      )
      asserts.fail(
          'Target device is disconnected from AP. Check AP DHCP config.'
      )

    iperf_speed_min_mbps, nc_speed_min_mbps = self._get_throughput_benchmark(
        sta_frequency, max_link_speed_mbps
    )

    if wifi_ssid and not self._is_valid_sta_frequency(wifi_ssid, sta_frequency):
      self._active_nc_fail_reason = (
          nc_constants.SingleTestFailureReason.WRONG_AP_FREQUENCY
      )
      asserts.fail(f'AP is set to a wrong frequency {sta_frequency}')

    if (
        self._current_test_result.quality_info.upgrade_medium
        in [
            nc_constants.NearbyConnectionMedium.WIFI_DIRECT,
            nc_constants.NearbyConnectionMedium.WIFI_HOTSPOT,
        ]
    ):
      p2p_frequency = setup_utils.get_wifi_p2p_frequency(self.advertiser)
      self._current_test_result.quality_info.medium_frequency = p2p_frequency
      if all([
          p2p_frequency != nc_constants.INVALID_INT,
          p2p_frequency != sta_frequency,
          not self._is_mcc,
          not self._is_dbs_mode,
          nc_speed_min_mbps > 0,
      ]):
        self._active_nc_fail_reason = (
            nc_constants.SingleTestFailureReason.WRONG_P2P_FREQUENCY
        )
        asserts.fail(
            f'P2P frequeny ({p2p_frequency}) is different from STA frequency'
            f' ({sta_frequency}) in SCC test case. Check the device capability'
            ' configuration especially for DBS, DFS, indoor capabilities.'
        )
      if all([
          p2p_frequency != nc_constants.INVALID_INT,
          p2p_frequency == sta_frequency,
          self._is_mcc,
          nc_speed_min_mbps > 0,
      ]):
        self._active_nc_fail_reason = (
            nc_constants.SingleTestFailureReason.WRONG_P2P_FREQUENCY
        )
        asserts.fail(
            f'P2P frequeny ({p2p_frequency}) is same as STA frequency'
            f' ({sta_frequency}) in MCC test case. Check the device capability'
            ' configuration especially for DBS, DFS, indoor capabilities.'
        )

    if (
        self._active_nc_fail_reason
        is nc_constants.SingleTestFailureReason.SUCCESS
    ):
      iperf_speed_mbps = int(
          self._current_test_result.iperf_throughput_kbps / 1024
      )
      nc_speed_mbps = round(
          self._current_test_result.file_transfer_throughput_kbps / 1024, 2
      )

      if (nc_speed_mbps < nc_speed_min_mbps) or (
          iperf_speed_mbps > 0 and iperf_speed_mbps < iperf_speed_min_mbps
      ):
        self._active_nc_fail_reason = (
            nc_constants.SingleTestFailureReason.FILE_TRANSFER_THROUGHPUT_LOW
        )
        result_str = ''
        if iperf_speed_mbps > 0 and iperf_speed_mbps < iperf_speed_min_mbps:
          result_str = result_str + (
              f'iperf speed {iperf_speed_mbps} < target {iperf_speed_min_mbps}'
          )
        if nc_speed_mbps < nc_speed_min_mbps:
          result_str = result_str + (
              f' file speed {nc_speed_mbps} < target {nc_speed_min_mbps}'
          )
        self._throughput_low_string = result_str + ' MB/s'
        asserts.fail(self._throughput_low_string)

  def _is_valid_sta_frequency(self, wifi_ssid: str, sta_frequency: int) -> bool:
    if wifi_ssid == self.test_parameters.wifi_2g_ssid:
      return sta_frequency <= _MAX_FREQ_2G_MHZ
    elif wifi_ssid == self.test_parameters.wifi_5g_ssid:
      return sta_frequency > _MAX_FREQ_2G_MHZ and (
          sta_frequency < _MIN_FREQ_5G_DFS_MHZ
          or sta_frequency > _MAX_FREQ_5G_DFS_MHZ
      )
    else:  # 5G DFS band
      return (
          sta_frequency >= _MIN_FREQ_5G_DFS_MHZ
          and sta_frequency <= _MAX_FREQ_5G_DFS_MHZ
      )

  def _get_transfer_file_size(self) -> int:
    return nc_constants.TRANSFER_FILE_SIZE_500MB

  def _get_file_transfer_timeout(self) -> datetime.timedelta:
    return nc_constants.WIFI_500M_PAYLOAD_TRANSFER_TIMEOUT

  def _write_current_test_report(self) -> None:
    """Writes test report for each iteration."""
    self._current_test_result.test_iteration = self._finished_test_iteration
    self._finished_test_iteration += 1
    if (
        self._use_prior_bt
        and self._prior_bt_nc_fail_reason
        is not nc_constants.SingleTestFailureReason.SUCCESS
    ):
      self._current_test_result.is_failed_with_prior_bt = True
      self._current_test_result.failure_reason = self._prior_bt_nc_fail_reason
    else:
      self._current_test_result.failure_reason = self._active_nc_fail_reason
    result_message = self._get_current_test_result_message()
    self._current_test_result.result_message = result_message
    self._test_results.append(self._current_test_result)

    quality_info: list[Any] = []
    if self._use_prior_bt:
      quality_info.append(
          'prior_bt:'
          f'{self._current_test_result.prior_nc_quality_info.get_dict()}'
      )
    quality_info.append(
        'file_transfer:'
        f'{self._current_test_result.quality_info.get_dict()}'
    )
    quality_info.append(
        'speed: '
        f'{round(self._current_test_result.file_transfer_throughput_kbps/1024, 1)}'
        'MBps'
    )
    if self._current_test_result.iperf_throughput_kbps > 0:
      quality_info.append(
          'iperf: '
          f'{round(self._current_test_result.iperf_throughput_kbps/1024, 1)}'
          'MBps'
      )

    if self._current_test_result.discoverer_sta_expected:
      src_connection_latency = round(
          self._current_test_result.discoverer_sta_latency.total_seconds()
      )
      quality_info.append(f'src_sta: {src_connection_latency}s')
    if self._current_test_result.advertiser_wifi_expected:
      tgt_connection_latency = round(
          self._current_test_result.advertiser_sta_latency.total_seconds()
      )
      quality_info.append(f'tgt_sta: {tgt_connection_latency}s')

    test_report = {
        'result': result_message,
        'quality_info': quality_info,
    }

    self.discoverer.log.info(test_report)
    self.record_data({
        'Test Class': self.TAG,
        'Test Name': self.current_test_info.name,
        'properties': test_report,
    })

  def _get_current_test_result_message(self) -> str:
    if (
        self._use_prior_bt
        and self._prior_bt_nc_fail_reason
        is not nc_constants.SingleTestFailureReason.SUCCESS
    ):
      return ''.join([
          'FAIL (The prior BT connection): ',
          f'{self._prior_bt_nc_fail_reason.name} - ',
          nc_constants.COMMON_TRIAGE_TIP.get(self._prior_bt_nc_fail_reason),
      ])

    if (
        self._active_nc_fail_reason
        == nc_constants.SingleTestFailureReason.SUCCESS
    ):
      return 'PASS'
    if (
        self._active_nc_fail_reason
        == nc_constants.SingleTestFailureReason.SOURCE_WIFI_CONNECTION
    ):
      return ''.join([
          f'FAIL: {self._active_nc_fail_reason.name} - ',
          nc_constants.COMMON_TRIAGE_TIP.get(self._active_nc_fail_reason),
      ])

    if (
        self._active_nc_fail_reason
        is nc_constants.SingleTestFailureReason.WIFI_MEDIUM_UPGRADE
    ):
      return ''.join([
          f'FAIL: {self._active_nc_fail_reason.name} - ',
          self._get_medium_upgrade_failure_tip(),
      ])
    if (
        self._active_nc_fail_reason
        is nc_constants.SingleTestFailureReason.FILE_TRANSFER_FAIL
    ):
      return ''.join([
          f'{self._active_nc_fail_reason.name} - ',
          self._get_file_transfer_failure_tip(),
      ])
    if (
        self._active_nc_fail_reason
        is nc_constants.SingleTestFailureReason.FILE_TRANSFER_THROUGHPUT_LOW
    ):
      return ''.join([
          f'{self._active_nc_fail_reason.name} - ',
          self._get_throughput_low_tip(),
      ])

    return ''.join([
        f'{self._active_nc_fail_reason.name} - ',
        nc_constants.COMMON_TRIAGE_TIP.get(
            self._active_nc_fail_reason, 'UNKNOWN'
        ),
    ])

  def _get_medium_upgrade_failure_tip(self) -> str:
    return nc_constants.MEDIUM_UPGRADE_FAIL_TRIAGE_TIPS.get(
        self._upgrade_medium_under_test,
        f'unexpected upgrade medium - {self._upgrade_medium_under_test}',
    )

  @abc.abstractmethod
  def _get_file_transfer_failure_tip(self) -> str:
    pass

  @abc.abstractmethod
  def _get_throughput_low_tip(self) -> str:
    pass

  def _collect_current_test_metrics(self) -> None:
    """Collects test result metrics for each iteration."""
    if self._use_prior_bt:
      self._performance_test_metrics.prior_bt_discovery_latencies.append(
          self._current_test_result.prior_nc_quality_info.discovery_latency
      )
      self._performance_test_metrics.prior_bt_connection_latencies.append(
          self._current_test_result.prior_nc_quality_info.connection_latency
      )

    self._performance_test_metrics.file_transfer_discovery_latencies.append(
        self._current_test_result.quality_info.discovery_latency
    )
    self._performance_test_metrics.file_transfer_connection_latencies.append(
        self._current_test_result.quality_info.connection_latency
    )
    self._performance_test_metrics.upgraded_wifi_transfer_mediums.append(
        self._current_test_result.quality_info.upgrade_medium
    )
    self._performance_test_metrics.file_transfer_throughputs_kbps.append(
        self._current_test_result.file_transfer_throughput_kbps
    )
    self._performance_test_metrics.iperf_throughputs_kbps.append(
        self._current_test_result.iperf_throughput_kbps
    )
    self._performance_test_metrics.discoverer_wifi_sta_latencies.append(
        self._current_test_result.discoverer_sta_latency
    )
    self._performance_test_metrics.advertiser_wifi_sta_latencies.append(
        self._current_test_result.advertiser_sta_latency
    )
    if (
        self._current_test_result.quality_info.medium_upgrade_expected
    ):
      self._performance_test_metrics.medium_upgrade_latencies.append(
          self._current_test_result.quality_info.medium_upgrade_latency
      )

  def __convert_kbps_to_mbps(self, throughput_kbps: float) -> float:
    """Convert throughput from kbyte/s to mbyte/s."""
    return round(throughput_kbps / 1024, 1)

  def __get_transfer_stats(
      self,
      throughput_indicators: list[float],
  ) -> nc_constants.TestResultStats:
    """get the min, median and max throughput from iterations which finished file transfer."""
    filtered = [
        x
        for x in throughput_indicators
        if x != nc_constants.UNSET_THROUGHPUT_KBPS
    ]
    if not filtered:
      # all test cases are failed
      return nc_constants.TestResultStats(0, 0, 0, 0)
    # use the descenting order of the throughput
    filtered.sort(reverse=True)
    return nc_constants.TestResultStats(
        len(filtered),
        self.__convert_kbps_to_mbps(filtered[len(filtered) - 1]),
        self.__convert_kbps_to_mbps(
            filtered[int(len(filtered) * nc_constants.PERCENTILE_50_FACTOR)]
        ),
        self.__convert_kbps_to_mbps(filtered[0]),
    )

  def __get_latency_stats(
      self, latency_indicators: list[datetime.timedelta]
  ) -> nc_constants.TestResultStats:
    filtered = [
        latency.total_seconds()
        for latency in latency_indicators
        if latency != nc_constants.UNSET_LATENCY
    ]
    if not filtered:
      # All test cases are failed.
      return nc_constants.TestResultStats(0, 0, 0, 0)

    filtered.sort()

    percentile_50 = round(
        filtered[int(len(filtered) * nc_constants.PERCENTILE_50_FACTOR)],
        nc_constants.LATENCY_PRECISION_DIGITS,
    )
    return nc_constants.TestResultStats(
        len(filtered),
        round(filtered[0], nc_constants.LATENCY_PRECISION_DIGITS),
        percentile_50,
        round(
            filtered[len(filtered) - 1], nc_constants.LATENCY_PRECISION_DIGITS
        ),
    )

  # @typing.override
  def _summary_test_results(self) -> None:
    """Summarizes test results of all iterations."""
    success_count = sum(
        test_result.failure_reason
        == nc_constants.SingleTestFailureReason.SUCCESS
        for test_result in self._test_results
    )
    passed = success_count >= round(
        self.performance_test_iterations * nc_constants.SUCCESS_RATE_TARGET
    )
    final_result_message = (
        'PASS'
        if passed
        else (
            'FAIL: low successe rate: '
            f' {success_count / self.performance_test_iterations:.2%} is lower'
            f' than the target {nc_constants.SUCCESS_RATE_TARGET:.2%}'
        )
    )
    detailed_stats = [
        f'Required Iterations: {self.performance_test_iterations}',
        f'Finished Iterations: {len(self._test_results)}',
    ]
    detailed_stats.append('Failed Iterations:')
    detailed_stats.extend(self.__get_failed_iteration_messages())
    detailed_stats.append('File Transfer Connection Stats:')
    detailed_stats.extend(self.__get_file_transfer_connection_stats())

    if self._use_prior_bt:
      detailed_stats.append('Prior BT Connection Stats:')
      detailed_stats.extend(self.__get_prior_bt_connection_stats())

    self.record_data({
        'Test Class': self.TAG,
        'properties': {
            '01_test_result': final_result_message,
            '02_source_device': '\n'.join(
                self.__get_device_attributes(self.discoverer)
            ),
            '03_target_device': '\n'.join(
                self.__get_device_attributes(self.advertiser)
            ),
            '04_test_config': '\n'.join([
                f'Country Code: {self._get_country_code()}',
                f'MCC mode: {self._is_mcc}',
                f'2G medium {self._is_2g_d2d_wifi_medium}',
                f'DBS mode: {self._is_dbs_mode}',
                (
                    'advertising_discovery_medium:'
                    f' {self._advertising_discovery_medium.name}'
                ),
                f'connection_medium: {self._connection_medium.name}',
                f'upgrade_medium: {self._upgrade_medium_under_test.name}',
                f'wifi_ssid: {self._wifi_ssid}',
                f'Start time: {self._start_time}',
                f'End time: {datetime.datetime.now()}',
            ]),
            '05_detailed_stats': '\n'.join(detailed_stats),
        },
    })

    asserts.assert_true(passed, final_result_message)

  def __get_failed_iteration_messages(self) -> list[str]:
    stats = []
    for test_result in self._test_results:
      if (
          test_result.failure_reason
          is not nc_constants.SingleTestFailureReason.SUCCESS
      ):
        stats.append(
            f'- Iter: {test_result.test_iteration}: {test_result.start_time}'
            f' {test_result.result_message}\n'
            f' sta freq: {test_result.sta_frequency},'
            f' sta max link speed: {test_result.max_sta_link_speed_mbps},'
            f' used medium: {test_result.quality_info.get_medium_name()},'
            f' medium freq: {test_result.quality_info.medium_frequency}.'
        )

    if stats:
      return stats
    else:
      return ['  - NA']

  def __get_prior_bt_connection_stats(self) -> list[str]:
    if not self._use_prior_bt:
      return []
    discovery_latency_stats = self.__get_latency_stats(
        self._performance_test_metrics.prior_bt_discovery_latencies
    )
    connection_latency_stats = self.__get_latency_stats(
        self._performance_test_metrics.prior_bt_connection_latencies
    )
    return [
        (
            '  - Min / Median / Max Discovery Latency'
            f' ({discovery_latency_stats.success_count} discovery):'
            f' {discovery_latency_stats.min_val} /'
            f' {discovery_latency_stats.median_val} /'
            f' {discovery_latency_stats.max_val}s '
        ),
        (
            '  - Min / Median / Max Connection Latency'
            f' ({connection_latency_stats.success_count} connections):'
            f' {connection_latency_stats.min_val} /'
            f' {connection_latency_stats.median_val} /'
            f' {connection_latency_stats.max_val}s '
        ),
    ]

  def __get_file_transfer_connection_stats(self) -> list[str]:
    discovery_latency_stats = self.__get_latency_stats(
        self._performance_test_metrics.file_transfer_discovery_latencies
    )
    connection_latency_stats = self.__get_latency_stats(
        self._performance_test_metrics.file_transfer_connection_latencies
    )
    transfer_stats = self.__get_transfer_stats(
        self._performance_test_metrics.file_transfer_throughputs_kbps
    )
    iperf_stats = self.__get_transfer_stats(
        self._performance_test_metrics.iperf_throughputs_kbps
    )
    stats = [
        (
            '  - Min / Median / Max Discovery Latency'
            f' ({discovery_latency_stats.success_count} discovery):'
            f' {discovery_latency_stats.min_val} /'
            f' {discovery_latency_stats.median_val} /'
            f' {discovery_latency_stats.max_val}s '
        ),
        (
            '  - Min / Median / Max Connection Latency'
            f' ({connection_latency_stats.success_count} connections):'
            f' {connection_latency_stats.min_val} /'
            f' {connection_latency_stats.median_val} /'
            f' {connection_latency_stats.max_val}s '
        ),
        (
            '  - Min / Median / Max Speed'
            f' ({transfer_stats.success_count} transfer):'
            f' {transfer_stats.min_val} / {transfer_stats.median_val} /'
            f' {transfer_stats.max_val} MBps'
        ),
        (
            '  - Min / Median / Max iperf Speed'
            f' ({iperf_stats.success_count} transfer):'
            f' {iperf_stats.min_val} / {iperf_stats.median_val} /'
            f' {iperf_stats.max_val} MBps'
        ),
    ]
    if nc_constants.is_high_quality_medium(self._upgrade_medium_under_test):
      medium_upgrade_latency_stats = self.__get_latency_stats(
          self._performance_test_metrics.medium_upgrade_latencies
      )
      stats.extend([
          (
              '  - Min / Median / Max Upgrade Latency '
              f' ({medium_upgrade_latency_stats. success_count} upgrade):'
              f' {medium_upgrade_latency_stats.min_val} /'
              f' {medium_upgrade_latency_stats.median_val} /'
              f' {medium_upgrade_latency_stats.max_val}s '
          ),
          '  - Upgrade Medium Stats:',
      ])
      stats.extend(self._summary_upgraded_wifi_transfer_mediums())

    return stats

  def _summary_upgraded_wifi_transfer_mediums(self) -> list[str]:
    medium_counts = {}
    for (
        upgraded_medium
    ) in self._performance_test_metrics.upgraded_wifi_transfer_mediums:
      if upgraded_medium:
        medium_counts[upgraded_medium.name] = (
            medium_counts.get(upgraded_medium.name, 0) + 1
        )
    return [f'    - {name}: {count}' for name, count in medium_counts.items()]

  def __get_device_attributes(
      self, ad: android_device.AndroidDevice
  ) -> list[str]:
    return [
        f'Device Serial: {ad.serial}',
        f'Device Model: {ad.model}',
        f'Build: {ad.build_info}',
        f'Wifi chipset: {ad.wifi_chipset}',
        f'Wifi FW: {ad.adb.getprop("vendor.wlan.firmware.version")}',
        f'Supports 5G Wifi: {ad.supports_5g}',
        f'Supports DBS: {ad.supports_dbs_sta_wfd}',
        (
            'Enable STA DFS channel for peer network:'
            f' {ad.enable_sta_dfs_channel_for_peer_network}'
        ),
        (
            'Enable STA Indoor channel for peer network:'
            f' {ad.enable_sta_indoor_channel_for_peer_network}'
        ),
        f'Max num of streams: {ad.max_num_streams}',
        f'Max num of streams (DBS): {ad.max_num_streams_dbs}',
        f'Android Version: {ad.android_version}',
        f'GMS_version: {setup_utils.dump_gms_version(ad)}',
    ]
