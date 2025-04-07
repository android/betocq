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

from google3.testing.pybase import googletest
from betocq.new import resources


class ResourcesTest(googletest.TestCase):

  def test_allows_resource_declared_in_manifest(self):
    filename = resources.GetResourceFilename(
        "google3/wireless/android/platform/testing/bettertogether/betocq/default_overrides_generated.txt"
    )
    self.assertEndsWith(filename, "default_overrides_generated.txt")

  def test_disallows_resource_not_declared_in_manifest(self):
    with self.assertRaisesRegex(
        ValueError, "not listed in the shared data registry"
    ):
      resources.GetResourceFilename(
          "google3/wireless/android/platform/testing/bettertogether/betocq/instant_connections_on_overrides_generated.txt"
      )


if __name__ == "__main__":
  googletest.main()
