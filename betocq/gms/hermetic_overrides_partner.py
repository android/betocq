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

"""Utilities for loading hermetic overrides on devices."""

import io
import os

from mobly.controllers import android_device
from mobly.controllers.android_device_lib import adb
from mobly.controllers.android_device_lib import apk_utils


_GMS_PACKAGE = 'com.google.android.gms'

OVERRIDES_PATH = '/sdcard/overrides.txt'
SCRIPT_PATH = '/sdcard/setup_flags.sh'
HERMETIC_FILE_PATH = 'app_phenotype_hermetic/overrides.txt'


def _create_setup_script(
    script_template: str,
    overrides_source: str = OVERRIDES_PATH,
    merge_overrides: bool = False,
    package: str = _GMS_PACKAGE,
) -> str:
  return (
      script_template.replace(r'${ARG_APP_PACKAGE_NAME}', package)
      .replace(r'${ARG_HERMETIC_OVERRIDES_SOURCE_DEVICE}', overrides_source)
      .replace(r'${ARG_MERGE_EXISTING_OVERRIDES}', str(merge_overrides))
  )


def _run_setup_script(
    device: android_device.AndroidDevice, script: str, output_path: str
) -> str:
  """Runs the overrides script on the device and returns the output."""
  host_file = os.path.join(output_path, 'setup_flags.sh')
  # If opening in text mode, Python will automatically convert any newline
  # characters to \r\n if the host is Windows, which will cause the script
  # to fail when pushed onto the device. To work around this, write the file
  # in binary mode so the exact content is preserved.
  with open(host_file, 'wb') as f:
    f.write(script.encode())
  device.adb.push([host_file, SCRIPT_PATH], timeout=120)
  device.adb.shell(f'chmod +x {SCRIPT_PATH}')
  # For backwards compatibility on very old devices, the overrides script writes
  # to stderr rather than stdout (which is always empty), even when there are
  # no errors.
  stderr = io.BytesIO()
  device.adb.shell(f'sh {SCRIPT_PATH}', stderr=stderr)
  stderr.seek(0)
  return stderr.read().decode('utf-8')


def install_hermetic_overrides(
    device: android_device.AndroidDevice,
    hermetic_overrides_file: str,
    output_path: str,
    package: str,
    setup_template: str,
    merge_with_existing_overrides: bool = False,
) -> None:
  """Installs hermetic overrides on device for the given package.

  You MUST stop the process for the given package after calling this function
  to see the effect of the overrides.

  Preconditions:
    The package must be already installed on the device.

  Note that if you are trying to set flags for GMS modules, you should use
  `com.google.android.gms` rather than the Chimera package.

  Args:
    device: The device of interest.
    hermetic_overrides_file: The file path to the hermetic overrides file.
    output_path: Path where debug data will be written.
    package: The package name for the app containing the flags to be overridden.
    setup_template: The raw overrides setup script template.
    merge_with_existing_overrides: Whether to merge the overrides with any
      existing overrides on the device. If `False`, the existing overrides will
      be completely replaced.
  """
  if package.startswith(_GMS_PACKAGE) and package != _GMS_PACKAGE:
    raise ValueError(f'GMS modules should use package {_GMS_PACKAGE}')
  if not apk_utils.is_apk_installed(device, package):
    raise ValueError(f'Package {package} is not installed on device')

  device.log.info(
      'Existing overrides will be'
      f' {"merged" if merge_with_existing_overrides else "replaced"}.',
  )
  device.adb.root()
  device.adb.push([hermetic_overrides_file, OVERRIDES_PATH])
  setup_script = _create_setup_script(
      setup_template,
      package=package,
      merge_overrides=merge_with_existing_overrides,
  )
  result = _run_setup_script(device, setup_script, output_path)
  device.log.info('Override script result:\n%s', result)


def clear_hermetic_overrides(
    device: android_device.AndroidDevice,
    package: str,
) -> None:
  """Clears file-based hermetic overrides on device for the given package.

  This is done by deleting the overrides.txt file from the app's hermetic
  directory in both Device Encrypted (DE) and Credential Encrypted (CE)
  storage paths, covering all users.
  You MUST stop the process for the given package after calling this function
  to see the effect of clearing the overrides.

  Args:
    device: The device of interest.
    package: The package name for the app for which flags should be cleared.
  """
  device.adb.root()
  # Path for credential-encrypted storage
  ce_path = f'/data/data/{package}/{HERMETIC_FILE_PATH}'
  # Path for device-encrypted storage - use glob for multiple users
  de_path_glob = f'/data/user_de/*/{package}/{HERMETIC_FILE_PATH}'

  try:
    # Use sh -c to ensure glob expansion for '*' in de_path_glob.
    # This removes .../overrides.txt for all users (0, 10, etc.).
    device.adb.shell(f"sh -c 'rm -f {de_path_glob}'")
    device.log.info(f'Attempted removal of DE overrides: {de_path_glob}')
  except adb.AdbError:
    device.log.exception('Failed removing DE override for %s', package)
  try:
    # Also remove from CE path, in case setup used that instead.
    device.adb.shell(['rm', '-f', ce_path])
    device.log.info(f'Attempted removal of CE overrides: {ce_path}')
  except adb.AdbError:
    device.log.exception('Failed removing CE override for %s', package)
