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

"""Utility functions for testing against Nearby Connection."""

from collections.abc import Sequence
import logging
import time

from mobly import asserts
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import snippet_client_v2

from betocq import android_wifi_utils
from betocq import nc_constants
from betocq import setup_utils
from betocq import test_result_utils
from betocq.nearby_connection import nearby_connection_wrapper


def setup_android_device_for_nc_tests(
    ad: android_device.AndroidDevice,
    snippet_confs: Sequence[nc_constants.SnippetConfig],
    country_code: str,
    debug_output_dir: str,
    skip_flag_override: bool = False,
    skip_forget_wifi_network: bool = False,
) -> None:
  """Performs general Android device setup steps for NC tests."""
  if not skip_forget_wifi_network:
    android_wifi_utils.forget_all_wifi(ad)
  setup_utils.disable_gms_auto_updates(ad)
  for conf in snippet_confs:
    setup_utils.load_nearby_snippet(ad, conf)
  setup_utils.enable_logs(ad)
  setup_utils.clear_hermetic_overrides(ad)
  if not skip_flag_override:
    setup_utils.set_flags(ad, debug_output_dir)
  setup_utils.set_country_code(ad, country_code)
  setup_utils.toggle_airplane_mode(ad)
  ad.nearby.wifiEnable()
  setup_utils.get_thermal_zone_data(ad)


def handle_file_transfer_failure(
    fail_reason: nc_constants.SingleTestFailureReason,
    test_result: test_result_utils.SingleTestResult,
    file_transfer_failure_tip: str,
):
  """Collects metrics and generates result message for file transfer failure."""
  if fail_reason == nc_constants.SingleTestFailureReason.SUCCESS:
    return
  result_message = None
  if fail_reason == nc_constants.SingleTestFailureReason.FILE_TRANSFER_FAIL:
    result_message = file_transfer_failure_tip
  test_result.set_active_nc_fail_reason(fail_reason, result_message)


def reset_nearby_connection(
    discoverer: android_device.AndroidDevice,
    advertiser: android_device.AndroidDevice,
) -> None:
  """Resets any nearby connection on the devices."""
  discoverer.nearby.stopDiscovery()
  discoverer.nearby.stopAllEndpoints()
  advertiser.nearby.stopAdvertising()
  advertiser.nearby.stopAllEndpoints()
  if getattr(discoverer, 'nearby2', None):
    discoverer.nearby2.stopDiscovery()
    discoverer.nearby2.stopAllEndpoints()
  if getattr(advertiser, 'nearby2', None):
    advertiser.nearby2.stopAdvertising()
    advertiser.nearby2.stopAllEndpoints()
  if getattr(discoverer, 'nearby3', None):
    discoverer.nearby3p.stopDiscovery()
    discoverer.nearby3p.stopAllEndpoints()
  if getattr(advertiser, 'nearby3', None):
    advertiser.nearby3p.stopAdvertising()
    advertiser.nearby3p.stopAllEndpoints()
  time.sleep(nc_constants.NEARBY_RESET_WAIT_TIME.total_seconds())


def abort_if_2g_ap_not_ready(
    test_parameters: nc_constants.TestParameters,
) -> None:
  """Aborts test class if 2G AP is not ready."""
  asserts.abort_class_if(
      not test_parameters.wifi_2g_ssid, '2G AP is not ready for this test.'
  )


def abort_if_5g_ap_not_ready(
    test_parameters: nc_constants.TestParameters,
) -> None:
  """Aborts test class if 5G AP is not ready."""
  asserts.abort_class_if(
      not test_parameters.wifi_5g_ssid, '5G AP is not ready for this test.'
  )


def abort_if_dfs_5g_ap_not_ready(
    test_parameters: nc_constants.TestParameters,
) -> None:
  """Aborts test class if DFS 5G AP is not ready."""
  asserts.abort_class_if(
      not test_parameters.wifi_dfs_5g_ssid,
      '5G DFS AP is not ready for this test.',
  )


def abort_if_wifi_direct_not_supported(
    ads: list[android_device.AndroidDevice],
) -> None:
  """Aborts test class if any device does not support Wi-Fi Direct."""
  for ad in ads:
    asserts.abort_class_if(
        not setup_utils.is_wifi_direct_supported(ad),
        f'Wifi Direct is not supported on the device {ad}.',
    )


def abort_if_wifi_hotspot_not_supported(
    ads: list[android_device.AndroidDevice],
) -> None:
  """Aborts test class if any device does not support Wi-Fi Hotspot."""
  for ad in ads:
    # We are checking Wi-Fi Direct capability here because Wi-Fi Hotspot is
    # implemented using Wi-Fi Direct in NC.
    asserts.abort_class_if(
        not setup_utils.is_wifi_direct_supported(ad),
        f'Wifi Hotspot is not supported on the device {ad}.',
    )


def abort_if_wifi_aware_not_available(
    ads: list[android_device.AndroidDevice],
) -> None:
  """Aborts test class if Wi-Fi Aware is not available in any device."""
  for ad in ads:
    # The utility function waits a small time. This is because Aware is not
    # immediately available after enabling WiFi.
    asserts.abort_class_if(
        not setup_utils.wait_for_aware_available(ad),
        f'Wifi Aware is not available in the device {ad}.',
    )


def abort_if_device_cap_not_match(
    ads: list[android_device.AndroidDevice],
    attribute_name: str,
    expected_value: bool,
) -> None:
  """Aborts class if the device capability does not match the expected value."""
  for ad in ads:
    actual_value = getattr(ad, attribute_name)
    asserts.abort_class_if(
        actual_value != expected_value,
        (
            f'{ad}, "{attribute_name}" is'
            f' {"enabled" if actual_value else "disabled"}, which does not'
            ' match test case requirement.'
        ),
    )


def _get_snippet(
    advertiser: android_device.AndroidDevice,
    discoverer: android_device.AndroidDevice,
    advertiser_nearby: snippet_client_v2.SnippetClientV2,
    discoverer_nearby: snippet_client_v2.SnippetClientV2,
    advertising_discovery_medium: nc_constants.NearbyMedium,
    connection_medium: nc_constants.NearbyMedium,
    upgrade_medium: nc_constants.NearbyMedium,
) -> nearby_connection_wrapper.NearbyConnectionWrapper:
  """Gets the snippet for Nearby Connection."""
  return nearby_connection_wrapper.NearbyConnectionWrapper(
      advertiser,
      discoverer,
      advertiser_nearby,
      discoverer_nearby,
      advertising_discovery_medium,
      connection_medium,
      upgrade_medium,
  )
