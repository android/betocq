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

"""Base class for BetoCQ test suites."""

import logging
import os

from mobly import base_suite
from mobly import records
import yaml

from betocq import version


_BETOCQ_SUITE_NAME = 'BeToCQ'


class BaseBetocqSuite(base_suite.BaseSuite):
  """Base class for BetoCQ test suites.

  Contains methods for aggregating and exporting suite data.
  """

  def __init__(self, runner, config):
    super().__init__(runner, config)
    self._summary_path = None
    self._summary_writer = None

  def teardown_suite(self):
    """Collects test class results and reports them as suite properties."""
    user_data = self._retrieve_user_data_from_summary()
    class_data = [
        entry
        for entry in user_data
        if records.TestResultEnums.RECORD_CLASS in entry
        and records.TestResultEnums.RECORD_NAME not in entry
    ]
    class_results = {
      'suite_name': _BETOCQ_SUITE_NAME,
      'run_identifier': f'v{version.TEST_SCRIPT_VERSION}',
    }
    for entry in class_data:
      properties = entry.get('properties', {})
      for key, value in properties.items():
        # prepend '0'/'1' so the properties appear first in lexicographic order
        if key.endswith('source_device'):
          if '0_source_device' not in class_results:
            class_results['0_source_device'] = value
        if key.endswith('target_device'):
          if '0_target_device' not in class_results:
            class_results['0_target_device'] = value
        if key.endswith('test_result'):
          class_results[f'1_{entry[records.TestResultEnums.RECORD_CLASS]}'] = (
              value
          )
        if key.endswith('detailed_stats'):
          class_results[
              f'1_{entry[records.TestResultEnums.RECORD_CLASS]}_detailed_stats'
          ] = value
    self._record_suite_properties(class_results)

  @property
  def summary_path(self):
    """Returns the path to the summary file.

    NOTE: This path is only correctly resolved if called within teardown_suite.
    """
    if self._summary_path is None:
      # pylint: disable-next=protected-access
      self._summary_path = self._runner._test_run_metadata.summary_file_path
    return self._summary_path

  def _retrieve_user_data_from_summary(self):
    """Retrieves all user_data entries from the currently streamed summary.

    Use this method to aggregate data written by record_data in test classes.

    NOTE: This method can only be called within teardown_suite.

    Returns:
      A list of dictionaries, each corresponding to a USER_DATA entry.
    """
    if not os.path.isfile(self.summary_path):
      logging.error(
          'Cannot retrieve user data for the suite. '
          'The summary file does not exist: %s',
          self.summary_path,
      )
      return []

    with open(self.summary_path, 'r') as f:
      return [
          entry
          for entry in yaml.safe_load_all(f)
          if entry['Type'] == records.TestSummaryEntryType.USER_DATA.value
      ]

  def _record_suite_properties(self, properties):
    """Record suite properties to the test summary file.

    NOTE: This method can only be called within teardown_suite.

    Args:
      properties: dict, the properties to add to the summary
    """
    if self._summary_writer is None:
      self._summary_writer = records.TestSummaryWriter(self.summary_path)
    content = {'properties': properties}
    self._summary_writer.dump(content, records.TestSummaryEntryType.USER_DATA)
