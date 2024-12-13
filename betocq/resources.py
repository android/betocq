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

"""Wrapper API for accessing `data` resources."""

from importlib.resources import files
import os


def GetResourceFilename(name: str) -> str:
  """Get the file path of the named resource.

  Args:
    name: The name of the resource.

  Returns:
    The local file path of the named resource.
  """
  file_path = str(files('betocq.synced_resource_data').joinpath(name))
  if not os.path.isfile(file_path):
    raise ValueError(f'Resource {name} does not exist.')
  return file_path
