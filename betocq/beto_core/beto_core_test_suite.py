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

"""This test suite batches all tests to run in sequence.


For presubmit tests running on emulators, also add them to
wireless/android/platform/testing/bettertogether/betocq/internal/unified_protocol/presubmit/presubmit_test_suite.py.
For continuous run tests running on real devices, also add them to
wireless/android/platform/testing/bettertogether/betocq/internal/unified_protocol/continuous_run/continuous_run_test_suite.py.
"""

from mobly import base_suite
from mobly import test_runner


class BetoCoreTestSuite(base_suite.BaseSuite):
  """Add test suites for Unified Protocol tests."""

if __name__ == '__main__':
  test_runner.main()
