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

"""Utils for handling Nearby Connection V3 rpc."""

import datetime
import logging

import random
import secrets

import time

from mobly import asserts
from mobly import utils
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import callback_handler_v2
from mobly.controllers.android_device_lib import snippet_client_v2
from mobly.snippet import callback_event

from betocq import constants
from betocq.nearby_connection import nc_constants

AUTH_PASSWORD_CHARS = '0123456789abcdefghijklmnopqrstuvwxyz'
AUTH_PASSWORD_LENGTH = 6

# This number should be large enough to cover advertising interval, firmware
# scheduling timing interval and user action delay
ADV_TO_DISCOVERY_MAX_DELAY_SEC = 4
ADV_TO_DISCOVERY_MIN_DELAY_SEC = 3

KEEP_DISCOVERY_ACTIVE_TIME_SEC = 5
WAIT_FOR_STOP_ADVERTISING_SEC = 2


class NearbyConnectionV3Wrapper:
  """Wrapper for Nearby Connection V3 Snippet Client Operations.

  Attributes:
    connection_quality_info: Information about the connection setup quality.
    test_failure_reason: The reason for the test failure.
  """

  def __init__(
      self,
      advertiser: android_device.AndroidDevice,
      discoverer: android_device.AndroidDevice,
      advertiser_nearby: snippet_client_v2.SnippetClientV2,
      discoverer_nearby: snippet_client_v2.SnippetClientV2,
      advertising_discovery_medium: constants.NearbyMedium = (
          constants.NearbyMedium.BLE_ONLY
      ),
      connection_medium: constants.NearbyMedium = (
          constants.NearbyMedium.BLE_ONLY
      ),
      upgrade_medium: constants.NearbyMedium = (
          constants.NearbyMedium.BLE_ONLY
      ),
  ):
    self._advertiser = advertiser
    self._discoverer = discoverer
    self._password = self._generate_auth_password()
    self._advertising_discovery_medium = advertising_discovery_medium
    self._connection_medium = connection_medium
    self._upgrade_medium = upgrade_medium
    self._discoverer_nearby = discoverer_nearby
    self._advertiser_nearby = advertiser_nearby
    self.connection_quality_info: constants.ConnectionSetupQualityInfo = (
        constants.ConnectionSetupQualityInfo()
    )
    # Explicit assert to help static analyzer
    assert isinstance(
        self.connection_quality_info, constants.ConnectionSetupQualityInfo
    )
    self.test_failure_reason = constants.SingleTestFailureReason.UNINITIALIZED

    self._advertiser_connection_lifecycle_callback: (
        callback_handler_v2.CallbackHandlerV2
    ) = None  # pyrefly: ignore[bad-assignment]
    self._discoverer_endpoint_discovery_callback: (
        callback_handler_v2.CallbackHandlerV2
    ) = None  # pyrefly: ignore[bad-assignment]
    self._discoverer_connection_lifecycle_callback: (
        callback_handler_v2.CallbackHandlerV2
    ) = None  # pyrefly: ignore[bad-assignment]
    self._advertiser_payload_callback: (
        callback_handler_v2.CallbackHandlerV2
    ) = None  # pyrefly: ignore[bad-assignment]
    self._discoverer_payload_callback: (
        callback_handler_v2.CallbackHandlerV2
    ) = None  # pyrefly: ignore[bad-assignment]
    self._advertiser_endpoint_id: str = None  # pyrefly: ignore[bad-assignment]
    self._discoverer_endpoint_id: str = None  # pyrefly: ignore[bad-assignment]
    self._endpoint_info: bytearray = None  # pyrefly: ignore[bad-assignment]

  def start_advertising(
      self,
      supported_services: int,  # Handled as int here
      timeout: datetime.timedelta,
  ) -> None:
    """Starts V3 Connection advertising."""
    if self._advertiser_connection_lifecycle_callback is not None:
      raise ValueError('Advertiser lifecycle callback is already active.')
    advertiser_callback = self._advertiser_nearby.startAdvertisingV3(
        self._password,
        self._advertising_discovery_medium.value,
        self._upgrade_medium.value,
        supported_services,
    )
    self._advertiser.log.info(
        'Start advertising V3 %s', self._advertising_discovery_medium.name
    )
    endpoint_id_rotated_event = advertiser_callback.waitAndGet(
        'onEndpointIdRotated',
        timeout=timeout.total_seconds(),
    )
    self._advertiser_endpoint_id = endpoint_id_rotated_event.data[
        'newEndpointId'
    ]
    self._advertiser_connection_lifecycle_callback = advertiser_callback

  def start_discovery(
      self,
      supported_services: int,
      timeout: datetime.timedelta,
  ) -> None:
    """Starts V3 Connection discovery."""
    self._discoverer.log.info(
        'Start discovery V3 %s', self._advertising_discovery_medium.name
    )
    if self._discoverer_endpoint_discovery_callback is not None:
      raise ValueError('Discoverer discovery callback is already active.')
    self._discoverer_endpoint_discovery_callback = (
        self._discoverer_nearby.startDiscoveryV3(
            self._advertising_discovery_medium.value, supported_services
        )
    )

    device_found_event = (
        self._discoverer_endpoint_discovery_callback.waitForEvent(
            'onDeviceFound',
            predicate=lambda event: event.data['endpointId']
            == self._advertiser_endpoint_id,
            timeout=timeout.total_seconds(),
        )
    )
    self._endpoint_info = device_found_event.data['endpointInfo']
    self.connection_quality_info.discovery_latency = datetime.timedelta(  # pyrefly: ignore[bad-assignment]
        microseconds=device_found_event.data['discoveryTimeNs'] / 1_000
    )

  def stop_advertising(self) -> None:
    """Stops V3 Connection advertising."""
    self._advertiser_nearby.stopAdvertisingV3()
    self._advertiser.log.info('Stop advertising V3')

  def stop_discovery(self) -> None:
    """Stops V3 Connection discovery."""
    self._discoverer_nearby.stopDiscoveryV3()
    self._discoverer.log.info('Stop discovery V3')

  def request_connection(
      self,
      medium_upgrade_type: constants.MediumUpgradeType,
      timeout: datetime.timedelta,
  ) -> None:
    """Requests V3 Connection."""

    if self._discoverer_connection_lifecycle_callback is not None:
      raise ValueError('Discoverer lifecycle callback is already active.')
    self._discoverer.log.info('Start connection request V3')
    self._discoverer_connection_lifecycle_callback = (
        self._discoverer_nearby.requestConnectionV3(
            self._endpoint_info,
            self._advertiser_endpoint_id,
            self._password,
            self._connection_medium.value,
            self._upgrade_medium.value,
            medium_upgrade_type.value,
        )
    )

    d_connection_init_event = (
        self._discoverer_connection_lifecycle_callback.waitAndGet(
            'onConnectionInitiated', timeout.total_seconds()
        )
    )
    self.connection_quality_info.connection_latency = datetime.timedelta(  # pyrefly: ignore[bad-assignment]
        microseconds=d_connection_init_event.data['connectionTimeNs'] / 1_000
    )

    d_connection_info = d_connection_init_event.data['connectionInfo']
    asserts.assert_false(
        d_connection_info['isIncomingConnection'],
        'Source device received an incoming connection:'
        f' {d_connection_init_event}but expected an outgoing connection',
    )

    # wait for the advertiser connection initialized.
    a_connection_init_event = (
        self._advertiser_connection_lifecycle_callback.waitAndGet(
            'onConnectionInitiated', timeout=timeout.total_seconds()
        )
    )
    a_connection_info = a_connection_init_event.data['connectionInfo']
    asserts.assert_true(
        a_connection_info['isIncomingConnection'],
        'Target device received an outgoing connection:'
        f' {d_connection_init_event} but expected an incoming connection',
    )

    self._discoverer_endpoint_id = a_connection_init_event.data['endpointId']

  def accept_connection(self, timeout: datetime.timedelta) -> None:
    """Accepts V3 Connection."""
    if self._advertiser_payload_callback is not None:
      raise ValueError('Advertiser payload callback is already active.')
    self._advertiser_payload_callback = (
        self._advertiser_nearby.acceptConnectionV3(
            self._discoverer_endpoint_id,
            self._endpoint_info,
        )
    )
    self._advertiser.log.info('Start connection accept V3')
    if self._discoverer_payload_callback is not None:
      raise ValueError('Discoverer payload callback is already active.')
    self._discoverer_payload_callback = (
        self._discoverer_nearby.acceptConnectionV3(
            self._advertiser_endpoint_id,
            self._endpoint_info,
        )
    )
    self._discoverer.log.info('Start connection accept V3')

    advertiser_connection_event = (
        self._advertiser_connection_lifecycle_callback.waitAndGet(
            'onConnectionResult', timeout=timeout.total_seconds()
        )
    )

    asserts.assert_true(
        advertiser_connection_event.data['isSuccess'],
        'Target device received an unsuccessful event:'
        f' {advertiser_connection_event}',
    )

    asserts.assert_equal(
        advertiser_connection_event.data['endpointId'],
        self._discoverer_endpoint_id,
        'Target device received an unexpected endpoint:'
        f' {advertiser_connection_event}',
    )

    discoverer_connection_event = (
        self._discoverer_connection_lifecycle_callback.waitAndGet(
            'onConnectionResult', timeout=timeout.total_seconds()
        )
    )
    asserts.assert_true(
        discoverer_connection_event.data['isSuccess'],
        'Source device received an unsuccessful event:'
        f' {discoverer_connection_event}',
    )

    asserts.assert_equal(
        discoverer_connection_event.data['endpointId'],
        self._advertiser_endpoint_id,
        'Source device received an unexpected endpoint:'
        f' {discoverer_connection_event}',
    )

    discoverer_medium_connection_event = (
        self._discoverer_connection_lifecycle_callback.waitAndGet(
            'onBandwidthChanged',
            constants.CONNECTION_BANDWIDTH_CHANGED_TIMEOUT.total_seconds(),
        )
    )

    self.connection_quality_info.connection_medium = (
        self._connection_medium.to_connection_medium()
    )
    self.connection_quality_info.upgrade_medium = (
        constants.NearbyConnectionMedium(  # pyrefly: ignore[bad-assignment]
            discoverer_medium_connection_event.data['medium']
        )
    )
    self.connection_quality_info.medium_upgrade_latency = datetime.timedelta(  # pyrefly: ignore[bad-assignment]
        microseconds=discoverer_medium_connection_event.data['upgradeTimeNs']
        / 1_000
    )

    if not constants.is_high_quality_medium(self._upgrade_medium):
      return

    if discoverer_medium_connection_event.data['isHighBwQuality']:
      self.connection_quality_info.medium_upgrade_expected = True  # pyrefly: ignore[bad-assignment]
      return

    self.test_failure_reason = (
        constants.SingleTestFailureReason.WIFI_MEDIUM_UPGRADE  # pyrefly: ignore[bad-assignment]
    )
    upgrade_start_time = time.monotonic()
    end_time = (
        time.monotonic()
        + constants.CONNECTION_BANDWIDTH_CHANGED_TIMEOUT.total_seconds()
    )
    while time.monotonic() < end_time:
      discoverer_medium_upgrade_event = (
          self._discoverer_connection_lifecycle_callback.waitAndGet(
              'onBandwidthChanged',
              constants.CONNECTION_BANDWIDTH_CHANGED_TIMEOUT.total_seconds(),
          )
      )
      self._discoverer.log.info(
          'medium upgrade to %s', discoverer_medium_upgrade_event.data
      )
      if discoverer_medium_upgrade_event.data['isHighBwQuality']:
        self.connection_quality_info.medium_upgrade_latency = (
            datetime.timedelta(  # pyrefly: ignore[bad-assignment]
                               seconds=time.monotonic() - upgrade_start_time
            )
        )
        self.connection_quality_info.upgrade_medium = (
            constants.NearbyConnectionMedium(  # pyrefly: ignore[bad-assignment]
                discoverer_medium_upgrade_event.data['medium']
            )
        )
        self.connection_quality_info.medium_upgrade_expected = True  # pyrefly: ignore[bad-assignment]
        self._discoverer.log.info(
            'upgraded to high quality medium: %s',
            self.connection_quality_info.upgrade_medium.name,
        )
        break
    else:
      raise TimeoutError('medium upgrade timeout')

  def disconnect_endpoint(self) -> None:
    """Disconnects V3 Connection endpoint."""
    try:
      if self._discoverer_endpoint_id is not None:
        self._discoverer_nearby.disconnectFromDeviceV3(
            self._advertiser_endpoint_id,
            self._endpoint_info,
        )
        self._discoverer.log.info(
            'Start disconnecting from endpoint V3: %s',
            self._advertiser_endpoint_id,
        )

        if self._discoverer_connection_lifecycle_callback is not None:
          disconnected_event = (
              self._discoverer_connection_lifecycle_callback.waitAndGet(
                  'onDisconnected',
                  timeout=constants.DISCONNECTION_TIMEOUT.total_seconds(),
              )
          )
          asserts.assert_equal(
              disconnected_event.data['endpointId'],
              self._advertiser_endpoint_id,
              'Source device received unexpected event on disconnect:'
              f' {disconnected_event}',
          )
        if self._advertiser_connection_lifecycle_callback is not None:
          disconnected_event = (
              self._advertiser_connection_lifecycle_callback.waitAndGet(
                  'onDisconnected',
                  timeout=constants.DISCONNECTION_TIMEOUT.total_seconds(),
              )
          )
          asserts.assert_equal(
              disconnected_event.data['endpointId'],
              self._discoverer_endpoint_id,
              'Target device received unexpected event on disconnect:'
              f' {disconnected_event}',
          )
        self._discoverer.log.info(
            'disconnected with endpoint: %s', self._advertiser_endpoint_id
        )
      else:
        self._discoverer.log.info('no nearby connection setup yet')
    finally:
      self._advertiser_connection_lifecycle_callback = None  # pyrefly: ignore[bad-assignment]
      self._discoverer_connection_lifecycle_callback = None  # pyrefly: ignore[bad-assignment]
      self._discoverer_endpoint_discovery_callback = None  # pyrefly: ignore[bad-assignment]
      self._advertiser_payload_callback = None  # pyrefly: ignore[bad-assignment]
      self._discoverer_payload_callback = None  # pyrefly: ignore[bad-assignment]

  def start_nearby_connection(
      self,
      timeouts: constants.ConnectionSetupTimeouts,
      medium_upgrade_type: constants.MediumUpgradeType = (
          constants.MediumUpgradeType.DEFAULT
      ),
      supported_services: int = 1,  # Default or something appropriate
      simulate_address_rotation: bool = False,
      keep_enabling_discovery: bool = False,
  ) -> None:
    """Starts V3 Connection between two Android devices."""
    if timeouts.connection_init_timeout is None:
      raise ValueError('connection_init_timeout is required')
    if timeouts.discovery_timeout is None:
      raise ValueError('discovery_timeout is required')
    if timeouts.connection_result_timeout is None:
      raise ValueError('connection_result_timeout is required')

    self.test_failure_reason = (
        constants.SingleTestFailureReason.TARGET_START_ADVERTISING
    )
    # Start advertising.
    self.start_advertising(
        supported_services, timeout=timeouts.connection_init_timeout
    )
    # Add a random delay between adversting and discovery
    # to mimic the random delay between two devices' user action
    time.sleep(
        ADV_TO_DISCOVERY_MIN_DELAY_SEC
        + (ADV_TO_DISCOVERY_MAX_DELAY_SEC - ADV_TO_DISCOVERY_MIN_DELAY_SEC)
        * random.random()
    )

    self.test_failure_reason = (
        constants.SingleTestFailureReason.SOURCE_START_DISCOVERY
    )
    # Start discovery.
    self.start_discovery(
        supported_services=supported_services,
        timeout=timeouts.discovery_timeout,
    )

    # Request connection.
    self.test_failure_reason = (
        constants.SingleTestFailureReason.SOURCE_REQUEST_CONNECTION
    )

    if not keep_enabling_discovery:
      self.stop_discovery()

    if simulate_address_rotation:
      self._simulate_address_rotation(
          supported_services, timeout=timeouts.connection_init_timeout
      )

    self.request_connection(
        medium_upgrade_type=medium_upgrade_type,
        timeout=timeouts.connection_init_timeout,
    )

    # Accept connection.
    self.test_failure_reason = (
        constants.SingleTestFailureReason.TARGET_ACCEPT_CONNECTION
    )
    self.accept_connection(timeout=timeouts.connection_result_timeout)

    # Stop advertising.
    self.stop_advertising()

    if keep_enabling_discovery:
      # Sleep to ensure performance is observed while discovery
      # is active.
      time.sleep(KEEP_DISCOVERY_ACTIVE_TIME_SEC)
      self.stop_discovery()

    self.test_failure_reason = constants.SingleTestFailureReason.SUCCESS

  def transfer_file(
      self,
      payload_size_kb: int,
      timeout: datetime.timedelta,
      payload_type: constants.PayloadType | nc_constants.V3PayloadType,
      response_payload_type: nc_constants.V3PayloadType = (
          nc_constants.V3PayloadType.REQUEST
      ),
      num_files: int = constants.TRANSFER_FILE_NUM_DEFAULT,
      response_size_kb: int = 0,
      part_type: nc_constants.PartType = nc_constants.PartType.SINGLE_PART,
      part_number: int = 1,
      concurrent_requests_num: int = 1,
  ) -> float:
    """Sends payloads and returns the transfer speed in kilo byte per second."""
    try:
      self.test_failure_reason = (
          constants.SingleTestFailureReason.FILE_TRANSFER_FAIL
      )
      if isinstance(payload_type, nc_constants.V3PayloadType):
        if concurrent_requests_num == 1:
          transfer_speed_kbps = self._send_request_payload(
              payload_size_kb,
              response_size_kb,
              response_payload_type,
              part_type,
              part_number,
              timeout,
          )
        else:
          transfer_speed_kbps = self._send_concurrent_requests(
              payload_size_kb,
              response_size_kb,
              response_payload_type,
              part_type,
              part_number,
              timeout,
              concurrent_requests_num,
          )
      else:
        self._discoverer.log.info(
            'sending %s payloads with type: %s and size: %s kB',
            num_files,
            payload_type.name,
            payload_size_kb,
        )
        transfer_speed_kbps = self._transfer_file(
            payload_size_kb, timeout, payload_type, num_files
        )
        self._advertiser.log.info('%s payloads received', num_files)

      self.test_failure_reason = constants.SingleTestFailureReason.SUCCESS
    finally:
      # clean up
      utils.concurrent_exec(
          lambda nb: nb.transferFilesCleanupV3(),
          param_list=[[self._discoverer_nearby], [self._advertiser_nearby]],
          raise_on_exception=True,
      )
    return transfer_speed_kbps

  def _send_request_payload(
      self,
      request_size_kb: int,
      response_size_kb: int,
      response_payload_type: nc_constants.V3PayloadType,
      part_type: nc_constants.PartType,
      part_number: int,
      timeout: datetime.timedelta,
  ) -> float:
    """Sends request, receives response and returns the response payload
    transfer speed in kBS."""
    self._advertiser.log.info(
        'sending REQUEST payload with request size: %s kB and '
        'response size: %s kB',
        request_size_kb,
        response_size_kb,
    )
    if response_size_kb > 0:
      self._discoverer_nearby.setResponseParamsV3(
          response_size_kb,
          response_payload_type.value,
          part_type.value,
          part_number,
      )
    self._advertiser_nearby.sendRequestPayloadV3(
        self._discoverer_endpoint_id, self._endpoint_info, request_size_kb
    )
    asserts.assert_is_not_none(
        self._advertiser_payload_callback,
        'No V3 connection is set up, advertiser payload cb is none.',
    )
    asserts.assert_is_not_none(
        self._discoverer_payload_callback,
        'No V3 connection is set up, discoverer payload cb is none.',
    )

    rx_received_event = self._discoverer_payload_callback.waitForEvent(
        'onPayloadReceived',
        predicate=lambda event: event.data['endpointId']
        == self._advertiser_endpoint_id,
        timeout=timeout.total_seconds(),
    )
    self._discoverer.log.info('rx_received_event: %s', rx_received_event)

    rx_payload_id = rx_received_event.data['payload']['id']
    rx_transfer_event = self._discoverer_payload_callback.waitForEvent(
        'onPayloadTransferUpdate',
        predicate=lambda event: event.data['update']['payloadId']
        == rx_payload_id
        and event.data['endpointId'] == self._advertiser_endpoint_id,
        timeout=timeout.total_seconds(),
    )
    self._discoverer.log.info('rx_transfer_event: %s', rx_transfer_event)
    asserts.assert_true(
        rx_transfer_event.data['update']['isSuccess'],
        f'Request payload transfer failed for payload {rx_payload_id}',
    )

    tx_received_event = self._advertiser_payload_callback.waitForEvent(
        'onPayloadReceived',
        predicate=lambda event: event.data['endpointId']
        == self._discoverer_endpoint_id,
        timeout=timeout.total_seconds(),
    )
    self._advertiser.log.info('tx_received_event: %s', tx_received_event)
    tx_payload_id = tx_received_event.data['payload']['id']
    tx_transfer_event = self._discoverer_payload_callback.waitForEvent(
        'onPayloadTransferUpdate',
        predicate=lambda event: event.data['update']['payloadId']
        == tx_payload_id
        and event.data['endpointId'] == self._advertiser_endpoint_id,
        timeout=timeout.total_seconds(),
    )
    self._discoverer.log.info('tx_transfer_event: %s', tx_transfer_event)
    asserts.assert_true(
        tx_transfer_event.data['update']['isSuccess'],
        f'Response payload transfer failed for payload {tx_payload_id}',
    )

    transfer_time_s = datetime.timedelta(
        microseconds=tx_transfer_event.data['transferTimeNs'] / 1_000
    ).total_seconds()

    asserts.assert_greater(transfer_time_s, 0, 'Transfer time is 0')
    return round(response_size_kb * part_number / transfer_time_s)

  def _send_concurrent_requests(
      self,
      request_size_kb: int,
      response_size_kb: int,
      response_payload_type: nc_constants.V3PayloadType,
      part_type: nc_constants.PartType,
      part_number: int,
      timeout: datetime.timedelta,
      concurrent_requests_num: int,
  ) -> float:
    """Send multiple requests concurrently and calculate the average
    throughput."""
    if response_size_kb == 0:
      return 0.0

    self._discoverer_nearby.setResponseParamsV3(
        response_size_kb,
        response_payload_type.value,
        part_type.value,
        part_number,
    )

    self._advertiser.log.info(
        'sending %s concurrent requests with request size: %s kB and response'
        ' size: %s kB',
        concurrent_requests_num,
        request_size_kb,
        response_size_kb,
    )

    utils.concurrent_exec(
        lambda _: self._advertiser_nearby.sendRequestPayloadV3(
            self._discoverer_endpoint_id, self._endpoint_info, request_size_kb
        ),
        param_list=[[i] for i in range(concurrent_requests_num)],
        raise_on_exception=True,
    )

    request_payload_ids = []
    for _ in range(concurrent_requests_num):
      rx_received_event = self._discoverer_payload_callback.waitForEvent(
          'onPayloadReceived',
          predicate=lambda event: event.data['endpointId']
          == self._advertiser_endpoint_id,
          timeout=timeout.total_seconds(),
      )
      self._discoverer.log.info('rx_received_event: %s', rx_received_event)
      request_payload_ids.append(rx_received_event.data['payload']['id'])

    for payload_id in request_payload_ids:
      rx_transfer_event = self._discoverer_payload_callback.waitForEvent(
          'onPayloadTransferUpdate',
          predicate=lambda event, pid=payload_id: event.data['update'][
              'payloadId'
          ]
          == pid
          and event.data['endpointId'] == self._advertiser_endpoint_id,
          timeout=timeout.total_seconds(),
      )
      self._discoverer.log.info('rx_transfer_event: %s', rx_transfer_event)
      asserts.assert_true(
          rx_transfer_event.data['update']['isSuccess'],
          'Request payload transfer failed on discoverer for payload'
          f' {rx_transfer_event.data["update"]["payloadId"]}',
      )

    for _ in range(concurrent_requests_num):
      tx_received_event = self._advertiser_payload_callback.waitForEvent(
          'onPayloadReceived',
          predicate=lambda event: event.data['endpointId']
          == self._discoverer_endpoint_id,
          timeout=timeout.total_seconds(),
      )
      self._advertiser.log.info('tx_received_event: %s', tx_received_event)


    throughputs = []
    for _ in range(concurrent_requests_num):
      tx_transfer_event = self._discoverer_payload_callback.waitForEvent(
          'onPayloadTransferUpdate',
          predicate=lambda event: event.data['endpointId']
          == self._advertiser_endpoint_id,
          timeout=timeout.total_seconds(),
      )
      self._discoverer.log.info('tx_transfer_event: %s', tx_transfer_event)

      if tx_transfer_event.data['update']['isSuccess']:
        transfer_time_s = datetime.timedelta(
            microseconds=tx_transfer_event.data['transferTimeNs'] / 1_000
        ).total_seconds()
        asserts.assert_greater(transfer_time_s, 0, 'Transfer time is 0')
        throughputs.append(
            round(response_size_kb * part_number / transfer_time_s)
        )
      else:
        asserts.fail(
            'Response payload transfer failed on discoverer for payload'
            f' {tx_transfer_event.data["update"]["payloadId"]}'
        )
    return sum(throughputs) / len(throughputs) if throughputs else 0.0

  def _transfer_file(
      self,
      file_size_kb: int,
      timeout: datetime.timedelta,
      payload_type: constants.PayloadType,
      num_files: int = constants.TRANSFER_FILE_NUM_DEFAULT,
  ) -> float:
    """Sends payloads and returns the transfer speed in kBS."""
    # Creates a file and send it to the advertiser.
    file_name = utils.rand_ascii_str(8)

    last_payload_id = self._discoverer_nearby.sendMultiplePayloadWithTypeV3(
        self._advertiser_endpoint_id,
        self._endpoint_info,
        file_name,
        file_size_kb,
        payload_type.value,  # Assuming payload_type has value
        num_files,
    )

    asserts.assert_is_not_none(
        self._advertiser_payload_callback,
        'No V3 connection is set up, advertiser payload cb is none.',
    )
    asserts.assert_is_not_none(
        self._discoverer_payload_callback,
        'No V3 connection is set up, discoverer payload cb is none.',
    )

    def on_advertiser_receive(event: callback_event.CallbackEvent) -> bool:
      return event.data['endpointId'] == self._discoverer_endpoint_id

    def on_discoverer_receive(event: callback_event.CallbackEvent) -> bool:
      return event.data['endpointId'] == self._advertiser_endpoint_id

    transfer_time_s = 0
    for _ in range(num_files):
      tx_transfer_event = self._discoverer_payload_callback.waitForEvent(
          'onPayloadTransferUpdate',
          predicate=on_discoverer_receive,
          timeout=timeout.total_seconds(),
      )
      asserts.assert_true(
          tx_transfer_event.data['update']['isSuccess'],
          'file transfer failure reported on the source side for payload id:'
          f' {tx_transfer_event.data["update"]["payloadId"]}',
      )

      rx_transfer_event = self._advertiser_payload_callback.waitForEvent(
          'onPayloadTransferUpdate',
          predicate=on_advertiser_receive,
          timeout=timeout.total_seconds(),
      )
      asserts.assert_true(
          rx_transfer_event.data['update']['isSuccess'],
          'file transfer failure reported on the target side for payload id:'
          f' {rx_transfer_event.data["update"]["payloadId"]}',
      )

      rx_received_event = self._advertiser_payload_callback.waitForEvent(
          'onPayloadReceived',
          predicate=on_advertiser_receive,
          timeout=timeout.total_seconds(),
      )
      tx_id = tx_transfer_event.data['update']['payloadId']
      rx_id_payload_received = rx_received_event.data['payload']['id']
      rx_id_transfer_update = rx_transfer_event.data['update']['payloadId']
      if payload_type == constants.PayloadType.FILE:
        asserts.assert_equal(
            tx_id,
            rx_id_payload_received,
            f'payload id mismatch between sent - {tx_id} and '
            f'received 1st time - {rx_id_payload_received}',
        )
        asserts.assert_equal(
            tx_id,
            rx_id_transfer_update,
            f'payload id mismatch between sent - {tx_id} and '
            f'received completely - {rx_id_transfer_update}',
        )

      if tx_id == last_payload_id:
        transfer_time_s = datetime.timedelta(
            microseconds=tx_transfer_event.data['transferTimeNs'] / 1_000
        ).total_seconds()

    asserts.assert_greater(transfer_time_s, 0, 'Transfer time is 0')
    return round(file_size_kb * num_files / transfer_time_s)

  def _generate_auth_password(self) -> str:
    """Generates a random auth password."""
    pin = []
    for _ in range(AUTH_PASSWORD_LENGTH):
      random_index = secrets.randbelow(len(AUTH_PASSWORD_CHARS))
      pin.append(AUTH_PASSWORD_CHARS[random_index])
    return ''.join(pin)

  def _simulate_address_rotation(
      self,
      supported_services: int,
      timeout: datetime.timedelta,
  ) -> None:
    """Simulates advertising rotation on advertiser."""
    logging.info('Mimicking advertising rotation on advertiser.')
    self.stop_advertising()
    self._advertiser_connection_lifecycle_callback = None  # pyrefly: ignore[bad-assignment]
    # Wait for the stop advertising to be processed before restarting.
    time.sleep(WAIT_FOR_STOP_ADVERTISING_SEC)
    self.start_advertising(supported_services, timeout=timeout)
