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

"""Provides the actor base for all function tests."""

from typing import Tuple

from mobly.controllers import android_device

from betocq import nc_constants


class FunctionTestActorBase:
  """Base class of actors for running all function tests."""

  def __init__(self,
               test_parameters: nc_constants.TestParameters,
               discoverer: android_device.AndroidDevice,
               advertiser: android_device.AndroidDevice
               ):
    self.test_parameters: nc_constants.TestParameters = test_parameters
    self.advertiser: android_device.AndroidDevice = advertiser
    self.discoverer: android_device.AndroidDevice = discoverer
    self._test_result: nc_constants.SingleTestResult = (
        nc_constants.SingleTestResult()
    )
    self._test_failure_reason: nc_constants.SingleTestFailureReason = (
        nc_constants.SingleTestFailureReason.UNINITIALIZED
    )
    self._wifi_medium_under_test = None
    self._skipped: bool = False

  def _get_wifi_ssid_password(self) -> Tuple[str, str]:
    """Returns the available wifi username and password."""
    if self.test_parameters.wifi_ssid:
      return (
          self.test_parameters.wifi_ssid,
          self.test_parameters.wifi_password,
      )
    if self.test_parameters.wifi_5g_ssid:
      return (
          self.test_parameters.wifi_5g_ssid,
          self.test_parameters.wifi_5g_password,
      )
    if self.test_parameters.wifi_dfs_5g_ssid:
      return (
          self.test_parameters.wifi_dfs_5g_ssid,
          self.test_parameters.wifi_dfs_5g_password,
      )
    if self.test_parameters.wifi_2g_ssid:
      return (
          self.test_parameters.wifi_2g_ssid,
          self.test_parameters.wifi_2g_password,
      )
    return ('', '')

  def get_test_result_message(self) -> str:
    """Returns the message about the test result."""
    return 'Unknown'

  def _get_test_failure_reason(self) -> nc_constants.SingleTestFailureReason:
    """Returns the test failure reason."""
    return self._test_failure_reason
