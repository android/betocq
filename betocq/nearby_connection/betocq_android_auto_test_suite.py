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

from mobly import base_suite
from mobly import suite_runner

from betocq.nearby_connection.directed_tests import bt_performance_test
from betocq.nearby_connection.directed_tests import local_only_hotspot_test


_SUITE_NAME = 'AndroidAuto'


class BetoCqAndroidAutoPerformanceTestSuite(base_suite.BaseSuite):
  """Add all BetoCQ tests to run in sequence."""

  def setup_suite(self, config):
    """Add all BetoCQ tests to the suite."""
    self.user_params['suite_name'] = _SUITE_NAME

    self.add_test_class(bt_performance_test.BtPerformanceTest)
    self.add_test_class(local_only_hotspot_test.LocalOnlyHotspotTest)


def main() -> None:
  """Entry point for execution as pip installed script."""
  suite_runner.run_suite_class()


if __name__ == '__main__':
  main()
