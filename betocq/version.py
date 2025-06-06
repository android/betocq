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

"""Define the Beto CQ test script version."""

import importlib.metadata
TEST_SCRIPT_VERSION = importlib.metadata.version('betocq')

# VERSION_LOG (only add new description for new version, keep the history log)
# '2.0.0': 'initial version'
# '2.1.0': 'add iperf for WFD and fix missing data of failed test cases.'
# '2.2.0': 'add iperf for AWARE,HOTSPOT mode and disable WLAN deny list.'
# '2.3.0': 'fix the low NC speed issue.'
# '2.3.1': 'fix WLAN function test and improve the report format.'
# '2.3.2': 'add TDLS/Aware device capability check.'
# '2.4.0': 'add multi-payload test parameters and optimize multi-payload transfer tests.'
# '2.4.1': 'add android auto test case.'
# '2.4.2': 'fix wifi direct capability check issue.'
# '2.5.0': 'refactor tests for improved readability; split 3 functional cases into 6.'
