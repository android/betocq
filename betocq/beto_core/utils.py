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

"""Utils for Beto Core."""

from betocq import constants
from betocq import setup_utils
from betocq.beto_core import bc_constants


def get_beto_core_snippet_config(
    user_params: dict[str, dict[str, list[str]]],
) -> constants.SnippetConfig:
  """Gets the snippet config for the Beto Core snippet."""
  return constants.SnippetConfig(
      snippet_name=bc_constants.BETO_CORE_SNIPPET_NAME,
      package_name=bc_constants.BETO_CORE_SNIPPET_APK_PACKAGE,
      apk_path=setup_utils.get_snippet_apk_path(
          user_params, bc_constants.BETO_CORE_SNIPPET_NAME_FROM_BUILD
      ),
  )

