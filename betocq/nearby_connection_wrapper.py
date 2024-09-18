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

"""Utils for handling Nearby Connection rpc."""

import datetime
import random
import time

from mobly import asserts
from mobly import utils
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import callback_handler_v2
from mobly.controllers.android_device_lib import snippet_client_v2
from mobly.snippet import callback_event

from betocq import nc_constants

# This number should be large enough to cover advertising interval, firmware
# scheduling timing interval and user action delay
ADV_TO_DISCOVERY_MAX_DELAY_SEC = 4
ADV_TO_DISCOVERY_MIN_DELAY_SEC = 3


class NearbyConnectionWrapper:
  """Wrapper for Nearby Connection Snippet Client Operations."""

  def __init__(
      self,
      advertiser: android_device.AndroidDevice,
      discoverer: android_device.AndroidDevice,
      advertiser_nearby: snippet_client_v2.SnippetClientV2,
      discoverer_nearby: snippet_client_v2.SnippetClientV2,
      advertising_discovery_medium: nc_constants.NearbyMedium = (
          nc_constants.NearbyMedium.BLE_ONLY
      ),
      connection_medium: nc_constants.NearbyMedium = (
          nc_constants.NearbyMedium.BT_ONLY
      ),
      upgrade_medium: nc_constants.NearbyMedium = (
          nc_constants.NearbyMedium.BT_ONLY
      ),
  ):
    self.advertiser = advertiser
    self.discoverer = discoverer
    self.service_id = utils.rand_ascii_str(8)
    self.advertising_discovery_medium = advertising_discovery_medium
    self.connection_medium = connection_medium
    self.upgrade_medium = upgrade_medium
    self.discoverer_nearby = discoverer_nearby
    self.advertiser_nearby = advertiser_nearby
    self.test_failure_reason = (
        nc_constants.SingleTestFailureReason.UNINITIALIZED
        )

    self.connection_quality_info: nc_constants.ConnectionSetupQualityInfo = (
        nc_constants.ConnectionSetupQualityInfo())

    self._advertiser_connection_lifecycle_callback: (
        callback_handler_v2.CallbackHandlerV2) = None
    self._discoverer_endpoint_discovery_callback: (
        callback_handler_v2.CallbackHandlerV2) = None
    self._discoverer_connection_lifecycle_callback: (
        callback_handler_v2.CallbackHandlerV2) = None
    self._advertiser_payload_callback: (
        callback_handler_v2.CallbackHandlerV2) = None
    self._discoverer_payload_callback: (
        callback_handler_v2.CallbackHandlerV2) = None
    self._advertiser_endpoint_id: str = None
    self._discoverer_endpoint_id: str = None

  def start_advertising(self) -> None:
    """Starts Nearby Connection advertising."""
    advertiser_callback = self.advertiser_nearby.startAdvertising(
        self.advertiser.serial,
        self.service_id,
        self.advertising_discovery_medium.value,
        self.upgrade_medium.value,
    )
    self.advertiser.log.info(
        f'Start advertising {self.advertising_discovery_medium.name}'
    )
    self._advertiser_connection_lifecycle_callback = advertiser_callback

  def start_discovery(
      self, timeout: datetime.timedelta, enable_target_discovery: bool = False
  ) -> None:
    """Starts Nearby Connection discovery."""
    self.discoverer.log.info(
        f'Start discovery {self.advertising_discovery_medium.name}'
    )
    self._discoverer_endpoint_discovery_callback = (
        self.discoverer_nearby.startDiscovery(
            self.service_id, self.advertising_discovery_medium.value
        )
    )

    if enable_target_discovery:
      self.advertiser.log.info(
          f'Start discovery {self.advertising_discovery_medium.name}'
      )
      self.advertiser_nearby.startDiscovery(
          self.service_id, self.advertising_discovery_medium.value
      )

    endpoint_found_event = (
        self._discoverer_endpoint_discovery_callback.waitAndGet(
            'onEndpointFound', timeout=timeout.total_seconds()
        )
    )
    endpoint_info = endpoint_found_event.data['discoveredEndpointInfo']
    self.connection_quality_info.discovery_latency = datetime.timedelta(
        microseconds=endpoint_found_event.data['discoveryTimeNs'] / 1_000
    )
    asserts.assert_equal(
        endpoint_info['endpointName'], self.advertiser.serial,
        'Received an unexpected endpoint during discovery: '
        f'{endpoint_found_event}')

    asserts.assert_equal(
        endpoint_info['serviceId'], self.service_id,
        f'Received an unexpected service id during discovery: '
        f'{endpoint_found_event}')
    self._advertiser_endpoint_id = endpoint_found_event.data['endpointId']

  def stop_advertising(self) -> None:
    """Stops Nearby Connection advertising."""
    self.advertiser_nearby.stopAdvertising()
    self.advertiser.log.info('Stop advertising')

  def stop_discovery(self, enable_target_discovery: bool = False) -> None:
    """Stops Nearby Connection discovery."""
    self.discoverer_nearby.stopDiscovery()
    self.discoverer.log.info('Stop discovery')
    if enable_target_discovery:
      self.advertiser_nearby.stopDiscovery()
      self.advertiser.log.info('Stop discovery')

  def request_connection(
      self,
      medium_upgrade_type: nc_constants.MediumUpgradeType,
      timeout: datetime.timedelta,
      keep_alive_timeout_ms: int = nc_constants.KEEP_ALIVE_TIMEOUT_BT_MS,
      keep_alive_interval_ms: int = nc_constants.KEEP_ALIVE_INTERVAL_BT_MS,
  ) -> None:
    """Requests Nearby Connection."""

    self.discoverer.log.info(
        'Start connection request with keep_alive_timeout_ms'
        f' {keep_alive_timeout_ms}'
    )
    self._discoverer_connection_lifecycle_callback = (
        self.discoverer_nearby.requestConnection(
            self.discoverer.serial,
            self._advertiser_endpoint_id,
            self.connection_medium.value,
            self.upgrade_medium.value,
            medium_upgrade_type.value,
            keep_alive_timeout_ms,
            keep_alive_interval_ms,
        )
    )

    d_connection_init_event = (
        self._discoverer_connection_lifecycle_callback.waitAndGet(
            'onConnectionInitiated', timeout.total_seconds()
        )
    )
    self.connection_quality_info.connection_latency = datetime.timedelta(
        microseconds=d_connection_init_event.data['connectionTimeNs'] / 1_000
    )

    d_connection_info = d_connection_init_event.data['connectionInfo']
    asserts.assert_false(
        d_connection_info['isIncomingConnection'],
        f'Received an incoming connection: {d_connection_init_event}'
        'but expected an outgoing connection')

    asserts.assert_equal(
        d_connection_info['endpointName'],
        self.advertiser.serial,
        f'Received an unexpected endpoint: {d_connection_init_event}')

    # wait for the advertiser connection initialized.
    a_connection_init_event = (
        self._advertiser_connection_lifecycle_callback.waitAndGet(
            'onConnectionInitiated', timeout=timeout.total_seconds()
        )
    )
    a_connection_info = a_connection_init_event.data['connectionInfo']
    asserts.assert_true(
        a_connection_info['isIncomingConnection'],
        f'Received an outgoing connection: {d_connection_init_event}'
        'but expected an incoming connection')

    asserts.assert_equal(
        a_connection_info['endpointName'],
        self.discoverer.serial,
        f'Received an unexpected endpoint: {a_connection_init_event}')

    self._discoverer_endpoint_id = a_connection_init_event.data['endpointId']

  def accept_connection(
      self, timeout: datetime.timedelta
  ) -> None:
    """Accepts Nearby Connection."""
    self._advertiser_payload_callback = (
        self.advertiser_nearby.acceptConnection(
            self._discoverer_endpoint_id
        )
    )
    self.advertiser.log.info('Start connection accept')
    self._discoverer_payload_callback = (
        self.discoverer_nearby.acceptConnection(
            self._advertiser_endpoint_id
        )
    )
    self.discoverer.log.info('Start connection accept')

    advertiser_connection_event = (
        self._advertiser_connection_lifecycle_callback.waitAndGet(
            'onConnectionResult', timeout=timeout.total_seconds()
        )
    )

    asserts.assert_true(
        advertiser_connection_event.data['isSuccess'],
        f'Received an unsuccessful event: {advertiser_connection_event}')

    asserts.assert_equal(
        advertiser_connection_event.data['endpointId'],
        self._discoverer_endpoint_id,
        f'Received an unexpected endpoint: {advertiser_connection_event}')

    discoverer_connection_event = (
        self._discoverer_connection_lifecycle_callback.waitAndGet(
            'onConnectionResult', timeout=timeout.total_seconds()
        )
    )
    asserts.assert_true(
        discoverer_connection_event.data['isSuccess'],
        f'Received an unsuccessful event: {discoverer_connection_event}')

    asserts.assert_equal(
        discoverer_connection_event.data['endpointId'],
        self._advertiser_endpoint_id,
        f'Received an unexpected endpoint: {discoverer_connection_event}')

    if nc_constants.is_high_quality_medium(self.upgrade_medium):
      self.test_failure_reason = (
          nc_constants.SingleTestFailureReason.WIFI_MEDIUM_UPGRADE
      )
      upgrade_start_time = datetime.datetime.now()
      wait_high_quality = True
      while wait_high_quality:
        discoverer_medium_upgrade_event = self._discoverer_connection_lifecycle_callback.waitAndGet(
            'onBandwidthChanged',
            nc_constants.CONNECTION_BANDWIDTH_CHANGED_TIMEOUT.total_seconds(),
        )
        self.discoverer.log.info(
            f'medium upgrade to {discoverer_medium_upgrade_event.data}'
        )
        if discoverer_medium_upgrade_event.data['isHighBwQuality']:
          wait_high_quality = False
          self.connection_quality_info.medium_upgrade_latency = (
              datetime.datetime.now() - upgrade_start_time)
          self.connection_quality_info.upgrade_medium = (
              nc_constants.NearbyConnectionMedium(
                  discoverer_medium_upgrade_event.data['medium']))
          self.connection_quality_info.medium_upgrade_expected = True
          self.discoverer.log.info(
              f'upgraded to high quality medium: '
              f'{self.connection_quality_info.upgrade_medium.name}')
        else:
          latency = datetime.datetime.now() - upgrade_start_time
          if latency >= nc_constants.CONNECTION_BANDWIDTH_CHANGED_TIMEOUT:
            raise TimeoutError('medium upgrade timeout')

  def disconnect_endpoint(self) -> None:
    """Disconnects Nearby Connection endpoint."""
    if self:
      self.discoverer_nearby.disconnectFromEndpoint(
          self._advertiser_endpoint_id
      )
      self.discoverer.log.info(
          f'Start disconnecting from endpoint: {self._advertiser_endpoint_id}'
      )
    else:
      self.discoverer.log.info('no nearby connecty setup yet')
      return nc_constants.OpResult(nc_constants.Result.SUCCESS)

    if self._discoverer_connection_lifecycle_callback is not None:
      disconnected_event = (
          self._discoverer_connection_lifecycle_callback.waitAndGet(
              'onDisconnected',
              timeout=nc_constants.DISCONNECTION_TIMEOUT.total_seconds(),
          )
      )
      asserts.assert_equal(
          disconnected_event.data['endpointId'],
          self._advertiser_endpoint_id,
          f'Receive unexpected event on disconnect: {disconnected_event}')
    self.discoverer.log.info(
        f'disconnected with endpoint: {self._advertiser_endpoint_id}'
    )

  def start_nearby_connection(
      self,
      timeouts: nc_constants.ConnectionSetupTimeouts,
      medium_upgrade_type: nc_constants.MediumUpgradeType = nc_constants.MediumUpgradeType.DEFAULT,
      keep_alive_timeout_ms: int = 0,
      keep_alive_interval_ms: int = 0,
      enable_target_discovery: bool = False,
  ) -> None:
    """Starts Nearby Connection between two Android devices."""
    self.test_failure_reason = (
        nc_constants.SingleTestFailureReason.TARGET_START_ADVERTISING)
    # Start advertising.
    self.start_advertising()
    # Add a random delay between adversting and discovery
    # to mimic the random delay between two devices' user action
    time.sleep(
        ADV_TO_DISCOVERY_MIN_DELAY_SEC
        + (ADV_TO_DISCOVERY_MAX_DELAY_SEC - ADV_TO_DISCOVERY_MIN_DELAY_SEC)
        * random.random()
    )

    self.test_failure_reason = (
        nc_constants.SingleTestFailureReason.SOURCE_START_DISCOVERY)
    # Start discovery.
    self.start_discovery(
        timeout=timeouts.discovery_timeout,
        enable_target_discovery=enable_target_discovery,
    )

    # Request connection.
    self.test_failure_reason = (
        nc_constants.SingleTestFailureReason.SOURCE_REQUEST_CONNECTION)
    self.request_connection(
        medium_upgrade_type=medium_upgrade_type,
        timeout=timeouts.connection_init_timeout,
        keep_alive_timeout_ms=keep_alive_timeout_ms,
        keep_alive_interval_ms=keep_alive_interval_ms)

    # Stop discovery.
    self.stop_discovery(enable_target_discovery=enable_target_discovery)

    # Accept connection.
    self.test_failure_reason = (
        nc_constants.SingleTestFailureReason.TARGET_ACCEPT_CONNECTION)
    self.accept_connection(timeout=timeouts.connection_result_timeout)

    # Stop advertising.
    self.stop_advertising()
    self.test_failure_reason = nc_constants.SingleTestFailureReason.SUCCESS

  def transfer_file(
      self,
      file_size_kb: int,
      timeout: datetime.timedelta,
      payload_type: nc_constants.PayloadType,
      num_files: int = nc_constants.TRANSFER_FILE_NUM_DEFAULT,
  ) -> float:
    """Sends payloads and returns the transfer speed in kilo byte per second."""
    try:
      self.test_failure_reason = (
          nc_constants.SingleTestFailureReason.FILE_TRANSFER_FAIL
      )
      self.discoverer.log.info(
          f'sending {num_files} payloads with type: {payload_type.name}'
      )
      transfer_speed_kbps = self._transfer_file(
          file_size_kb, timeout, payload_type, num_files
      )
      self.advertiser.log.info(f'{num_files} payloads received')
      self.test_failure_reason = nc_constants.SingleTestFailureReason.SUCCESS
    finally:
      # clean up
      utils.concurrent_exec(
          lambda nb: nb.transferFilesCleanup(),
          param_list=[[self.discoverer_nearby], [self.advertiser_nearby]],
          raise_on_exception=True)
    return transfer_speed_kbps

  def _transfer_file(
      self, file_size_kb: int, timeout: datetime.timedelta,
      payload_type: nc_constants.PayloadType,
      num_files: int = nc_constants.TRANSFER_FILE_NUM_DEFAULT,
  ) -> float:
    """Sends payloads and returns the transfer speed in kBS."""
    # Creates a file and send it to the advertiser.
    file_name = utils.rand_ascii_str(8)

    last_payload_id = self.discoverer_nearby.sendMultiplePayloadWithType(
        self._advertiser_endpoint_id,
        file_name,
        file_size_kb,
        payload_type,
        num_files,
    )

    asserts.assert_is_not_none(
        self._advertiser_payload_callback,
        'No nearby connection is set up, advertiser payload cb is none.')
    asserts.assert_is_not_none(
        self._discoverer_payload_callback,
        'No nearby connection is set up, discoverer payload cb is none.')
    def on_receive(event: callback_event.CallbackEvent) -> bool:
      return (
          event.data['endpointId'] == self._discoverer_endpoint_id
      )
    transfer_time_s = 0
    for _ in range(num_files):
      # Ensure the order of payload transfer events are the same on both sides.

      rx_received_event = self._advertiser_payload_callback.waitForEvent(
          'onPayloadReceived',
          predicate=on_receive,
          timeout=timeout.total_seconds())

      rx_transfer_event = self._advertiser_payload_callback.waitForEvent(
          'onPayloadTransferUpdate',
          predicate=lambda event: event.data['update']['isSuccess'],
          timeout=timeout.total_seconds())

      tx_transfer_event = self._discoverer_payload_callback.waitForEvent(
          'onPayloadTransferUpdate',
          predicate=lambda event: event.data['update']['isSuccess'],
          # and event.data['update']['payloadId'] == last_payload_id,
          timeout=timeout.total_seconds(),
      )
      tx_id = tx_transfer_event.data['update']['payloadId']
      rx_id_payload_received = rx_received_event.data['payload']['id']
      rx_id_transfer_update = rx_transfer_event.data['update']['payloadId']
      if payload_type == nc_constants.PayloadType.FILE:
        asserts.assert_equal(tx_id, rx_id_payload_received)
        asserts.assert_equal(tx_id, rx_id_transfer_update)
      if tx_id == last_payload_id:
        transfer_time_s = datetime.timedelta(
            microseconds=tx_transfer_event.data['transferTimeNs']
            / 1_000
        ).total_seconds()

    asserts.assert_true(transfer_time_s > 0, 'Transfer time is 0')
    return round(file_size_kb * num_files / transfer_time_s)
