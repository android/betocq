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

r"""Converts BeToCQ test results and metrics into an APA-compatible ZIP package.

Usage (Internal/Blaze):
  blaze run //wireless/android/platform/testing/bettertogether/betocq/tools/apa_package:betocq_to_apa -- \
    --input_dir=/path/to/suite1_logs,/path/to/suite2_logs \
    [--output_dir=/path/to/output/dir] \
    [--resultstore_link=https://btx.cloud.google.com/invocations/...]

Usage (Independent Script for OEMs):
  Prerequisites:
    pip install absl-py mobly PyYAML

  Command:
    python3 betocq_to_apa.py \
      --input_dir=/path/to/suite1_logs,/path/to/suite2_logs \
      [--output_dir=/path/to/output/dir] \
      [--resultstore_link=https://btx.cloud.google.com/invocations/...]

Expected Input Directory Structure (single dir or comma-separated/parent dir of runs):
  <run_dir>/
    test_summary.yaml
    report-log-files/
      <apa_module_name>.reportlog.json

Output ZIP Structure (named <end_time>.zip):
  test_result.xml
  test_result.html
  report-log-files/
    <apa_module_name>.reportlog.json  # Merged if the same suite was run multiple times
  non-tradefed_results/
    <apa_module_name>/
      <run_time>/test_summary.yaml  # Each run's original test_summary.yaml in its run-time subfolder

Library Usage:
  from betocq.tools.apa_package import betocq_to_apa

  betocq_to_apa.package_for_apa(
      input_dir=["/path/to/suite1_logs", "/path/to/suite2_logs"],
      output_dir="/path/to/output/dir",  # Optional
      resultstore_link="https://btx.cloud.google.com/invocations/...",
      start_time=1700000000000,
      end_time=1700000010000,
  )
"""

import collections
from collections.abc import Sequence
import datetime
import json
import logging
import os
import platform
import random
import shutil
import socket
import sys
import textwrap
from typing import Any
from xml.etree import ElementTree as ET
import zipfile


from absl import app
from absl import flags
from mobly import records
import yaml

_APA_STATUS_PASS = "pass"
_APA_STATUS_FAIL = "fail"
_APA_STATUS_WARNING = "warning"
_APA_STATUS_IGNORED = "IGNORED"
_APA_SUITE_NAME = "BETOCQ"

_STATUS_PRIORITY = (
    _APA_STATUS_FAIL,
    _APA_STATUS_WARNING,
    _APA_STATUS_IGNORED,
    _APA_STATUS_PASS,
)
# When merging multiple executions (retries) of the same scenario across runs,
# a passing retry supersedes a warning/failure, and an executed result
# supersedes an ignored/skipped result. Ties favor the newer run.
_RETRY_MERGE_PRIORITY = (
    _APA_STATUS_PASS,
    _APA_STATUS_WARNING,
    _APA_STATUS_FAIL,
    _APA_STATUS_IGNORED,
)
_METRIC_BUCKETS = ("numeric_metrics", "boolean_metrics", "text_metrics")

_FAILURE_TERMINATION_SIGNAL_TYPES = frozenset({
    "TestAbortAll",
    "ProtocolError",
    "AdbError",
    "WifiApNotReadyError",
    "PythonVersionError",
    "DeviceRegistrationError",
    "UnrootedDeviceError",
    "MissingConfigError",
    "SnippetDisconnectionError",
})

_MISSING_VALUE = "MISSING"


def _get_host_properties() -> dict[str, str]:
  """Retrieves required properties of the test host."""
  return {
      "host_name": socket.gethostname(),
      "os_name": platform.system(),
      "os_version": platform.release(),
      "os_arch": platform.machine(),
  }


def _get_base_test_name(test_name: str) -> str:
  """Strips a trailing numeric iteration suffix (e.g. '_0') if present."""
  parts = test_name.rsplit("_", 1)
  if len(parts) == 2 and parts[1].isdigit():
    return parts[0]
  return test_name


def _get_scenarios_for_class(
    metrics_data: dict[str, Any], class_name: str
) -> dict[str, Any]:
  """Extracts the scenarios dictionary for a given test class."""
  test_classes = metrics_data.get("test_classes", {})
  class_data = {}
  if isinstance(test_classes, list):
    for item in test_classes:
      if item.get("key") == class_name:
        class_data = item.get("value", {})
        break
  else:
    class_data = test_classes.get(class_name, {})

  scenarios = class_data.get("scenarios", {})
  if isinstance(scenarios, list):
    return {
        item["key"]: item.get("value", {})
        for item in scenarios
        if item.get("key")
    }
  return scenarios


_INPUT_DIR = flags.DEFINE_string(
    "input_dir",
    None,
    "Path to BeToCQ/Mobly output directory",
)
_OUTPUT_DIR = flags.DEFINE_string(
    "output_dir",
    None,
    "Path to output directory for the report ZIP (default:"
    " /tmp/betocq/results)",
)
_RESULTSTORE_LINK = flags.DEFINE_string(
    "resultstore_link", None, "ResultStore link for the test run"
)
_INCLUDE_METRICS = flags.DEFINE_boolean(
    "include_metrics",
    False,
    "Controls metrics inclusion in XML. If True, includes detailed"
    " per-iteration telemetry and numeric/boolean/text metrics inline within"
    " the test_result.xml tags. If False (default), only outputs high-level"
    " status like standard GTS.",
)
_AGGREGATE_ITERATIONS = flags.DEFINE_boolean(
    "aggregate_iterations",
    True,
    "Controls iteration output format. If True (default), repetitive iteration"
    " suffixes (e.g., _0, _1) are merged/condensed into a single test case"
    " matching strict GTS delivery styles. If False, every record remains"
    " uncoupled.",
)


def parse_test_summary(input_dir: str) -> dict[str, Any]:
  """Parses test_summary.yaml to get test hierarchy and results."""
  input_dir = os.path.expanduser(input_dir)
  yaml_path = os.path.join(input_dir, "test_summary.yaml")
  logging.info("Parsing %s", yaml_path)
  try:
    with open(yaml_path, "r", encoding="utf-8") as f:
      docs = list(yaml.safe_load_all(f))
  except FileNotFoundError as e:
    raise FileNotFoundError(
        f"test_summary.yaml not found in {input_dir}"
    ) from e

  # Default values for APA-required fields
  apa_info = {
      "apa_module_name": "betocq_test_suite",
      "enforce_same_fingerprint": False,
      "apa_suite_plan": "",
      "all_test_must_pass": False,
      "apa_target_device": "",
  }
  results: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
  build_info = {}
  device_serials = []
  mobly_properties = {}
  all_controllers = []

  start_times = []
  end_times = []

  for doc in docs:
    if not doc:
      continue
    entry_type = doc.get("Type")

    if entry_type == records.TestSummaryEntryType.RECORD.value:
      class_name = doc.get(records.TestResultEnums.RECORD_CLASS)
      test_name = doc.get(records.TestResultEnums.RECORD_NAME)
      result = doc.get(records.TestResultEnums.RECORD_RESULT)
      details = doc.get(records.TestResultEnums.RECORD_DETAILS)
      stacktrace = doc.get(records.TestResultEnums.RECORD_STACKTRACE)

      begin_time = doc.get(records.TestResultEnums.RECORD_BEGIN_TIME)
      end_time = doc.get(records.TestResultEnums.RECORD_END_TIME)

      if begin_time:
        start_times.append(begin_time)
      if end_time:
        end_times.append(end_time)

      if not class_name or not test_name:
        continue

      results[class_name][test_name] = {
          "result": result,
          "details": details,
          "stacktrace": stacktrace,
          "termination_signal_type": doc.get(
              records.TestResultEnums.RECORD_TERMINATION_SIGNAL_TYPE
          ),
      }
    elif entry_type == records.TestSummaryEntryType.CONTROLLER_INFO.value:
      controllers = (
          doc.get(records.ControllerInfoRecord.KEY_CONTROLLER_INFO) or []
      )
      all_controllers.extend(controllers)
      for controller in controllers:
        if not isinstance(controller, dict):
          continue
        serial = controller.get("serial")
        if not serial:
          continue
        serials = serial if isinstance(serial, list) else [serial]
        for s in serials:
          s_str = str(s)
          if s_str not in device_serials:
            device_serials.append(s_str)
    elif entry_type == records.TestSummaryEntryType.USER_DATA.value:
      properties = doc.get("properties", {})
      if isinstance(properties, dict):
        for key, value in properties.items():
          # Strip digit prefix like "00_"
          clean_key = key
          parts = key.split("_", 1)
          if len(parts) == 2 and parts[0].isdigit():
            clean_key = parts[1]

          mobly_properties[clean_key] = value

          if clean_key in apa_info:
            apa_info[clean_key] = value
          elif clean_key == "apa_info" and isinstance(value, dict):
            # Handle nested apa_info dictionary
            for sub_key, sub_value in value.items():
              if sub_key in apa_info:
                apa_info[sub_key] = sub_value

  # Identify target device using apa_target_device (serial) from apa_info
  if all_controllers:
    target_controller = None
    target_serial = apa_info.get("apa_target_device")

    if target_serial:
      for controller in all_controllers:
        if isinstance(controller, dict) and str(
            controller.get("serial")
        ) == str(target_serial):
          target_controller = controller
          break

    if not target_controller:
      logging.warning(
          "Target device '%s' not found in controller info; falling back to "
          "first controller.",
          target_serial,
      )
      target_controller = all_controllers[0]

    if isinstance(target_controller, dict):
      build_info = dict(target_controller.get("build_info", {}))
      user_added_info = target_controller.get("user_added_info", {})
      build_info.update(user_added_info)
      if "product_model" not in build_info and "model" in target_controller:
        build_info["product_model"] = target_controller["model"]

  all_test_must_pass = apa_info.get("all_test_must_pass", False)
  if isinstance(all_test_must_pass, str):
    all_test_must_pass = all_test_must_pass.lower() == "true"
  apa_info["all_test_must_pass"] = bool(all_test_must_pass)

  # Validate same build fingerprint if enforced
  enforce_same_fingerprint = apa_info.get("enforce_same_fingerprint")
  if isinstance(enforce_same_fingerprint, str):
    enforce_same_fingerprint = enforce_same_fingerprint.lower() == "true"

  if enforce_same_fingerprint and len(all_controllers) > 1:
    fingerprints = set()
    for controller in all_controllers:
      if isinstance(controller, dict):
        fingerprint = controller.get("build_info", {}).get("build_fingerprint")
        if fingerprint:
          fingerprints.add(fingerprint)

    if len(fingerprints) > 1:
      raise ValueError(
          "Enforce same build fingerprint is set, but devices have different "
          f"fingerprints: {fingerprints}"
      )

  return {
      "results": dict(results),
      "build_info": build_info,
      "device_serials": device_serials,
      "apa_info": apa_info,
      "mobly_properties": mobly_properties,
      "start_time": min(start_times) if start_times else 0,
      "end_time": max(end_times) if end_times else 0,
  }


def get_scenario_metrics(
    metrics_data: dict[str, Any], class_name: str, base_name: str
) -> dict[str, Any]:
  """Retrieves aggregated metrics for a specific scenario base_name."""
  scenarios_dict = _get_scenarios_for_class(metrics_data, class_name)
  scenario_data = scenarios_dict.get(base_name, {})

  normalized_scenario: dict[str, Any] = {"test_name": base_name}

  # Initialize buckets
  for bucket in _METRIC_BUCKETS:
    normalized_scenario[bucket] = {}

  # Add hero metric if present
  if "file_transfer_throughput_med" in scenario_data:
    normalized_scenario["numeric_metrics"]["file_transfer_throughput_med"] = (
        scenario_data["file_transfer_throughput_med"]
    )

  # Normalize standard buckets
  for bucket in _METRIC_BUCKETS:
    raw_bucket = scenario_data.get(bucket, [])
    if isinstance(raw_bucket, list):
      for item in raw_bucket:
        k = item.get("key")
        v = item.get("value")
        if k is not None:
          normalized_scenario[bucket][k] = v
    elif isinstance(raw_bucket, dict):
      normalized_scenario[bucket].update(raw_bucket)

  return normalized_scenario


def get_iteration_metrics(
    metrics_data: dict[str, Any], class_name: str, test_name: str
) -> dict[str, Any]:
  """Retrieves metrics for a specific iteration test_name."""
  scenarios_dict = _get_scenarios_for_class(metrics_data, class_name)

  # Try direct match first (e.g. for function tests or base names)
  if test_name in scenarios_dict:
    scenario_data = scenarios_dict[test_name]
  else:
    base_name = _get_base_test_name(test_name)
    scenario_data = scenarios_dict.get(base_name, {})

  iterations = scenario_data.get("iterations", [])

  for iter_data in iterations:
    if iter_data.get("test_name") != test_name:
      continue
    # Normalize buckets to standard dicts
    normalized_iter: dict[str, Any] = {"test_name": test_name}
    for bucket in _METRIC_BUCKETS:
      raw_bucket = iter_data.get(bucket, [])
      bucket_dict = {}
      if isinstance(raw_bucket, list):
        for item in raw_bucket:
          k = item.get("key")
          v = item.get("value")
          if k is not None:
            bucket_dict[k] = v
      else:
        bucket_dict = raw_bucket
      normalized_iter[bucket] = bucket_dict
    return normalized_iter

  return {}


def generate_simple_html(
    yaml_results: dict[str, dict[str, dict[str, Any]]],
    metrics_data: dict[str, Any],
    html_path: str,
    all_test_must_pass: bool = False,
    aggregate_iterations: bool = True,
) -> None:
  """Generates a simple viewable HTML report."""
  logging.info("Generating HTML report to %s", html_path)

  suite_name = _APA_SUITE_NAME

  html_parts: list[str] = [textwrap.dedent(f"""\
        <html>
        <head>
            <title>{suite_name} Test Report</title>
            <style>
                body {{ font-family: sans-serif; margin: 20px; }}
                h1, h2 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .pass {{ color: green; font-weight: bold; }}
                .fail {{ color: red; font-weight: bold; }}
                .warning {{ color: orange; font-weight: bold; }}
                .skip {{ color: blue; font-weight: bold; }}
                .metric-group {{ margin-left: 20px; }}
                .pass-cell {{ background-color: #d4edda; color: #155724; }}
                .fail-cell {{ background-color: #f8d7da; color: #721c24; }}
                .warning-cell {{ background-color: #ffeeba; color: #856404; }}
                .skip-cell {{ background-color: #d1ecf1; color: #0c5460; }}
            </style>
        </head>
        <body>
            <h1>{suite_name} Test Report</h1>
      """)]

  for class_name, tests in yaml_results.items():
    html_parts.append(f"<h2>Test Class: {class_name}</h2>")

    # --- Calculate Aggregated Summary for the Class ---
    aggregated_summary: dict[str, dict[str, Any]] = {}
    for test_name, test_data in tests.items():
      base_name = _get_base_test_name(test_name)

      raw_result = test_data.get("result", "fail").lower()
      termination_signal_type = test_data.get("termination_signal_type")
      apa_status = get_apa_status(
          raw_result, termination_signal_type, all_test_must_pass
      )

      if base_name not in aggregated_summary:
        aggregated_summary[base_name] = {
            "result": apa_status,
            "counts": collections.Counter(),
        }
      else:
        current_status = aggregated_summary[base_name]["result"]
        if _STATUS_PRIORITY.index(apa_status) < _STATUS_PRIORITY.index(
            current_status
        ):
          aggregated_summary[base_name]["result"] = apa_status

      aggregated_summary[base_name]["counts"][apa_status] += 1

    # --- Render Class Summary Table ---
    html_parts.append("<h3>Class Summary (Aggregated)</h3>")
    html_parts.append(
        "<table><tr><th>Scenario</th><th>Aggregated"
        " Status</th><th>Pass</th><th>Fail</th><th>Warning</th><th>Ignored</th></tr>"
    )
    for base_name, summary in aggregated_summary.items():
      status_counts = summary["counts"]
      status_val = summary["result"]

      if status_val == _APA_STATUS_PASS:
        status_class = "pass"
      elif status_val == _APA_STATUS_IGNORED:
        status_class = "skip"
      elif status_val == _APA_STATUS_WARNING:
        status_class = "warning"
      else:
        status_class = "fail"

      html_parts.append(textwrap.dedent(f"""\
        <tr>
          <td>{base_name}</td>
          <td class="{status_class}-cell"><span class="{status_class}">{status_val}</span></td>
          <td>{status_counts[_APA_STATUS_PASS]}</td>
          <td>{status_counts[_APA_STATUS_FAIL]}</td>
          <td>{status_counts[_APA_STATUS_WARNING]}</td>
          <td>{status_counts[_APA_STATUS_IGNORED]}</td>
        </tr>
      """))
    html_parts.append("</table>")

    html_parts.append(textwrap.dedent("""\
      <details style="margin-bottom: 15px;">
        <summary style="cursor: pointer; font-weight: bold; color: #555;">Click to Expand/Collapse Test Details</summary>
        <div style="margin-left: 20px; margin-top: 10px;">
    """))

    display_tests: dict[str, dict[str, Any]] = tests
    if aggregate_iterations:
      aggregated_tests: dict[str, dict[str, Any]] = {}
      for test_name, test_data in tests.items():
        base_name = _get_base_test_name(test_name)

        raw_result = test_data.get("result", "fail").lower()
        termination_signal_type = test_data.get("termination_signal_type")
        apa_status = get_apa_status(
            raw_result, termination_signal_type, all_test_must_pass
        )

        if base_name not in aggregated_tests:
          aggregated_tests[base_name] = {
              "result": apa_status,
              "raw_result": raw_result,
              "failures": [],
          }
        else:
          current_status = aggregated_tests[base_name]["result"]
          if _STATUS_PRIORITY.index(apa_status) < _STATUS_PRIORITY.index(
              current_status
          ):
            aggregated_tests[base_name]["result"] = apa_status
            aggregated_tests[base_name]["raw_result"] = raw_result

        if apa_status != _APA_STATUS_PASS:
          aggregated_tests[base_name]["failures"].append({
              "original_name": test_name,
              "apa_status": apa_status,
              "details": test_data.get("details"),
              "stacktrace": test_data.get("stacktrace"),
          })
      display_tests = aggregated_tests

    for test_name, test_data in display_tests.items():
      if aggregate_iterations:
        apa_status = test_data["result"]
      else:
        raw_result = test_data.get("result", "fail").lower()
        termination_signal_type = test_data.get("termination_signal_type")
        apa_status = get_apa_status(
            raw_result, termination_signal_type, all_test_must_pass
        )

      if apa_status == _APA_STATUS_PASS:
        result_class = "pass"
      elif apa_status == _APA_STATUS_IGNORED:
        result_class = "skip"
      elif apa_status == _APA_STATUS_WARNING:
        result_class = "warning"
      else:
        result_class = "fail"

      html_parts.append(textwrap.dedent(f"""\
        <div style="border: 1px solid #ddd; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
          <h4>Test: {test_name} - <span class="{result_class}">{apa_status}</span></h4>
      """))

      if aggregate_iterations:
        failures = test_data.get("failures", [])
        if failures:
          html_parts.append("<h5>Non-Passing Iteration Diagnostics</h5>")
          for f in failures:
            f_status = f["apa_status"]
            if f_status == _APA_STATUS_IGNORED:
              f_class = "skip"
            elif f_status == _APA_STATUS_WARNING:
              f_class = "warning"
            else:
              f_class = "fail"

            html_parts.append(textwrap.dedent(f"""\
              <div style="border-bottom: 1px dashed #ccc; padding-bottom: 10px; margin-bottom: 10px;">
                <p><strong>Iteration:</strong> {f['original_name']}</p>
                <p><strong>Status:</strong> <span class="{f_class}">{f_status}</span></p>
                <p><strong>Details:</strong> {f.get('details')}</p>
                <p><strong>Stacktrace:</strong> <pre style='white-space: pre-wrap; background-color: #f8f9fa; padding: 10px; border: 1px solid #ddd;'>{f.get('stacktrace')}</pre></p>
              </div>
            """))
      else:
        if test_data.get("details"):
          html_parts.append(
              f"<p><strong>Details:</strong> {test_data.get('details')}</p>"
          )
        if test_data.get("stacktrace"):
          html_parts.append(
              "<p><strong>Stacktrace:</strong> <pre style='white-space:"
              " pre-wrap; background-color: #f8f9fa; padding: 10px; border:"
              f" 1px solid #ddd;'>{test_data.get('stacktrace')}</pre></p>"
          )

      if aggregate_iterations:
        test_metrics = get_scenario_metrics(metrics_data, class_name, test_name)
      else:
        test_metrics = get_iteration_metrics(
            metrics_data, class_name, test_name
        )

      if test_metrics:
        for bucket in _METRIC_BUCKETS:
          metrics = test_metrics.get(bucket, {})
          if metrics:
            html_parts.append(f"<h5>{bucket.replace('_', ' ').title()}</h5>")
            html_parts.append("<table><tr><th>Key</th><th>Value</th></tr>")
            for k, v in metrics.items():
              html_parts.append(f"<tr><td>{k}</td><td>{v}</td></tr>")
            html_parts.append("</table>")

      html_parts.append("</div>")
    html_parts.append("</div></details>")

  html_parts.append("</body></html>")

  with open(html_path, "w", encoding="utf-8") as f:
    f.write("".join(html_parts))


def get_apa_status(
    raw_result: str,
    termination_signal_type: str | None,
    all_test_must_pass: bool = False,
) -> str:
  """Determines APA status based on Mobly result and termination signal."""
  if termination_signal_type in _FAILURE_TERMINATION_SIGNAL_TYPES:
    return _APA_STATUS_FAIL
  if raw_result in ("fail", "error"):
    return _APA_STATUS_FAIL if all_test_must_pass else _APA_STATUS_WARNING
  if raw_result == "pass":
    return _APA_STATUS_PASS
  if raw_result == "skip":
    return _APA_STATUS_IGNORED
  return _APA_STATUS_FAIL


def _populate_module_element(
    root: ET.Element,
    summary_data: dict[str, Any],
    metrics_data: dict[str, Any],
    include_metrics: bool,
    aggregate_iterations: bool,
    all_test_must_pass: bool,
    total_status_counts: collections.Counter[str],
) -> bool:
  """Appends a <Module> element to root and returns True if the module is done."""
  results = summary_data.get("results", {})
  apa_info = summary_data.get("apa_info", {})
  module = ET.SubElement(root, "Module")
  module.set("name", apa_info.get("apa_module_name", "betocq_test_suite"))

  module_counts: collections.Counter[str] = collections.Counter()

  for class_name, tests in results.items():
    test_case = ET.SubElement(module, "TestCase")
    test_case.set("name", class_name)

    display_tests = tests
    if aggregate_iterations:
      aggregated_tests = {}
      for test_name, test_data in tests.items():
        base_name = _get_base_test_name(test_name)

        raw_result = test_data.get("result", "fail").lower()
        termination_signal_type = test_data.get("termination_signal_type")
        apa_status = get_apa_status(
            raw_result, termination_signal_type, all_test_must_pass
        )

        if base_name not in aggregated_tests:
          aggregated_tests[base_name] = {
              "result": apa_status,
              "details": test_data.get("details"),
              "stacktrace": test_data.get("stacktrace"),
              "raw_result": raw_result,
              "original_name": test_name,
          }
        else:
          current_status = aggregated_tests[base_name]["result"]
          if _STATUS_PRIORITY.index(apa_status) < _STATUS_PRIORITY.index(
              current_status
          ):
            aggregated_tests[base_name]["result"] = apa_status
            aggregated_tests[base_name]["details"] = test_data.get("details")
            aggregated_tests[base_name]["stacktrace"] = test_data.get(
                "stacktrace"
            )
            aggregated_tests[base_name]["raw_result"] = raw_result
            aggregated_tests[base_name]["original_name"] = test_name
      display_tests = aggregated_tests

    for test_name, test_data in display_tests.items():
      test_element = ET.SubElement(test_case, "Test")
      test_element.set("name", test_name)

      if aggregate_iterations:
        apa_status = test_data["result"]
      else:
        raw_result = test_data.get("result", "fail").lower()
        termination_signal_type = test_data.get("termination_signal_type")
        apa_status = get_apa_status(
            raw_result, termination_signal_type, all_test_must_pass
        )

      test_element.set("result", apa_status)

      module_counts[apa_status] += 1
      total_status_counts[apa_status] += 1

      if apa_status == _APA_STATUS_IGNORED:
        test_element.set("skipped", "true")
      elif apa_status in (
          _APA_STATUS_FAIL,
          _APA_STATUS_WARNING,
      ):
        failure = ET.SubElement(test_element, "Failure")
        failure.set("message", test_data.get("details") or "")
        if test_data.get("stacktrace"):
          stack_trace = ET.SubElement(failure, "StackTrace")
          stack_trace.text = test_data.get("stacktrace")

      if include_metrics:
        if aggregate_iterations:
          test_metrics = get_scenario_metrics(
              metrics_data, class_name, test_name
          )
        else:
          test_metrics = get_iteration_metrics(
              metrics_data, class_name, test_name
          )

        for bucket in _METRIC_BUCKETS:
          for k, v in test_metrics.get(bucket, {}).items():
            metric = ET.SubElement(test_element, "Metric")
            metric.set("key", k)
            metric.text = str(v)

  module_done = module_counts[_APA_STATUS_FAIL] == 0
  module.set("done", str(module_done).lower())
  module.set("pass", str(module_counts[_APA_STATUS_PASS]))
  return module_done


def convert_to_xml(
    summary_data: dict[str, Any],
    metrics_data: dict[str, Any],
    xml_path: str,
    include_metrics: bool = False,
    aggregate_iterations: bool = True,
    all_test_must_pass: bool = False,
    additional_modules: (
        Sequence[tuple[dict[str, Any], dict[str, Any]]] | None
    ) = None,
) -> None:
  """Converts one or more BeToCQ suite results to APA Compatibility Report XML."""
  logging.info("Generating XML report to %s", xml_path)

  build_info = summary_data.get("build_info", {})
  device_serials = list(summary_data.get("device_serials", []))
  apa_info = summary_data.get("apa_info", {})

  all_module_entries: list[tuple[dict[str, Any], dict[str, Any]]] = [
      (summary_data, metrics_data)
  ]
  if additional_modules:
    all_module_entries.extend(additional_modules)
    for extra_summary, _ in additional_modules:
      for s in extra_summary.get("device_serials", []):
        if s not in device_serials:
          device_serials.append(s)

  root = ET.Element("Result")

  # Hardcoded standard identifiers for APA routing
  suite_name = _APA_SUITE_NAME

  suite_plan = apa_info.get("apa_suite_plan")
  if not suite_plan:
    raise ValueError("apa_suite_plan cannot be empty in config.")

  # Set suite_version for APA XML from test_script_version
  mobly_properties = summary_data.get("mobly_properties", {})
  suite_version = str(mobly_properties.get("test_script_version", "1.0"))

  root.set("suite_name", suite_name)
  root.set("suite_variant", suite_name)
  root.set("suite_plan", suite_plan)
  root.set("suite_version", suite_version)
  root.set("report_version", "5.0")
  root.set("devices", ",".join(device_serials))

  start_times = [
      int(m_summary.get("start_time", 0) or 0)
      for m_summary, _ in all_module_entries
      if int(m_summary.get("start_time", 0) or 0) > 0
  ]
  end_times = [
      int(m_summary.get("end_time", 0) or 0)
      for m_summary, _ in all_module_entries
      if int(m_summary.get("end_time", 0) or 0) > 0
  ]
  start_time_ms = min(start_times) if start_times else 0
  end_time_ms = max(end_times) if end_times else 0

  root.set("start", str(start_time_ms))
  root.set("end", str(end_time_ms))

  # Add formatted UTC display times
  time_format = "%a %b %d %H:%M:%S UTC %Y"
  if isinstance(start_time_ms, (int, float)) and start_time_ms > 0:
    start_dt = datetime.datetime.fromtimestamp(
        start_time_ms / 1000.0, datetime.timezone.utc
    )
    root.set("start_display", start_dt.strftime(time_format))

  if isinstance(end_time_ms, (int, float)) and end_time_ms > 0:
    end_dt = datetime.datetime.fromtimestamp(
        end_time_ms / 1000.0, datetime.timezone.utc
    )
    root.set("end_display", end_dt.strftime(time_format))

  # Add host properties
  for k, v in _get_host_properties().items():
    root.set(k, v)

  # Add Build element
  build_element = ET.SubElement(root, "Build")

  android_version = build_info.get("android_version")
  if not android_version:
    fingerprint = build_info.get("build_fingerprint")
    if fingerprint and ":" in fingerprint:
      try:
        android_version = fingerprint.split(":")[1].split("/")[0]
      except IndexError:
        pass

  mapped_build_fields = {
      "build_fingerprint": build_info.get("build_fingerprint"),
      "build_product": build_info.get("product_name"),
      "build_type": build_info.get("build_type"),
      "build_version_incremental": build_info.get("build_version_incremental"),
      "build_version_sdk": build_info.get("build_version_sdk"),
      "build_version_release": android_version or _MISSING_VALUE,
      "build_model": build_info.get("product_model", _MISSING_VALUE),
      "build_manufacturer": build_info.get(
          "product_manufacturer", _MISSING_VALUE
      ),
      "build_id": build_info.get("build_id"),
  }
  for k, v in mapped_build_fields.items():
    if v:
      build_element.set(k, str(v))

  summary_element = ET.SubElement(root, "Summary")

  status_counts: collections.Counter[str] = collections.Counter()
  modules_done_count = 0
  for mod_summary, mod_metrics in all_module_entries:
    mod_apa_info = mod_summary.get("apa_info", {})
    mod_must_pass = all_test_must_pass or bool(
        mod_apa_info.get("all_test_must_pass", False)
    )
    if _populate_module_element(
        root=root,
        summary_data=mod_summary,
        metrics_data=mod_metrics,
        include_metrics=include_metrics,
        aggregate_iterations=aggregate_iterations,
        all_test_must_pass=mod_must_pass,
        total_status_counts=status_counts,
    ):
      modules_done_count += 1

  # Update Summary counts across all modules in the test plan
  summary_element.set("pass", str(status_counts[_APA_STATUS_PASS]))
  summary_element.set("failed", str(status_counts[_APA_STATUS_FAIL]))
  summary_element.set("warning", str(status_counts[_APA_STATUS_WARNING]))
  summary_element.set("modules_done", str(modules_done_count))
  summary_element.set("modules_total", str(len(all_module_entries)))

  tree = ET.ElementTree(root)
  ET.indent(tree)
  tree.write(xml_path, encoding="utf-8", xml_declaration=True)


def _resolve_suite_input_dirs(input_dir: str | Sequence[str]) -> list[str]:
  """Resolves one or more Mobly suite directories from a path or list of paths."""
  if isinstance(input_dir, str):
    raw_dirs = [p.strip() for p in input_dir.split(",") if p.strip()]
  else:
    raw_dirs = [str(p).strip() for p in input_dir if str(p).strip()]

  resolved_dirs: list[str] = []
  for raw_dir in raw_dirs:
    expanded = os.path.expanduser(raw_dir)
    yaml_candidate = os.path.join(expanded, "test_summary.yaml")
    if os.path.isfile(yaml_candidate) or not os.path.isdir(expanded):
      resolved_dirs.append(expanded)
      continue
    # Support passing a parent directory containing multiple suite subdirs.
    subdir_candidates = sorted(
        os.path.join(expanded, entry)
        for entry in os.listdir(expanded)
        if os.path.isfile(os.path.join(expanded, entry, "test_summary.yaml"))
    )
    if subdir_candidates:
      resolved_dirs.extend(subdir_candidates)
    else:
      resolved_dirs.append(expanded)
  return resolved_dirs


def _load_suite_metrics(
    suite_dir: str,
    summary_data: dict[str, Any],
    resultstore_link: str | None,
) -> tuple[str, dict[str, Any]]:
  """Loads and enriches the <apa_module_name>.reportlog.json for a suite."""
  apa_info = summary_data.get("apa_info", {})
  apa_module_name = apa_info.get("apa_module_name", "betocq_test_suite")
  expected_metrics_name = f"{apa_module_name}.reportlog.json"
  json_path = os.path.join(suite_dir, "report-log-files", expected_metrics_name)

  metrics_data: dict[str, Any] = {}
  try:
    with open(json_path, "r", encoding="utf-8") as f:
      metrics_data = json.load(f)
  except FileNotFoundError:
    logging.warning(
        "Expected metrics file '%s' not found in %s",
        expected_metrics_name,
        os.path.join(suite_dir, "report-log-files"),
    )
    generic_json_path = os.path.join(
        suite_dir, "report-log-files", "metrics.json"
    )
    if os.path.exists(generic_json_path):
      logging.warning(
          "Metrics file name is not aligned. Expected "
          "'%s', but found 'metrics.json'.",
          expected_metrics_name,
      )
  except json.JSONDecodeError as e:
    raise ValueError(
        f"Failed to parse metrics JSON {expected_metrics_name}: {e}"
    ) from e

  if resultstore_link:
    metrics_data["result_store_link"] = resultstore_link

  mobly_properties = summary_data.get("mobly_properties", {})
  test_script_version = mobly_properties.get("test_script_version", "1.0")
  if "test_script_version" not in metrics_data:
    metrics_data["test_script_version"] = str(test_script_version)
  return expected_metrics_name, metrics_data


def _kv_or_dict_to_ordered_dict(raw: Any) -> collections.OrderedDict[str, Any]:
  """Normalizes a KV-list ([{'key': k, 'value': v}]) or dict into an OrderedDict."""
  out: collections.OrderedDict[str, Any] = collections.OrderedDict()
  if isinstance(raw, list):
    for item in raw:
      if isinstance(item, dict) and "key" in item:
        out[str(item["key"])] = item.get("value")
  elif isinstance(raw, dict):
    for k, v in raw.items():
      out[str(k)] = v
  return out


def _ordered_dict_to_kv_list(
    mapping: collections.OrderedDict[str, Any] | dict[str, Any],
) -> list[dict[str, Any]]:
  """Serializes a mapping into the ProtobufJsonConverter KV-list format."""
  return [{"key": k, "value": v} for k, v in mapping.items()]


def _compute_scenario_apa_status(
    scenario_tests: dict[str, dict[str, Any]],
    all_test_must_pass: bool,
) -> str:
  """Computes the aggregated APA status for all iterations of a scenario."""
  best_idx = len(_STATUS_PRIORITY) - 1
  for test_data in scenario_tests.values():
    raw_result = str(test_data.get("result", "fail")).lower()
    term_sig = test_data.get("termination_signal_type")
    apa_status = get_apa_status(raw_result, term_sig, all_test_must_pass)
    idx = _STATUS_PRIORITY.index(apa_status)
    if idx < best_idx:
      best_idx = idx
  return _STATUS_PRIORITY[best_idx]


def _merge_same_suite_metrics(
    run_metrics_list: Sequence[dict[str, Any]],
    winning_run_by_scenario: dict[tuple[str, str], int],
) -> dict[str, Any]:
  """Merges multiple `<apa_module_name>.reportlog.json` payloads from the same suite.

  When the same test suite is executed multiple times (e.g., retry of failed
  test cases or split runs covering different test classes/cases), this function
  merges `test_classes` and each class's `scenarios` so all test classes and
  test cases are preserved in a single `<apa_module_name>.reportlog.json` file.

  Args:
    run_metrics_list: Chronologically ordered metrics dicts for the same suite.
    winning_run_by_scenario: Mapping of `(class_name, scenario_base_name)` to
      the winning run index in `run_metrics_list`.

  Returns:
    A single merged metrics dictionary for `<apa_module_name>.reportlog.json`.
  """
  merged_classes: collections.OrderedDict[str, dict[str, Any]] = (
      collections.OrderedDict()
  )
  result_store_links: list[str] = []
  suite_name_val = ""
  script_version_val = ""
  wifi_chipset_val = ""
  extra_top_level: dict[str, Any] = {}

  for run_idx, m_data in enumerate(run_metrics_list):
    if not m_data:
      continue
    rs_link = str(m_data.get("result_store_link", "") or "").strip()
    if rs_link and rs_link not in result_store_links:
      result_store_links.append(rs_link)

    s_name = str(m_data.get("suite_name", "") or "").strip()
    if s_name:
      suite_name_val = s_name

    ver = str(m_data.get("test_script_version", "") or "").strip()
    if ver:
      script_version_val = ver

    chipset = str(m_data.get("wifi_chipset", "") or "").strip()
    if chipset:
      wifi_chipset_val = chipset

    for k, v in m_data.items():
      if k not in (
          "test_classes",
          "suite_name",
          "result_store_link",
          "test_script_version",
          "wifi_chipset",
      ):
        extra_top_level[k] = v

    raw_classes = _kv_or_dict_to_ordered_dict(m_data.get("test_classes", []))
    for cls_key, cls_val in raw_classes.items():
      if not isinstance(cls_val, dict):
        continue
      if cls_key not in merged_classes:
        cls_copy = dict(cls_val)
        cls_copy["class_metrics"] = _ordered_dict_to_kv_list(
            _kv_or_dict_to_ordered_dict(cls_copy.get("class_metrics", []))
        )
        cls_copy["scenarios"] = _ordered_dict_to_kv_list(
            _kv_or_dict_to_ordered_dict(cls_copy.get("scenarios", []))
        )
        merged_classes[cls_key] = cls_copy
        continue

      # Merge into existing TestClassRecord for cls_key
      existing_cls = merged_classes[cls_key]
      old_info = dict(existing_cls.get("test_info", {}) or {})
      new_info = dict(cls_val.get("test_info", {}) or {})
      merged_info = dict(old_info)
      merged_info.update(new_info)
      old_start = str(old_info.get("start_time", "") or "")
      new_start = str(new_info.get("start_time", "") or "")
      if old_start and new_start:
        merged_info["start_time"] = min(old_start, new_start)
      elif old_start or new_start:
        merged_info["start_time"] = old_start or new_start

      old_end = str(old_info.get("end_time", "") or "")
      new_end = str(new_info.get("end_time", "") or "")
      if old_end and new_end:
        merged_info["end_time"] = max(old_end, new_end)
      elif old_end or new_end:
        merged_info["end_time"] = old_end or new_end
      if merged_info:
        existing_cls["test_info"] = merged_info

      existing_cls_metrics = _kv_or_dict_to_ordered_dict(
          existing_cls.get("class_metrics", [])
      )
      new_cls_metrics = _kv_or_dict_to_ordered_dict(
          cls_val.get("class_metrics", [])
      )
      for k, v in new_cls_metrics.items():
        existing_cls_metrics[k] = v
      existing_cls["class_metrics"] = _ordered_dict_to_kv_list(
          existing_cls_metrics
      )

      existing_scenarios = _kv_or_dict_to_ordered_dict(
          existing_cls.get("scenarios", [])
      )
      new_scenarios = _kv_or_dict_to_ordered_dict(cls_val.get("scenarios", []))
      for scen_key, scen_val in new_scenarios.items():
        winner_idx = winning_run_by_scenario.get((cls_key, scen_key), run_idx)
        if scen_key not in existing_scenarios or winner_idx == run_idx:
          existing_scenarios[scen_key] = scen_val
      existing_cls["scenarios"] = _ordered_dict_to_kv_list(existing_scenarios)

  merged: dict[str, Any] = dict(extra_top_level)
  if merged_classes:
    merged["test_classes"] = _ordered_dict_to_kv_list(merged_classes)
  if result_store_links:
    non_placeholder = [
        l for l in result_store_links if l.upper() != "PLACEHOLDER"
    ]
    chosen_links = non_placeholder or result_store_links
    merged["result_store_link"] = ",".join(chosen_links)
  if suite_name_val:
    merged["suite_name"] = suite_name_val
  if script_version_val:
    merged["test_script_version"] = script_version_val
  if wifi_chipset_val:
    merged["wifi_chipset"] = wifi_chipset_val
  return merged


def _merge_same_suite_runs(
    module_runs: Sequence[tuple[str, dict[str, Any], str, dict[str, Any]]],
) -> tuple[
    list[tuple[str, dict[str, Any]]], dict[str, Any], str, dict[str, Any]
]:
  """Merges 1 or more runs of the same `apa_module_name` into a single bundle.

  Args:
    module_runs: Sequence of `(suite_dir, summary_data, m_filename, m_data)` for
      the same `apa_module_name`.

  Returns:
    Tuple of `(ordered_run_summaries, merged_summary_data, m_filename,
    merged_metrics_data)`.

  Raises:
    ValueError: If runs have different `build_fingerprint` values.
  """
  fingerprints = {
      str(s_data.get("build_info", {}).get("build_fingerprint", "") or "")
      for _, s_data, _, _ in module_runs
  }
  if len(fingerprints) > 1:
    raise ValueError(
        "Cannot merge runs with different build_fingerprint values: "
        f"{sorted(fingerprints)}"
    )

  if len(module_runs) == 1:
    s_dir, s_data, m_filename, m_data = module_runs[0]
    return [(s_dir, s_data)], s_data, m_filename, m_data

  # Sort chronologically by (start_time, end_time, original_index) so later
  # retry runs naturally supersede earlier runs.
  indexed_runs = list(enumerate(module_runs))
  indexed_runs.sort(
      key=lambda item: (
          int(item[1][1].get("start_time", 0) or 0),
          int(item[1][1].get("end_time", 0) or 0),
          item[0],
      )
  )
  ordered_runs = [r for _, r in indexed_runs]
  ordered_run_summaries = [(r[0], r[1]) for r in ordered_runs]
  m_filename = ordered_runs[-1][2]

  # Track winning run per (class_name, scenario_base_name):
  # value is (run_idx, scenario_apa_status, OrderedDict[test_name, test_data])
  scenario_winners: collections.OrderedDict[
      tuple[str, str],
      tuple[int, str, collections.OrderedDict[str, dict[str, Any]]],
  ] = collections.OrderedDict()
  class_order: list[str] = []

  for run_idx, (_, s_data, _, _) in enumerate(ordered_runs):
    must_pass = bool(
        s_data.get("apa_info", {}).get("all_test_must_pass", False)
    )
    for cls_name, cls_tests in s_data.get("results", {}).items():
      if cls_name not in class_order:
        class_order.append(cls_name)
      scenarios_in_run: collections.OrderedDict[
          str, collections.OrderedDict[str, dict[str, Any]]
      ] = collections.OrderedDict()
      for test_name, test_data in cls_tests.items():
        base_name = _get_base_test_name(test_name)
        if base_name not in scenarios_in_run:
          scenarios_in_run[base_name] = collections.OrderedDict()
        scenarios_in_run[base_name][test_name] = test_data

      for base_name, scen_tests in scenarios_in_run.items():
        scen_status = _compute_scenario_apa_status(scen_tests, must_pass)
        key = (cls_name, base_name)
        if key not in scenario_winners:
          scenario_winners[key] = (run_idx, scen_status, scen_tests)
        else:
          _, prev_status, _ = scenario_winners[key]
          if _RETRY_MERGE_PRIORITY.index(
              scen_status
          ) <= _RETRY_MERGE_PRIORITY.index(prev_status):
            scenario_winners[key] = (run_idx, scen_status, scen_tests)

  merged_results: dict[str, dict[str, dict[str, Any]]] = {
      cls_name: {} for cls_name in class_order
  }
  winning_run_by_scenario: dict[tuple[str, str], int] = {}
  for (cls_name, base_name), (
      win_idx,
      _,
      scen_tests,
  ) in scenario_winners.items():
    winning_run_by_scenario[(cls_name, base_name)] = win_idx
    merged_results[cls_name].update(scen_tests)

  # Merge summary metadata across runs
  base_summary = dict(ordered_runs[-1][1])
  device_serials: list[str] = []
  start_times: list[int] = []
  end_times: list[int] = []
  merged_build_info: dict[str, Any] = {}
  merged_mobly_props: dict[str, Any] = {}
  merged_apa_info: dict[str, Any] = {}

  for _, s_data, _, _ in ordered_runs:
    for s in s_data.get("device_serials", []):
      if s not in device_serials:
        device_serials.append(s)
    st = int(s_data.get("start_time", 0) or 0)
    if st > 0:
      start_times.append(st)
    et = int(s_data.get("end_time", 0) or 0)
    if et > 0:
      end_times.append(et)
    merged_build_info.update(s_data.get("build_info", {}))
    merged_mobly_props.update(s_data.get("mobly_properties", {}))
    merged_apa_info.update(s_data.get("apa_info", {}))

  base_summary["results"] = merged_results
  base_summary["device_serials"] = device_serials
  base_summary["build_info"] = merged_build_info
  base_summary["mobly_properties"] = merged_mobly_props
  base_summary["apa_info"] = merged_apa_info
  base_summary["start_time"] = min(start_times) if start_times else 0
  base_summary["end_time"] = max(end_times) if end_times else 0

  merged_metrics = _merge_same_suite_metrics(
      [r[3] for r in ordered_runs],
      winning_run_by_scenario,
  )
  return (
      ordered_run_summaries,
      base_summary,
      m_filename,
      merged_metrics,
  )


def _format_run_time_subfolder(
    summary_data: dict[str, Any], run_index: int
) -> str:
  """Formats a run's timestamp into a UTC run-time subfolder name."""
  ts = int(
      summary_data.get("start_time", 0) or summary_data.get("end_time", 0) or 0
  )
  if ts > 0:
    dt = datetime.datetime.fromtimestamp(ts / 1000.0, datetime.timezone.utc)
    return dt.strftime("%Y.%m.%d_%H.%M.%S.%f")[:-3]
  return f"run_{run_index + 1}"


def _stage_module_test_summaries(
    ordered_run_summaries: Sequence[tuple[str, dict[str, Any]]],
    mod_name: str,
    non_tf_module_dir: str,
) -> list[tuple[str, str]]:
  """Copies each run's `test_summary.yaml` into its own run-time subfolder."""
  staged: list[tuple[str, str]] = []
  used_subfolders: set[str] = set()
  for idx, (suite_dir, s_data) in enumerate(ordered_run_summaries):
    src_yaml = os.path.join(suite_dir, "test_summary.yaml")
    if not os.path.isfile(src_yaml):
      continue
    base_subfolder = _format_run_time_subfolder(s_data, idx)
    subfolder = base_subfolder
    collision_idx = 2
    while subfolder in used_subfolders:
      subfolder = f"{base_subfolder}_{collision_idx}"
      collision_idx += 1
    used_subfolders.add(subfolder)

    run_dir = os.path.join(non_tf_module_dir, subfolder)
    os.makedirs(run_dir, exist_ok=True)
    dest_yaml_path = os.path.join(run_dir, "test_summary.yaml")
    shutil.copy(src_yaml, dest_yaml_path)
    staged.append((
        dest_yaml_path,
        f"non-tradefed_results/{mod_name}/{subfolder}/test_summary.yaml",
    ))
  return staged


def package_for_apa(
    input_dir: str | Sequence[str],
    output_dir: str | None = None,
    resultstore_link: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    include_metrics: bool = False,
    aggregate_iterations: bool = True,
) -> None:
  """Packages one or more BeToCQ suite runs into an APA-compatible ZIP.

  Args:
    input_dir: Path (or comma-separated paths / sequence of paths) to BeToCQ/
      Mobly output directory(ies) belonging to the same test plan. If the same
      test suite (`apa_module_name`) was executed multiple times (e.g., retry or
      split runs across different test cases), its results and
      `<apa_module_name>.reportlog.json` metrics are automatically merged, while
      each run's original `test_summary.yaml` is preserved in its own run-time
      subfolder under `non-tradefed_results/<apa_module_name>/`.
    output_dir: Optional path to output directory. If None, uses
      /tmp/betocq/results.
    resultstore_link: Optional ResultStore link for the test run.
    start_time: Optional explicit start time (epoch ms). If None, calculated
      from tests.
    end_time: Optional explicit end time (epoch ms). If None, calculated from
      tests.
    include_metrics: If True, includes detailed per-iteration metrics in the
      XML.
    aggregate_iterations: If True, aggregates repeated test iterations to match
      GTS style.

  Raises:
    FileNotFoundError: If test_summary.yaml is not found in input_dir.
    ValueError: If the metrics JSON file cannot be parsed, required config is
      missing, or multiple runs/suites have mismatched test plans or
      build_fingerprint values.
  """
  suite_dirs = _resolve_suite_input_dirs(input_dir)
  if not suite_dirs:
    raise ValueError("input_dir must specify at least one directory.")
  if output_dir:
    output_dir = os.path.expanduser(output_dir)

  raw_runs_by_module: collections.OrderedDict[
      str, list[tuple[str, dict[str, Any], str, dict[str, Any]]]
  ] = collections.OrderedDict()
  suite_plans: set[str] = set()
  target_fingerprints: set[str] = set()

  for suite_dir in suite_dirs:
    s_data = parse_test_summary(suite_dir)
    if start_time is not None:
      s_data["start_time"] = start_time
    if end_time is not None:
      s_data["end_time"] = end_time
    m_filename, m_data = _load_suite_metrics(
        suite_dir, s_data, resultstore_link
    )
    plan_name = str(
        s_data.get("apa_info", {}).get("apa_suite_plan", "") or ""
    ).strip()
    if not plan_name:
      raise ValueError(
          f"apa_suite_plan cannot be empty in config for input: {suite_dir}"
      )
    suite_plans.add(plan_name)
    fp = str(s_data.get("build_info", {}).get("build_fingerprint", "") or "")
    target_fingerprints.add(fp)
    mod_name = str(
        s_data.get("apa_info", {}).get("apa_module_name", "betocq_test_suite")
        or "betocq_test_suite"
    )
    raw_runs_by_module.setdefault(mod_name, []).append(
        (suite_dir, s_data, m_filename, m_data)
    )

  if len(suite_plans) > 1:
    raise ValueError(
        "All suites packaged into a single APA ZIP must share the same "
        f"apa_suite_plan, but found: {sorted(suite_plans)}"
    )
  if len(target_fingerprints) > 1:
    raise ValueError(
        "All runs packaged into a single APA ZIP must target the same "
        f"build_fingerprint, but found: {sorted(target_fingerprints)}"
    )

  # Consolidate multiple executions of the same test suite (retries / split
  # runs).
  suite_bundles: list[
      tuple[
          list[tuple[str, dict[str, Any]]],
          dict[str, Any],
          str,
          dict[str, Any],
      ]
  ] = []
  for mod_name, module_runs in raw_runs_by_module.items():
    if len(module_runs) > 1:
      logging.info(
          "Merging %d runs for test suite '%s'", len(module_runs), mod_name
      )
    suite_bundles.append(_merge_same_suite_runs(module_runs))

  _, primary_summary, _, primary_metrics = suite_bundles[0]
  apa_info = primary_summary.get("apa_info", {})
  all_test_must_pass = bool(apa_info.get("all_test_must_pass", False))
  additional_modules = [
      (s_data, m_data) for _, s_data, _, m_data in suite_bundles[1:]
  ]
  if len(suite_bundles) == 1:
    merged_html_metrics = primary_metrics
  else:
    all_html_winners: dict[tuple[str, str], int] = {}
    for b_idx, (_, s_data, _, _) in enumerate(suite_bundles):
      for cls_name, cls_tests in s_data.get("results", {}).items():
        for t_name in cls_tests:
          all_html_winners[(cls_name, _get_base_test_name(t_name))] = b_idx
    merged_html_metrics = _merge_same_suite_metrics(
        [m_data for _, _, _, m_data in suite_bundles],
        all_html_winners,
    )

  # Combine yaml_results across all consolidated suites for HTML rendering
  combined_yaml_results: dict[str, dict[str, dict[str, Any]]] = {}
  for _, s_data, _, _ in suite_bundles:
    for cls_name, cls_tests in s_data.get("results", {}).items():
      if cls_name not in combined_yaml_results:
        combined_yaml_results[cls_name] = dict(cls_tests)
      else:
        combined_yaml_results[cls_name].update(cls_tests)

  # Determine output paths
  end_times = [
      int(s_data.get("end_time", 0) or 0) for _, s_data, _, _ in suite_bundles
  ]
  actual_end_time = max(end_times) if end_times else 0

  if output_dir is None:
    output_dir = "/tmp/betocq/results"

  # Convert actual_end_time to UTC string if it's a timestamp
  if isinstance(actual_end_time, (int, float)) and actual_end_time > 0:
    dt = datetime.datetime.fromtimestamp(
        actual_end_time / 1000.0, datetime.timezone.utc
    )
    base_formatted_time = dt.strftime("%Y.%m.%d_%H.%M.%S.%f")[:-3]
    random_suffix = random.randint(1000, 9999)
    formatted_end_time = f"{base_formatted_time}_{random_suffix}"
  else:
    formatted_end_time = str(actual_end_time)

  run_output_dir = os.path.join(output_dir, formatted_end_time)
  os.makedirs(run_output_dir, exist_ok=True)

  output_zip = os.path.join(output_dir, f"{formatted_end_time}.zip")

  # Paths for unzipped data
  xml_path = os.path.join(run_output_dir, "test_result.xml")
  html_path = os.path.join(run_output_dir, "test_result.html")

  # Generate XML and HTML directly in output dir
  convert_to_xml(
      primary_summary,
      primary_metrics,
      xml_path,
      include_metrics,
      aggregate_iterations,
      all_test_must_pass,
      additional_modules=additional_modules,
  )
  generate_simple_html(
      combined_yaml_results,
      merged_html_metrics,
      html_path,
      all_test_must_pass,
      aggregate_iterations,
  )

  report_log_dir = os.path.join(run_output_dir, "report-log-files")
  os.makedirs(report_log_dir, exist_ok=True)
  staged_metrics_files: list[tuple[str, str]] = []
  staged_yaml_files: list[tuple[str, str]] = []

  for (
      ordered_run_summaries,
      s_data,
      m_filename,
      m_data,
  ) in suite_bundles:
    mod_name = s_data.get("apa_info", {}).get(
        "apa_module_name", "betocq_test_suite"
    )
    metrics_output_path = os.path.join(report_log_dir, m_filename)
    with open(metrics_output_path, "w", encoding="utf-8") as f:
      json.dump(m_data, f, indent=2)
    staged_metrics_files.append(
        (metrics_output_path, f"report-log-files/{m_filename}")
    )

    non_tf_dir = os.path.join(run_output_dir, "non-tradefed_results", mod_name)
    os.makedirs(non_tf_dir, exist_ok=True)
    staged_yaml_files.extend(
        _stage_module_test_summaries(
            ordered_run_summaries, mod_name, non_tf_dir
        )
    )

  # Prepare device-info-files in output dir
  dest_edi_dir = os.path.join(run_output_dir, "device-info-files")
  os.makedirs(dest_edi_dir, exist_ok=True)

  found_edi = False
  for ordered_run_summaries, _, _, _ in suite_bundles:
    for suite_dir, _ in ordered_run_summaries:
      for root_dir, dirs, _ in os.walk(suite_dir):
        if "device-info-files" not in dirs:
          continue
        src_edi_dir = os.path.join(root_dir, "device-info-files")
        for filename in os.listdir(src_edi_dir):
          if filename.endswith(".json"):
            src_filepath = os.path.join(src_edi_dir, filename)
            dest_filepath = os.path.join(dest_edi_dir, filename)
            shutil.copy(src_filepath, dest_filepath)
            logging.info("Staged EDI file: %s", filename)
            found_edi = True
        break
      if found_edi:
        break
    if found_edi:
      break

  if not found_edi:
    logging.warning("device-info-files directory not found in input_dir tree.")

  # Create ZIP file
  logging.info("Creating ZIP file at %s", output_zip)
  with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
    zipf.write(xml_path, "test_result.xml")
    zipf.write(html_path, "test_result.html")
    for src_path, arc_path in staged_metrics_files:
      zipf.write(src_path, arc_path)

    if found_edi:
      for filename in os.listdir(dest_edi_dir):
        filepath = os.path.join(dest_edi_dir, filename)
        zipf.write(filepath, f"device-info-files/{filename}")
        logging.info("Added EDI file to ZIP: %s", filename)

    for src_path, arc_path in staged_yaml_files:
      zipf.write(src_path, arc_path)

  logging.info("Successfully packaged results for APA.")
  logging.info("ZIP report: %s", output_zip)
  logging.info("Unzipped artifacts directory: %s", run_output_dir)


def main(argv: Sequence[str]) -> None:
  """Validates CLI flags and packages BeToCQ results for APA."""
  if len(argv) > 1:
    raise app.UsageError("Too many command-line arguments.")
  if not _INPUT_DIR.value:
    raise app.UsageError("--input_dir is required.")

  package_for_apa(
      input_dir=_INPUT_DIR.value,
      output_dir=_OUTPUT_DIR.value,
      resultstore_link=_RESULTSTORE_LINK.value,
      include_metrics=_INCLUDE_METRICS.value,
      aggregate_iterations=_AGGREGATE_ITERATIONS.value,
  )


def cli_main() -> None:
  """Entry point for execution as a pip-installed console script."""
  flags.mark_flag_as_required("input_dir")
  logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
  app.run(main)


if __name__ == "__main__":
  cli_main()
