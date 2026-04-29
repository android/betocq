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

"""A Mobly test for the BetoCore snippet's V2 discovery RPC."""

import time

from mobly import asserts
from mobly import base_test as mobly_base_test
from mobly import test_runner
from mobly.controllers import android_device

from betocq import constants
from betocq import setup_utils
from betocq.beto_core import bc_constants
from betocq.beto_core import utils as beto_core_utils

_SERVICE_ID = "01020304050607080910111213141516"


class BetoCoreDiscoveryTest(mobly_base_test.BaseTestClass):
  """A two-device test for BetoCore V2 service registration and discovery."""

  beto_core_snippet_config: constants.SnippetConfig

  def setup_class(self) -> None:
    """Initializes the test class."""
    self.ads = self.register_controller(android_device, min_number=2)
    self.broadcaster = self.ads[0]
    self.discoverer = self.ads[1]

    self.beto_core_snippet_config = (
        beto_core_utils.get_beto_core_snippet_config(self.user_params)
    )

    for ad in self.ads:
      ad.log.info(
          "Loading snippet %s", self.beto_core_snippet_config.package_name
      )
      setup_utils.load_nearby_snippet(ad, self.beto_core_snippet_config)

  def setup_test(self) -> None:
    """Initializes the test."""
    for ad in self.ads:
      ad.log.info("Setting API surface to OXIDE")
      ad.betocore.setBeToCoreApiSurface(
          bc_constants.BETO_CORE_API_SURFACE_OXIDE
      )
      # Unlock the screen to allow for BLE scanning.
      ad.log.info("Unlocking screen")
      setup_utils.turn_device_on(ad)
      setup_utils.unlock_screen(ad)
      # TODO: check the device settings, e.g. bluetooth, wifi, etc.

  def test_discovery(self):
    """Starts discovery on one device and registration on another."""
    self.discoverer.log.info(
        "Starting discovery for service: %s", _SERVICE_ID
    )
    try:
      discovery_callback = self.discoverer.betocore.startDiscovery(
          _SERVICE_ID
      )

      # Wait for the BLE scanner to warm up.
      self.discoverer.log.info("Waiting 5s for BLE scanner warmup...")
      time.sleep(5)

      self.broadcaster.log.info(
          "Starting registration for service: %s", _SERVICE_ID
      )
      self.broadcaster.betocore.registerService(_SERVICE_ID)

      self.broadcaster.log.info("Waiting for wakeup to be observed...")
      # 15 seconds timeout
      wakeup_observed = self.broadcaster.betocore.onWakeupObserved(15)
      asserts.assert_true(
          wakeup_observed,
          "Failed to observe wakeup for service: %s" % _SERVICE_ID,
      )

      self.broadcaster.log.info("Requesting temporary public visibility...")
      self.broadcaster.betocore.requestTemporaryPublicVisibility()

      self.discoverer.log.info(
          "Waiting for discovery event (onDeviceDiscovered)..."
      )
      discovery_callback.waitAndGet("onDeviceDiscovered", timeout=30)
      self.discoverer.log.info("Discovery event received!")

      discovered_devices = self.discoverer.betocore.getDiscoveredDeviceIds()
      self.discoverer.log.info("Discovered device IDs: %s", discovered_devices)

      asserts.assert_true(
          len(discovered_devices) > 0,
          "Failed to discover any device. Discovered: %s"
          % discovered_devices,
      )
    finally:
      self.discoverer.log.info("Cleaning up discovery/registration")
      self.discoverer.betocore.stopDiscovery()
      self.broadcaster.betocore.unregisterService()

  def teardown_test(self):
    self.broadcaster.services.create_output_excerpts_all(self.current_test_info)
    self.discoverer.services.create_output_excerpts_all(self.current_test_info)

  def teardown_class(self):
    for ad in self.ads:
      ad.log.info("Unloading and uninstalling snippet apks")
      setup_utils.unload_nearby_snippet(ad, self.beto_core_snippet_config)


if __name__ == "__main__":
  test_runner.main()
