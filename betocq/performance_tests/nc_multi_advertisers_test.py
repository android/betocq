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

"""Tests Nearby Connections performance when multiple advertisers nearby."""

import datetime
import statistics
import time

from mobly import asserts
from mobly import base_test
from mobly import test_runner
from mobly import records
from mobly import utils
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import callback_handler_v2

from google3.testing.mobly.platforms.android.utils import apk_utils
from betocq import nc_constants
from betocq import nearby_connection_wrapper

_NEARBY_SNIPPET_PACKAGE_NAME = 'com.google.android.nearby.mobly.snippet'
_WAIT_TIME_FOR_DISCOVERY = datetime.timedelta(seconds=25)

_REPEAT_COUNT = 100
_MAX_CONSECUTIVE_ERROR = 5


class NCMultiAdvertisersTest(base_test.BaseTestClass):
  """Nearby Connections multiple advertisers tests."""

  ads: list[android_device.AndroidDevice]

  def setup_class(self) -> None:
    self._sum_connection_time_sec = 0
    self._test_count = 0
    self._connection_time_list = []
    self.ads = self.register_controller(android_device, min_number=3)
    utils.concurrent_exec(
        self._setup_android_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    apk_utils.install(ad, self.user_params['mh_files']['nearby_snippet'][0])
    ad.load_snippet('nearby', _NEARBY_SNIPPET_PACKAGE_NAME)

  def setup_test(self):
    self.record_data({
        'Test Name': self.current_test_info.name,
        'properties': {
            'beto_team': 'Nearby Connections',
            'beto_feature': 'Nearby Connections',
        },
    })

  @base_test.repeat(
      count=_REPEAT_COUNT, max_consecutive_error=_MAX_CONSECUTIVE_ERROR
  )
  def test_multiple_advertiser_medium_ble_only(self) -> None:
    """Tests Nearby Connections with medium BLE only."""
    service_id = utils.rand_ascii_str(8)
    connection_medium = nc_constants.NearbyMedium.BLE_ONLY
    upgrade_medium = nc_constants.NearbyMedium.BLE_ONLY
    medium_upgrade_type = nc_constants.MediumUpgradeType.DEFAULT
    keep_alive_timeout_ms = nc_constants.KEEP_ALIVE_TIMEOUT_BT_MS
    keep_alive_interval_ms = nc_constants.KEEP_ALIVE_INTERVAL_BT_MS

    discoverer, *advertisers = self.ads

    # Start advertising.
    utils.concurrent_exec(
        self._start_advertising,
        param_list=[
            [ad, service_id, connection_medium, upgrade_medium]
            for ad in advertisers
        ],
        raise_on_exception=True,
    )

    # Start discovery.
    utils.concurrent_exec(
        self._start_discovery,
        param_list=[[ad, service_id, connection_medium] for ad in advertisers],
        raise_on_exception=True,
    )
    discovery_callback = self._start_discovery(
        discoverer, service_id, connection_medium
    )
    time.sleep(_WAIT_TIME_FOR_DISCOVERY.total_seconds())
    events = discovery_callback.getAll('onEndpointFound')

    # Check if the discoverer finds all advertisers.
    expected_advertisers = {ad.serial for ad in advertisers}
    actual_found_advertisers = {
        event.data['discoveredEndpointInfo']['endpointName'] for event in events
    }
    asserts.assert_equal(
        expected_advertisers,
        actual_found_advertisers,
        'The devices found were not what was expected. Expected:'
        f' {expected_advertisers}, Actual: {actual_found_advertisers}',
    )

    # Save advertisers' endpointId.
    advertisers_map = {ad.serial: ad for ad in advertisers}
    for event in events:
      endpoint_name = event.data['discoveredEndpointInfo']['endpointName']
      ad = advertisers_map.get(endpoint_name)
      ad.endpoint_id = event.data['endpointId']

    # Establish connection between discoverer and one of the advertisers.
    advertiser = advertisers[0]
    nearby_connection = nearby_connection_wrapper.NearbyConnectionWrapper(
        advertiser,
        discoverer,
        advertiser.nearby,
        discoverer.nearby,
        advertising_discovery_medium=connection_medium,
        connection_medium=connection_medium,
        upgrade_medium=upgrade_medium,
    )
    nearby_connection._advertiser_connection_lifecycle_callback = (
        advertiser.advertising_callback
    )
    nearby_connection._advertiser_endpoint_id = advertiser.endpoint_id
    connection_start_time = time.monotonic()
    nearby_connection.request_connection(
        medium_upgrade_type=medium_upgrade_type,
        timeout=nc_constants.FIRST_CONNECTION_INIT_TIMEOUT,
        keep_alive_timeout_ms=keep_alive_timeout_ms,
        keep_alive_interval_ms=keep_alive_interval_ms,
    )
    nearby_connection.accept_connection(
        timeout=nc_constants.FIRST_CONNECTION_RESULT_TIMEOUT
    )
    connection_time_sec = time.monotonic() - connection_start_time

    nearby_connection.disconnect_endpoint()

    self._sum_connection_time_sec += connection_time_sec
    self._test_count += 1
    self._connection_time_list.append(connection_time_sec)
    self.record_data({
        'Test Name': self.current_test_info.name,
        'properties': {
            'connection_time (sec)': connection_time_sec,
        },
    })

  def _start_advertising(
      self,
      ad: android_device.AndroidDevice,
      service_id: str,
      connection_medium: nc_constants.NearbyMedium,
      upgrade_medium: nc_constants.NearbyMedium,
  ) -> None:
    """Starts Nearby Connections advertising."""
    ad.nearby.bringToFront()
    ad.advertising_callback = ad.nearby.startAdvertising(
        ad.serial, service_id, connection_medium, upgrade_medium
    )
    ad.advertising_callback.waitAndGet('onSuccess')
    ad.log.info('Start advertising')

  def _start_discovery(
      self,
      ad: android_device.AndroidDevice,
      service_id: str,
      discovery_medium: nc_constants.NearbyMedium,
  ) -> callback_handler_v2.CallbackHandlerV2:
    """Starts Nearby Connections discovery."""
    discovery_callback = ad.nearby.startDiscovery(service_id, discovery_medium)
    ad.log.info(
        'Start discovery and wait for %s seconds to collect data',
        _WAIT_TIME_FOR_DISCOVERY.total_seconds(),
    )
    return discovery_callback

  def teardown_test(self) -> None:
    utils.concurrent_exec(
        lambda d: d.nearby.stopDiscovery(),
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )
    utils.concurrent_exec(
        lambda d: d.nearby.stopAdvertising(),
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )
    utils.concurrent_exec(
        lambda d: d.services.create_output_excerpts_all(self.current_test_info),
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

  def on_fail(self, record: records.TestResultRecord) -> None:
    android_device.take_bug_reports(
        self.ads,
        destination=self.current_test_info.output_path,
    )

  def teardown_class(self) -> None:
    self.record_data({
        'Test Class': self.TAG,
        'properties': {
            'avg_connection_time (sec)': (
                self._sum_connection_time_sec / self._test_count
            ),
            'max_connection_time (sec)': max(self._connection_time_list),
            'median_connection_time (sec)': statistics.median(
                self._connection_time_list
            ),
            'min_connection_time (sec)': min(self._connection_time_list),
        },
    })


if __name__ == '__main__':
  test_runner.main()
