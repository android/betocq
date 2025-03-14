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

"""Generates a BeToCQ test report for upload to APA."""
import collections
import os
import platform
import socket
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from betocq import nc_constants
from betocq import version
from mobly import records
import yaml


_RECORD_RESULT = records.TestResultEnums.RECORD_RESULT
_RECORD_DETAILS = records.TestResultEnums.RECORD_DETAILS
_RECORD_STACKTRACE = records.TestResultEnums.RECORD_STACKTRACE

_MOBLY_SUMMARY_KEY_TYPE = 'Type'
_MOBLY_SUMMARY_TYPE_RECORD = 'Record'

_APA_TEST_RESULT_XML = 'test_result.xml'

_APA_STATUS_PASS = 'pass'
_APA_STATUS_WARNING = 'warning'
_APA_STATUS_ALERT = 'alert'
_MOBLY_TO_APA_STATUS = {
    'pass': _APA_STATUS_PASS,
    'fail': _APA_STATUS_WARNING,
    'skip': _APA_STATUS_PASS,
    'error': _APA_STATUS_WARNING,
}

# Placeholder value for missing fields that APA requires to be non-empty, but
# otherwise is not essential information.
# TODO: Replace with actual test-derived values.
_MISSING_VALUE = 'MISSING'

# Placeholder values for APA-required fields, so the report can be accepted.
_PLACEHOLDER_RESULT_FIELDS = {
    'suite_name': 'GTS',
    'report_version': '5.0',
    'suite_version': '12.0_r2',
}


def _get_test_case_name_without_iteration_number(test_case_name: str) -> str:
    """
    Gets the base test case name of a repeated test case without the
    iteration number.
    """
    parts = test_case_name.rsplit('_', 1)
    if parts[1].isdigit():
        return parts[0]
    return test_case_name


def _map_mobly_build_info_to_test_report_build_fields(
        build_info: dict[str, str]) -> dict[str, str]:
    """Maps build info collected from Mobly to APA's Build fields."""
    return {
        'build_fingerprint': build_info.get('build_fingerprint'),
        'build_product': build_info.get('product_name'),
        'build_type': build_info.get('build_type'),
        'build_version_incremental': build_info.get(
            'build_version_incremental'),
        'build_version_sdk': build_info.get('build_version_sdk'),
        'build_version_release': build_info.get(
            'android_version'),
        'build_model': build_info.get('product_model', _MISSING_VALUE),
        'build_manufacturer': build_info.get(
            'product_manufacturer', _MISSING_VALUE),
    }


def _get_host_properties() -> dict[str, str]:
    """Retrieves required properties of the test host."""
    return {
        'host_name': socket.gethostname(),
        'os_name': platform.system(),
        'os_version': platform.release(),
        'os_arch': platform.machine(),
    }


def _generate_test_result_xml(
        mobly_logs: Path, report_dir: Path, start_time: int, end_time: int
) -> bool:
    """Generates a test_result.xml from the Mobly results.

    Args:
        mobly_logs: The base Mobly log directory (containing test_summary.yaml)
        report_dir: The target directory to save the test_result.xml
        start_time: Starting epoch time of the Mobly run.
        end_time: Ending epoch time of the Mobly run.

    Returns: True if the operation succeeds.
    """
    mobly_summary = mobly_logs.joinpath(records.OUTPUT_FILE_SUMMARY)
    if not mobly_summary.is_file():
        print(
            f'[WARNING] No BeToCQ summary found. Aborting {_APA_TEST_RESULT_XML}'
            ' generation.'
        )
        return False
    results = {}
    build_info = {}
    device_serials = []
    setup_failure_classes = set()
    with open(mobly_summary) as f:
        summary = yaml.safe_load_all(f)
        for entry in summary:
            entry_type = entry[_MOBLY_SUMMARY_KEY_TYPE]
            # Parse a test result record
            if entry_type == records.TestSummaryEntryType.RECORD.value:
                test_class = entry[records.TestResultEnums.RECORD_CLASS]
                test_name = _get_test_case_name_without_iteration_number(
                    entry[records.TestResultEnums.RECORD_NAME]
                )
                if test_class not in results:
                    results[test_class] = {}
                # Mark test class as aborted if we encounter a `setup_class`
                # record (indicating failure).
                if test_name == 'setup_class':
                    setup_failure_classes.add(test_class)
                    continue
                # Replace the existing testcase results with the aggregated
                # results from `teardown_class`.
                if test_name == 'teardown_class':
                    test_name = list(results[test_class].keys())[0]
                results[test_class][test_name] = {
                    key: entry[key] for key in (
                        _RECORD_RESULT, _RECORD_DETAILS, _RECORD_STACKTRACE
                    )
                }
                if test_class in setup_failure_classes:
                    results[test_class][test_name][_RECORD_RESULT] = 'alert'
            # Parse Android controller info
            if entry_type == records.TestSummaryEntryType.CONTROLLER_INFO.value:
                for controller in entry[
                    records.ControllerInfoRecord.KEY_CONTROLLER_INFO
                ]:
                    device_serials.append(controller.get('serial'))
                    user_added_info = controller.get('user_added_info', {})
                    role = user_added_info.get('role')
                    # Get build properties only from the target device
                    if role == 'target_device':
                        build_info = controller.get('build_info', {})
                        build_info.update(user_added_info)

    xml_root = ElementTree.Element(
        'Result',
        {
            'suite_plan': nc_constants.BETOCQ_SUITE_NAME,
            'suite_version': version.TEST_SCRIPT_VERSION,
            'devices': ','.join(device_serials),
            'start': str(start_time),
            'end': str(end_time),
        } | _get_host_properties() | _PLACEHOLDER_RESULT_FIELDS
    )
    _ = ElementTree.SubElement(
        xml_root, 'Build',
        _map_mobly_build_info_to_test_report_build_fields(build_info)
    )
    xml_summary = ElementTree.SubElement(xml_root, 'Summary')
    xml_module = ElementTree.SubElement(
        xml_root, 'Module',
        {
            'name': 'betocq_test_suite',
        }
    )

    status_counts = collections.Counter()
    done = True
    for test_class in results:
        xml_test_case = ElementTree.SubElement(
            xml_module, 'TestCase', {'name': test_class}
        )
        for test_name in results[test_class]:
            test_case_entry = results[test_class][test_name]
            result = test_case_entry[_RECORD_RESULT]
            details = test_case_entry[_RECORD_DETAILS]
            stacktrace = test_case_entry[_RECORD_STACKTRACE]
            apa_status = _MOBLY_TO_APA_STATUS.get(
                result.lower(), _APA_STATUS_ALERT
            )
            xml_test = ElementTree.SubElement(
                xml_test_case, 'Test',
                {
                    'name': test_name,
                    'result': apa_status}
            )
            if apa_status == _APA_STATUS_PASS:
                status_counts[_APA_STATUS_PASS] += 1
            elif apa_status == _APA_STATUS_WARNING:
                status_counts[_APA_STATUS_WARNING] += 1
                xml_failure = ElementTree.SubElement(
                    xml_test, 'Failure',
                    {'message': f'[WARNING] {details}'}
                )
                xml_stacktrace = ElementTree.SubElement(
                    xml_failure, 'StackTrace'
                )
                xml_stacktrace.text = stacktrace
            else:
                done = False
                status_counts[_APA_STATUS_ALERT] += 1
                xml_failure = ElementTree.SubElement(
                    xml_test, 'Failure',
                    {'message': f'[SETUP ERROR] {details}'}
                )
                xml_stacktrace = ElementTree.SubElement(
                    xml_failure, 'StackTrace'
                )
                xml_stacktrace.text = stacktrace
    xml_summary.set('pass', str(status_counts[_APA_STATUS_PASS]))
    xml_summary.set('warning', str(status_counts[_APA_STATUS_WARNING]))
    xml_summary.set('failed', str(status_counts[_APA_STATUS_ALERT]))
    # TODO: support execution of more than one module (BeToCQ suite)
    xml_summary.set('modules_done', '1' if done else '0')
    xml_summary.set('modules_total', '1')

    xml_module.set('done', str(done).lower())
    xml_module.set('pass', str(status_counts[_APA_STATUS_PASS]))

    test_result_xml = ElementTree.ElementTree(xml_root)
    ElementTree.indent(test_result_xml)
    os.makedirs(report_dir, exist_ok=True)
    report_file = report_dir.joinpath(_APA_TEST_RESULT_XML)
    test_result_xml.write(
        report_file, encoding='utf-8', xml_declaration=True
    )
    return True


def generate_report(mobly_logs: Path, start_time: int, end_time: int) -> None:
    """Generates a zipped report for upload to Android Partner Approvals.

    Args:
        mobly_logs: The base Mobly log directory (containing test_summary.yaml)
        start_time: Starting epoch time of the Mobly run.
        end_time: Ending epoch time of the Mobly run.
    """
    report_dir = Path(tempfile.mkdtemp())
    report_base_files = report_dir.joinpath('base_files')

    if not _generate_test_result_xml(
            mobly_logs, report_base_files, start_time, end_time
    ):
        return

    zip_path = report_dir.joinpath('report.zip')
    with zipfile.ZipFile(zip_path, 'w') as zip_file:
        for path in report_base_files.iterdir():
            zip_file.write(str(path), arcname=str(path.name))
    print(f'Report created in {zip_path}')
