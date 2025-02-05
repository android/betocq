#!/usr/bin/env python3

#  Copyright 2025 Google LLC
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

"""Script for running git-based Mobly tests locally.

Example:
    - Run a selected test binary
    local_mobly_runner test_suite_a

    - Run a test binary. Install test APKs before running the test.
    local_mobly_runner test_suite_a -i

    - Run a test binary with specific Android devices.
    local_mobly_runner test_suite_a -s DEV00001,DEV00002

Please run `local_mobly_runner -h` for a full list of options.
"""

import argparse
import importlib.resources
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

import yaml

_DEFAULT_MOBLY_LOGPATH = Path('/tmp/logs/mobly')
_DEFAULT_TESTBED = 'LocalTestBed'

_tempfiles = []


def _padded_print(line: str) -> None:
    print(f'\n-----{line}-----\n')


def _parse_args() -> argparse.Namespace:
    """Parses command line args."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__)

    parser.add_argument(
        'mobly_bin',
        help=(
            'Name of the installed Mobly binary to run.'
        ),
    )

    parser.add_argument(
        '-i',
        '--install_apks',
        action='store_true',
        help=(
            'Install all APKs contained in package resource files to all '
            'specified devices.'
        ),
    )
    parser.add_argument(
        '-s',
        '--serials',
        help=(
            'Specify the devices to test with a comma-delimited list of device '
            'serials. If --config is also specified, this option will only be '
            'used to select the devices to install APKs.'
        ),
    )
    parser.add_argument(
        '-c', '--config', help='Provide a custom Mobly config for the test.'
    )
    parser.add_argument('-tb', '--test_bed',
                        default=_DEFAULT_TESTBED,
                        help='Select the testbed for the test. If left '
                             f'unspecified, "{_DEFAULT_TESTBED}" will be '
                             'selected by default.')
    parser.add_argument('-lp', '--log_path',
                        help='Specify a path to store logs.')

    parser.add_argument(
        '--tests',
        nargs='+',
        type=str,
        metavar='TEST_CLASS[.TEST_CASE]',
        help=(
            'A list of test classes and optional tests to execute within the '
            'suite binary. E.g. `--tests TestClassA TestClassB.test_b` '
            'would run all of test class TestClassA, but only test_b in '
            'TestClassB.'
        ),
    )

    return parser.parse_args()


def _parse_adb_devices(lines: List[str]) -> List[str]:
    """Parses result from 'adb devices' into a list of serials.

    Derived from mobly.controllers.android_device.
    """
    results = []
    for line in lines:
        tokens = line.strip().split('\t')
        if len(tokens) == 2 and tokens[1] == 'device':
            results.append(tokens[0])
    return results


def _install_apks(
        serials: Optional[List[str]] = None,
) -> None:
    """Installs snippet APKS to specified devices.

    If no serials specified, installs APKs on all attached devices.

    Args:
      serials: List of device serials.
    """
    _padded_print('Installing test APKs.')
    if not serials:
        adb_devices_out = (
            subprocess.check_output(
                ['adb', 'devices']
            ).decode('utf-8').strip().splitlines()
        )
        serials = _parse_adb_devices(adb_devices_out)
    for apk in importlib.resources.files(
            'betocq').joinpath('snippets').iterdir():
        for serial in serials:
            print(f'Installing {apk} on device {serial}.')
            subprocess.check_call(
                ['adb', '-s', serial, 'install', '-r', '-g', apk]
            )


def _generate_mobly_config(serials: Optional[List[str]] = None) -> str:
    """Generates a Mobly config for the provided device serials.

    If no serials specified, generate a wildcard config (test loads all attached
    devices).

    Args:
      serials: List of device serials.

    Returns:
      Path to the generated config.
    """
    config = {
        'TestBeds': [{
            'Name': _DEFAULT_TESTBED,
            'Controllers': {
                'AndroidDevice': serials if serials else '*',
            },
        }]
    }
    _, config_path = tempfile.mkstemp(prefix='mobly_config_', suffix='.yaml')
    _padded_print(f'Generating Mobly config at {config_path}.')
    with open(config_path, 'w') as f:
        yaml.safe_dump(config, f)
    _tempfiles.append(config_path)
    return config_path


def _run_mobly_tests(
        mobly_bin: str,
        tests: Optional[List[str]],
        config: str,
        test_bed: str,
        log_path: Optional[str]
) -> Path:
    """Runs the Mobly tests with the specified binary and config.

    Returns:
        Path to the generated Mobly test log directory.
    """
    env = os.environ.copy()
    base_log_path = _DEFAULT_MOBLY_LOGPATH
    if log_path:
        base_log_path = Path(log_path, mobly_bin)
        env['MOBLY_LOGPATH'] = str(base_log_path)
    cmd = [mobly_bin, '-c', config, '-tb', test_bed]
    if tests is not None:
        cmd.append('--tests')
        cmd += tests
    _padded_print(f'Running Mobly test {mobly_bin}.')
    print(f'Command: {cmd}\n')
    subprocess.run(cmd, env=env)
    # Save a copy of the config in the log directory.
    latest_logs = base_log_path.joinpath(test_bed, 'latest')
    if latest_logs.is_dir():
        shutil.copy2(config, latest_logs)
    return latest_logs


def _clean_up() -> None:
    """Cleans up temporary files."""
    _padded_print('Cleaning up temporary files.')
    for tf in _tempfiles:
        os.remove(tf)
    _tempfiles.clear()


def main() -> None:
    args = _parse_args()

    serials = args.serials.split(',') if args.serials else None

    # Install test APKs, if necessary
    if args.install_apks:
        _install_apks(serials)

    # Generate the Mobly config, if necessary
    config = args.config or _generate_mobly_config(serials)

    # Run the tests
    _run_mobly_tests(args.mobly_bin, args.tests, config,
                     args.test_bed, args.log_path)

    # Clean up temporary dirs/files
    _clean_up()


if __name__ == '__main__':
    main()
