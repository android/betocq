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
    --input_dir=/path/to/mobly_logs \
    [--output_dir=/path/to/output/dir] \
    [--resultstore_link=https://btx.cloud.google.com/invocations/...]

Usage (Independent Script for OEMs):
  Prerequisites:
    pip install absl-py mobly PyYAML

  Command:
    python3 betocq_to_apa.py \
      --input_dir=/path/to/mobly_logs \
      [--output_dir=/path/to/output/dir]
      [--resultstore_link=https://btx.cloud.google.com/invocations/...]

Expected Input Directory Structure:
  <input_dir>/
    test_summary.yaml
    report-log-files/
      <apa_module_name>.reportlog.json

Output ZIP Structure (named <end_time>.zip):
  test_result.xml
  test_result.html
  report-log-files/
    <apa_module_name>.reportlog.json
  non-tradefed_results/
    <apa_module_name>/test_summary.yaml

Library Usage:
  from betocq.tools.apa_package import betocq_to_apa

  betocq_to_apa.package_for_apa(
      input_dir="/path/to/mobly_logs",
      output_dir="/path/to/output/dir", # Optional
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
import textwrap
from typing import Any
import xml.ElementTree as ET
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
    required=True,
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


def convert_to_xml(
    summary_data: dict[str, Any],
    metrics_data: dict[str, Any],
    xml_path: str,
    include_metrics: bool = False,
    aggregate_iterations: bool = True,
    all_test_must_pass: bool = False,
) -> None:
  """Converts results to APA Compatibility Report XML."""
  logging.info("Generating XML report to %s", xml_path)

  results = summary_data.get("results", {})
  build_info = summary_data.get("build_info", {})
  device_serials = summary_data.get("device_serials", [])
  apa_info = summary_data.get("apa_info", {})

  root = ET.Element("Result")

  # Hardcoded standard identifiers for APA routing
  suite_name = _APA_SUITE_NAME

  suite_plan = apa_info.get("apa_suite_plan")
  if not suite_plan:
    raise ValueError("apa_suite_plan cannot be empty in config.")

  # Calculate synthetic suite_version for APA XML
  mobly_properties = summary_data.get("mobly_properties", {})
  test_script_version = mobly_properties.get("test_script_version", "1.0")
  suite_version_property = mobly_properties.get("suite_version", "unknown")
  suite_version = f"{test_script_version}+{suite_version_property}"

  root.set("suite_name", suite_name)
  root.set("suite_variant", suite_name)
  root.set("suite_plan", suite_plan)
  root.set("suite_version", suite_version)
  root.set("report_version", "5.0")
  root.set("devices", ",".join(device_serials))

  start_time_ms = summary_data.get("start_time", 0)
  end_time_ms = summary_data.get("end_time", 0)

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

  # Single Module for BeToCQ
  module = ET.SubElement(root, "Module")
  module.set("name", apa_info.get("apa_module_name", "betocq_test_suite"))

  status_counts = collections.Counter()

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
              "raw_result": raw_result,  # Keep for metrics lookup if needed
              "original_name": (
                  test_name
              ),  # Keep one original name for metrics fallback
          }
        else:
          current_status = aggregated_tests[base_name]["result"]
          # Update status based on priority (FAILED > WARNING > IGNORED > pass)
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

      status_counts[apa_status] += 1

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

  # Update Summary counts
  summary_element.set("pass", str(status_counts[_APA_STATUS_PASS]))
  summary_element.set("failed", str(status_counts[_APA_STATUS_FAIL]))
  summary_element.set("warning", str(status_counts[_APA_STATUS_WARNING]))

  # Consider done if no blocking failures (FAIL). Warnings are non-blocking.
  done = status_counts[_APA_STATUS_FAIL] == 0
  summary_element.set("modules_done", "1" if done else "0")
  summary_element.set("modules_total", "1")

  module.set("done", str(done).lower())
  module.set("pass", str(status_counts[_APA_STATUS_PASS]))

  tree = ET.ElementTree(root)
  ET.indent(tree)
  tree.write(xml_path, encoding="utf-8", xml_declaration=True)


def package_for_apa(
    input_dir: str,
    output_dir: str | None = None,
    resultstore_link: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    include_metrics: bool = False,
    aggregate_iterations: bool = True,
) -> None:
  """Packages BeToCQ results into an APA-compatible ZIP.

  Args:
    input_dir: Path to BeToCQ/Mobly output directory.
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
    ValueError: If the metrics JSON file cannot be parsed or required config is
      missing.
  """
  # Expand user paths
  input_dir = os.path.expanduser(input_dir)
  if output_dir:
    output_dir = os.path.expanduser(output_dir)

  # Parse test_summary.yaml first
  summary_data = parse_test_summary(input_dir)
  yaml_results = summary_data["results"]
  apa_info = summary_data.get("apa_info", {})
  apa_module_name = apa_info.get("apa_module_name", "betocq_test_suite")
  all_test_must_pass = bool(apa_info.get("all_test_must_pass", False))

  # Override start/end time if explicitly provided
  if start_time is not None:
    summary_data["start_time"] = start_time
  if end_time is not None:
    summary_data["end_time"] = end_time

  # Verify metrics file alignment
  expected_metrics_name = f"{apa_module_name}.reportlog.json"
  json_path = os.path.join(input_dir, "report-log-files", expected_metrics_name)

  metrics_data: dict[str, Any] = {}
  try:
    with open(json_path, "r", encoding="utf-8") as f:
      metrics_data = json.load(f)
  except FileNotFoundError:
    logging.warning(
        "Expected metrics file '%s' not found in %s",
        expected_metrics_name,
        os.path.join(input_dir, "report-log-files"),
    )
    # Check if a generic metrics.json exists to provide a better warning
    generic_json_path = os.path.join(
        input_dir, "report-log-files", "metrics.json"
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
  suite_version = mobly_properties.get("suite_version", "unknown")
  metrics_data["test_script_version"] = f"{test_script_version}+{suite_version}"

  # Determine output paths
  actual_end_time = summary_data.get("end_time", 0)

  if output_dir is None:
    output_dir = "/tmp/betocq/results"

  # Convert actual_end_time to UTC string if it's a timestamp
  if isinstance(actual_end_time, (int, float)) and actual_end_time > 0:
    dt = datetime.datetime.fromtimestamp(
        actual_end_time / 1000.0, datetime.timezone.utc
    )
    # Format as YYYY.MM.DD_HH.MM.SS.SSS
    base_formatted_time = dt.strftime("%Y.%m.%d_%H.%M.%S.%f")[:-3]
    # Append a 4-digit random suffix like _1799
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
      summary_data,
      metrics_data,
      xml_path,
      include_metrics,
      aggregate_iterations,
      all_test_must_pass,
  )
  generate_simple_html(
      yaml_results,
      metrics_data,
      html_path,
      all_test_must_pass,
      aggregate_iterations,
  )

  # Prepare report-log-files in output dir
  report_log_dir = os.path.join(run_output_dir, "report-log-files")
  os.makedirs(report_log_dir, exist_ok=True)
  metrics_output_path = os.path.join(report_log_dir, expected_metrics_name)
  with open(metrics_output_path, "w", encoding="utf-8") as f:
    json.dump(metrics_data, f, indent=2)

  # Prepare non-tradefed_results in output dir
  non_tf_dir = os.path.join(
      run_output_dir, "non-tradefed_results", apa_module_name
  )
  os.makedirs(non_tf_dir, exist_ok=True)
  yaml_path = os.path.join(input_dir, "test_summary.yaml")
  dest_yaml_path = os.path.join(non_tf_dir, "test_summary.yaml")
  if os.path.exists(yaml_path):
    shutil.copy(yaml_path, dest_yaml_path)

  # Prepare device-info-files in output dir
  dest_edi_dir = os.path.join(run_output_dir, "device-info-files")
  os.makedirs(dest_edi_dir, exist_ok=True)

  # Find EDI files in input_dir
  found_edi = False
  for root, dirs, _ in os.walk(input_dir):
    if "device-info-files" not in dirs:
      continue
    src_edi_dir = os.path.join(root, "device-info-files")
    for filename in os.listdir(src_edi_dir):
      if filename.endswith(".json"):
        src_filepath = os.path.join(src_edi_dir, filename)
        dest_filepath = os.path.join(dest_edi_dir, filename)
        shutil.copy(src_filepath, dest_filepath)
        logging.info("Staged EDI file: %s", filename)
        found_edi = True
    break  # Assume only one such directory is needed or take the first one

  if not found_edi:
    logging.warning("device-info-files directory not found in input_dir tree.")

  # Create ZIP file
  logging.info("Creating ZIP file at %s", output_zip)
  with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
    zipf.write(xml_path, "test_result.xml")
    zipf.write(html_path, "test_result.html")
    zipf.write(metrics_output_path, f"report-log-files/{expected_metrics_name}")

    # Add staged EDI files
    if found_edi:
      for filename in os.listdir(dest_edi_dir):
        filepath = os.path.join(dest_edi_dir, filename)
        zipf.write(filepath, f"device-info-files/{filename}")
        logging.info("Added EDI file to ZIP: %s", filename)

    if os.path.exists(dest_yaml_path):
      zipf.write(
          dest_yaml_path,
          f"non-tradefed_results/{apa_module_name}/test_summary.yaml",
      )

  logging.info("Successfully packaged results for APA.")
  logging.info("ZIP report: %s", output_zip)
  logging.info("Unzipped artifacts directory: %s", run_output_dir)


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError("Too many command-line arguments.")

  package_for_apa(
      input_dir=_INPUT_DIR.value,
      output_dir=_OUTPUT_DIR.value,
      resultstore_link=_RESULTSTORE_LINK.value,
      include_metrics=_INCLUDE_METRICS.value,
      aggregate_iterations=_AGGREGATE_ITERATIONS.value,
  )


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
  app.run(main)
