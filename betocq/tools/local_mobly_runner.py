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
    - Run a test binary from a Python wheel
    local_mobly_runner.py -w my-test-0.1-py3-none-any.whl --bin test_suite_a

    - Run a test binary from a Python wheel. Install test APKs before running
      the test.
    local_mobly_runner.py -w my-test-0.1-py3-none-any.whl --bin test_suite_a -i

    - Run a test binary from a Python wheel, with specific Android devices.
    local_mobly_runner.py -w my-test-0.1-py3-none-any.whl --bin test_suite_a -s DEV00001,DEV00002

    - [Legacy] Run a list of zipped executable Mobly packages
    local_mobly_runner.py -p test_pkg1,test_pkg2,test_pkg3


Please run `local_mobly_runner.py -h` for a full list of options.
"""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple
import zipfile


_DEFAULT_MOBLY_LOGPATH = Path('/tmp/logs/mobly')
_DEFAULT_TESTBED = 'LocalTestBed'

_tempdirs = []
_tempfiles = []


def _padded_print(line: str) -> None:
    print(f'\n-----{line}-----\n')


def _parse_args() -> argparse.Namespace:
    """Parses command line args."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__)
    group1 = parser.add_mutually_exclusive_group(required=True)
    group1.add_argument(
        '-p', '--packages',
        help=(
            'A comma-delimited list of test packages to run. The packages '
            'should be directly executable by the Python interpreter. If '
            'the package includes a requirements.txt file, deps will '
            'automatically be installed.'
        )
    )
    group1.add_argument(
        '-w', '--wheel',
        help=(
            'A Python wheel (.whl) containing one or more Mobly test scripts. '
            'Does not support the --novenv option.'
        )
    )
    group1.add_argument(
        '-t',
        '--test_paths',
        help=(
            'A comma-delimited list of test paths to run directly. Implies '
            'the --novenv option.'
        ),
    )

    parser.add_argument(
        '-i',
        '--install_apks',
        action='store_true',
        help=(
            'Install all APKs contained inside the package to all specified'
            ' devices. Does not support the -t option.'
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
            'package or file. E.g. `--tests TestClassA TestClassB.test_b` '
            'would run all of test class TestClassA, but only test_b in '
            'TestClassB. This option cannot be used if multiple packages/test '
            'paths are specified.'
        ),
    )
    parser.add_argument(
        '--bin',
        help=(
            'Name of the binary to run in the installed wheel. Must be '
            'specified alongside the --wheel option.'
        ),
    )
    parser.add_argument(
        '--novenv',
        action='store_true',
        help=(
            "Run directly in the host's system Python, without setting up a "
            'virtualenv.'
        ),
    )
    args = parser.parse_args()
    if args.wheel:
        if args.novenv:
            parser.error('Option --novenv cannot be used with --wheel.')
        if not args.bin:
            parser.error('Option --wheel requires --bin to be specified.')
    if args.bin:
        if not args.wheel:
            parser.error('Option --bin requires --wheel to be specified.')
    if args.install_apks and args.test_paths:
        parser.error('Option --install_apks cannot be used with --test_paths.')
    if args.tests is not None:
        multiple_packages = (args.packages is not None
                             and len(args.packages.split(',')) > 1)
        multiple_test_paths = (args.test_paths is not None
                               and len(args.test_paths.split(',')) > 1)
        if multiple_packages or multiple_test_paths:
            parser.error(
                'Option --tests cannot be used if multiple --packages or '
                '--test_paths are specified.'
            )

    args.novenv = args.novenv or (args.test_paths is not None)
    return args


def _extract_test_resources(
        args: argparse.Namespace,
) -> Tuple[List[str], List[str], List[str]]:
    """Extract test resources from the given test package.

    Args:
      args: Parsed command-line args.

    Returns:
      Tuple of (mobly_bins, requirement_files, test_apks).
    """
    _padded_print('Resolving test resources.')
    mobly_bins = []
    requirements_files = []
    test_apks = []
    if args.test_paths:
        mobly_bins.extend(args.test_paths.split(','))
    elif args.packages or args.wheel:
        packages = args.packages.split(',') if args.packages else [args.wheel]
        unzip_root = tempfile.mkdtemp(prefix='mobly_unzip_')
        _tempdirs.append(unzip_root)
        for package in packages:
            mobly_bins.append(os.path.abspath(package))
            unzip_dir = os.path.join(unzip_root, os.path.basename(package))
            print(f'Unzipping test package {package} to {unzip_dir}.')
            os.makedirs(unzip_dir)
            with zipfile.ZipFile(package) as zf:
                zf.extractall(unzip_dir)
            for root, _, files in os.walk(unzip_dir):
                for file_name in files:
                    path = os.path.join(root, file_name)
                    if path.endswith('requirements.txt'):
                        requirements_files.append(path)
                    if path.endswith('.apk'):
                        test_apks.append(path)
    else:
        print('No tests specified. Aborting.')
        exit(1)
    return mobly_bins, requirements_files, test_apks


def _setup_virtualenv(
        requirements_files: List[str],
        wheel_file: Optional[str]
) -> str:
    """Creates a virtualenv and install dependencies into it.

    Args:
      requirements_files: List of paths of requirements.txt files.
      wheel_file: A Mobly test package as an installable Python wheel.

    Returns:
      Path to the virtualenv's Python interpreter.
    """
    venv_dir = tempfile.mkdtemp(prefix='venv_')
    _padded_print(f'Setting up virtualenv at {venv_dir}.')
    subprocess.check_call([sys.executable, '-m', 'venv', venv_dir])
    _tempdirs.append(venv_dir)
    if platform.system() == 'Windows':
        venv_executable = os.path.join(venv_dir, 'Scripts', 'python.exe')
    else:
        venv_executable = os.path.join(venv_dir, 'bin', 'python3')

    # Install requirements
    for requirements_file in requirements_files:
        print(f'Installing dependencies from {requirements_file}.\n')
        subprocess.check_call(
            [venv_executable, '-m', 'pip', 'install', '-r', requirements_file]
        )

    # Install wheel
    if wheel_file is not None:
        print(f'Installing test wheel package {wheel_file}.\n')
        subprocess.check_call(
            [venv_executable, '-m', 'pip', 'install', wheel_file]
        )
    return venv_executable


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
        apks: List[str],
        serials: Optional[List[str]] = None,
) -> None:
    """Installs given APKS to specified devices.

    If no serials specified, installs APKs on all attached devices.

    Args:
      apks: List of paths to APKs.
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
    for apk in apks:
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
        json.dump(config, f)
    _tempfiles.append(config_path)
    return config_path


def _run_mobly_tests(
        python_executable: Optional[str],
        mobly_bins: List[str],
        tests: Optional[List[str]],
        config: str,
        test_bed: str,
        log_path: Optional[str]
) -> None:
    """Runs the Mobly tests with the specified binary and config."""
    env = os.environ.copy()
    base_log_path = _DEFAULT_MOBLY_LOGPATH
    for mobly_bin in mobly_bins:
        bin_name = os.path.basename(mobly_bin)
        if log_path:
            base_log_path = Path(log_path, bin_name)
            env['MOBLY_LOGPATH'] = str(base_log_path)
        cmd = [python_executable] if python_executable else []
        cmd += [mobly_bin, '-c', config, '-tb', test_bed]
        if tests is not None:
            cmd.append('--tests')
            cmd += tests
        _padded_print(f'Running Mobly test {bin_name}.')
        print(f'Command: {cmd}\n')
        subprocess.run(cmd, env=env)
        # Save a copy of the config in the log directory.
        latest_logs = base_log_path.joinpath(test_bed, 'latest')
        if latest_logs.is_dir():
            shutil.copy2(config, latest_logs)


def _clean_up() -> None:
    """Cleans up temporary directories and files."""
    _padded_print('Cleaning up temporary directories/files.')
    for td in _tempdirs:
        shutil.rmtree(td, ignore_errors=True)
    _tempdirs.clear()
    for tf in _tempfiles:
        os.remove(tf)
    _tempfiles.clear()


def main() -> None:
    args = _parse_args()

    serials = args.serials.split(',') if args.serials else None

    # Extract test resources
    mobly_bins, requirements_files, test_apks = _extract_test_resources(args)

    # Install test APKs, if necessary
    if args.install_apks:
        _install_apks(test_apks, serials)

    # Set up the Python virtualenv, if necessary
    python_executable = None
    if args.novenv:
        if args.test_paths is not None:
            python_executable = sys.executable
    else:
        python_executable = _setup_virtualenv(requirements_files, args.wheel)

    if args.wheel:
        mobly_bins = [
            os.path.join(os.path.dirname(python_executable), args.bin)
        ]
        python_executable = None

    # Generate the Mobly config, if necessary
    config = args.config or _generate_mobly_config(serials)

    # Run the tests
    _run_mobly_tests(python_executable, mobly_bins, args.tests, config,
                     args.test_bed, args.log_path)

    # Clean up temporary dirs/files
    _clean_up()


if __name__ == '__main__':
    main()
