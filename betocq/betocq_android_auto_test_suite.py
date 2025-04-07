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

"""This test suite batches all tests to run in sequence."""

import sys

from mobly import base_suite
from mobly import suite_runner

from betocq import nc_constants
from betocq.directed_tests import bt_performance_test
from betocq.directed_tests import local_only_hotspot_test


class BetoCqAndroidAutoPerformanceTestSuite(base_suite.BaseSuite):
  """Add all BetoCQ tests to run in sequence."""

  # pylint: disable=line-too-long
  def __init__(self, runner, config):
    super().__init__(runner, config)
    self._enabled_test_classes = {}

  def enable_test_class(self, clazz, config=None):
    """Enable the test class within the suite.

    Once enabled, the test class will run if the user selects it explicitly from
    the command line, or by default if no user selection is made.

    Args:
      clazz: class, a Mobly test class.
      config: config_parser.TestRunConfig, the config to run the class with. If
        not specified, the loaded config file is used as is.
    """
    self._enabled_test_classes[clazz] = config

  def add_enabled_test_classes_from_selection(self):
    """Add enabled test classes to run, based on the user selection."""
    test_selector = suite_runner._parse_cli_args(None).tests
    selected_tests = suite_runner.compute_selected_tests(
        self._enabled_test_classes.keys(), test_selector
    )
    for test_class, tests in selected_tests.items():
      self.add_test_class( # DO_NOT_TRANSFORM
          test_class, config=self._enabled_test_classes[test_class], tests=tests
      )
  # pylint: enable=line-too-long

  def setup_suite(self, config):
    """Add all BetoCQ tests to the suite."""
    test_parameters = nc_constants.TestParameters.from_user_params(
        config.user_params
    )
    config = self._config.copy()
    config.user_params['wifi_channel'] = nc_constants.CHANNEL_2G

    if test_parameters.run_bt_performance_test:
      self.add_test_class(
          clazz=bt_performance_test.BtPerformanceTest,
          config=config,
      )

    if test_parameters.run_directed_test:
      self.add_test_class(
          clazz=local_only_hotspot_test.LocalOnlyHotspotTest,
          config=config,
      )
    self.add_enabled_test_classes_from_selection()


def main() -> None:
  """Entry point for execution as pip installed script."""
  # Mobly's suite_runner searches for suite classes in the __main__ namespace,
  # which breaks when main() is called from a module import. Manually add the
  # suite class to the __main__ module namespace as a workaround.
  sys.modules['__main__'].__dict__[
      BetoCqAndroidAutoPerformanceTestSuite.__name__
  ] = BetoCqAndroidAutoPerformanceTestSuite
  # Use suite_runner's `main`.
  suite_runner.run_suite_class()


if __name__ == '__main__':
  main()
