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

"""Base test class for nearby connection E2E performance tests."""

import logging

from mobly import asserts
from mobly import records

from betocq.new import base_test
from betocq.new import nc_constants
from betocq.new import test_result_utils


class PerformanceTestBase(base_test.BaseTestClass):
  """Base test class for nearby connection E2E performance tests."""

  _test_results: test_result_utils.PerformanceTestResults

  def setup_class(self):
    self._test_results = test_result_utils.PerformanceTestResults()
    super().setup_class()

  @property
  def test_results(self) -> test_result_utils.PerformanceTestResults:
    return self._test_results

  @property
  def current_test_result(self) -> test_result_utils.SingleTestResult:
    return self._test_results.current_test_result

  def setup_test(self):
    self.test_results.start_new_test_iteration()
    super().setup_test()

  def teardown_test(self) -> None:
    self.test_results.end_test_iteration()
    super().teardown_test()

  def on_pass(self, record: records.TestResultRecord):
    self.current_test_result.set_active_nc_fail_reason(
        nc_constants.SingleTestFailureReason.SUCCESS
    )
    self._record_single_test_iter_report()
    super().on_pass(record)

  def on_fail(self, record: records.TestResultRecord):
    # If any exception is raised in `setup_class`, `on_fail` will be invoked
    # and we should not record any result because no test iteration is executed.
    if self._test_results.is_any_test_iter_executed():
      self._record_single_test_iter_report()
    super().on_fail(record)

  def _record_single_test_iter_report(self):
    test_report = test_result_utils.gen_single_test_iter_report(
        self.current_test_result
    )
    self.record_data({
        'Test Class': self.TAG,
        'Test Name': self.current_test_info.name,  # pytype: disable=attribute-error
        'properties': test_report,
    })

  def teardown_class(self):
    if not self.test_results.is_any_test_iter_executed():
      logging.info('Skipping teardown class.')
      return

    test_summary = self.test_results.gen_test_summary()
    self.record_data({'Test Class': self.TAG, 'properties': test_summary})

    passed = self.test_results.is_test_class_passed()
    final_result_message = self.test_results.get_test_class_result_message()
    asserts.assert_true(passed, final_result_message)
    super().teardown_class()
