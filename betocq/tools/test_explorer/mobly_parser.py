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

"""Parser and data aggregator for Mobly test_summary.yaml test results."""

import collections
import dataclasses
import enum
import os
import re
import shutil
import tempfile
from typing import Any
import zipfile
import yaml


@dataclasses.dataclass(frozen=True)
class TestAttemptRun:
  """Representation of a single attempt for a test case.

  Attributes:
    attempt: Attempt index number.
    result: Result status of the attempt.
    stacktrace: Error stacktrace string if the attempt failed.
    details: Failure details or execution summary message.
    is_fixture: Whether the execution attempt was a setup/teardown fixture.
  """

  attempt: int
  result: str
  stacktrace: str
  details: str
  is_fixture: bool


@dataclasses.dataclass(frozen=True)
class TestCaseItem:
  """Data representation of a single test case execution item.

  Attributes:
    name: Name of the test case.
    status: Overall result status of the test case.
    is_flaky: Whether the test case is flaky across attempts.
    attempts_count: Total number of execution attempts.
    runs: List of attempt runs.
    stacktrace: Error stacktrace string of the failure if applicable.
    details: Execution details or failure summary message.
    is_fixture: Whether this item represents a fixture execution.
  """

  name: str
  status: str
  is_flaky: bool
  attempts_count: int
  runs: list[TestAttemptRun]
  stacktrace: str
  details: str
  is_fixture: bool


@dataclasses.dataclass(frozen=True)
class TestGroup:
  """Representation of grouped repeated test case iterations.

  Attributes:
    base_name: Base name of the repeated test group.
    status: Aggregated status of the test group.
    total_repeats: Total number of repeated iterations.
    passed_repeats: Number of passed iterations.
    failed_repeats: Number of failed iterations.
    skipped_repeats: Number of skipped iterations.
    iterations: List of test case items.
  """

  base_name: str
  status: str
  total_repeats: int
  passed_repeats: int
  failed_repeats: int
  skipped_repeats: int
  iterations: list[TestCaseItem]


@dataclasses.dataclass(frozen=True)
class TestClassSummary:
  """Structured representation of a test class and its test cases.

  Attributes:
    name: Name of the test class.
    total_test_cases: Total count of unique test cases in the class.
    passed_test_cases: Count of passed test cases.
    failed_test_cases: Count of failed test cases.
    skipped_test_cases: Count of skipped test cases.
    total_executions: Total executions including attempts and repeats.
    test_cases: List of test case items in the class.
    test_groups: List of test groups in the class.
    cleanups: List of cleanup fixture items in the class.
  """

  name: str
  total_test_cases: int
  passed_test_cases: int
  failed_test_cases: int
  skipped_test_cases: int
  total_executions: int
  test_cases: list[TestCaseItem]
  test_groups: list[TestGroup]
  cleanups: list[TestCaseItem]


@dataclasses.dataclass(frozen=True)
class TestSummary:
  """Summary metrics for Mobly test execution.

  Attributes:
    requested: Total test cases requested to run.
    passed: Count of test cases that passed.
    failed: Count of test cases that failed.
    skipped: Count of test cases that were skipped.
    executed: Count of unique test cases executed.
    total_executions: Total executions across all test cases.
    exec_passed: Count of passed executions.
    exec_failed: Count of failed executions.
    exec_skipped: Count of skipped executions.
  """

  requested: int = 0
  passed: int = 0
  failed: int = 0
  skipped: int = 0
  executed: int = 0
  total_executions: int = 0
  exec_passed: int = 0
  exec_failed: int = 0
  exec_skipped: int = 0


@dataclasses.dataclass(frozen=True)
class ArtifactInfo:
  """Metadata for a test execution artifact file.

  Attributes:
    filename: Name of the artifact file.
    rel_path: Relative path to the artifact file.
    size_bytes: File size in bytes.
    size_formatted: Human-readable formatted file size.
    is_text: Whether the file is plain text.
  """

  filename: str
  rel_path: str
  size_bytes: int
  size_formatted: str
  is_text: bool


@dataclasses.dataclass(frozen=True)
class ParseResult:
  """Overall test explorer parsed results structure.

  Attributes:
    summary: Summary of test execution metrics.
    test_classes: Dictionary mapping test class names to their summaries.
    artifacts: List of artifact information objects.
    results_dir: Path to the parsed Mobly test results directory.
  """

  summary: TestSummary
  test_classes: dict[str, TestClassSummary]
  artifacts: list[ArtifactInfo] = dataclasses.field(default_factory=list)
  results_dir: str = ""


class TestResult(str, enum.Enum):
  """Mobly test result statuses."""

  PASS = "PASS"
  PASSED = "PASSED"
  SKIP = "SKIP"
  SKIPPED = "SKIPPED"
  FAIL = "FAIL"
  UNKNOWN = "UNKNOWN"


class MoblyYamlKey(str, enum.Enum):
  """Mobly test record YAML dictionary key names."""

  TYPE = "Type"
  TYPE_LOWER = "type"
  RECORD = "record"
  TEST_CLASS = "Test Class"
  TEST_CLASS_LOWER = "test_class"
  TEST_NAME = "Test Name"
  TEST_NAME_LOWER = "test_name"
  RESULT = "Result"
  RESULT_LOWER = "result"
  STACKTRACE = "Stacktrace"
  STACKTRACE_LOWER = "stacktrace"
  DETAILS = "Details"
  DETAILS_LOWER = "details"


UNKNOWN_CLASS = "UnknownClass"
UNKNOWN_TEST = "UnknownTest"
MOBLY_SUMMARY_FILENAME = "test_summary.yaml"
UPLOADED_ZIP_NAME = "uploaded.zip"

FIXTURE_PREFIXES = ("setup_", "teardown_", "clean_up", "cleanup")
FIXTURE_NAMES = (
    "setup_class",
    "teardown_class",
    "setup_test",
    "teardown_test",
    "clean_up",
    "cleanup",
)

TEXT_ARTIFACT_EXTENSIONS = (
    ".txt",
    ".log",
    ".yaml",
    ".yml",
    ".json",
    ".xml",
    ".html",
)


def is_fixture_or_cleanup(test_name: str) -> bool:
  """Checks if test name represents a setup, teardown, or cleanup fixture.

  Args:
    test_name: Name of the test case to check.

  Returns:
    True if the test name is a fixture or cleanup item, False otherwise.
  """
  t_lower = test_name.lower()
  return t_lower.startswith(FIXTURE_PREFIXES) or t_lower in FIXTURE_NAMES


def get_base_test_name(test_name: str) -> tuple[str, int]:
  """Extracts base test name and repetition index.

  Args:
    test_name: Raw name of the test case, which may include a repetition suffix
      (e.g., 'test_foo_1').

  Returns:
    A tuple containing the base test name and the repetition index (or 0 if not
    repeated).
  """
  m = re.fullmatch(r"(.*?)(?:_(\d+))?", test_name)
  if m:
    base = m.group(1)
    repeat = m.group(2)
    return base, int(repeat) if repeat else 0
  return test_name, 0


def _extract_raw_records(summary_path: str) -> list[dict[str, Any]]:
  """Loads YAML documents and filters test record dicts."""
  raw_records = []
  with open(summary_path, "r", encoding="utf-8") as f:
    docs = yaml.safe_load_all(f)
    for doc in docs:
      if not doc or not isinstance(doc, dict):
        continue

      doc_type = str(
          doc.get(MoblyYamlKey.TYPE.value)
          or doc.get(MoblyYamlKey.TYPE_LOWER.value)
          or ""
      ).strip().lower()
      if doc_type == MoblyYamlKey.RECORD.value or (
          not doc_type
          and (
              MoblyYamlKey.RESULT.value in doc
              or MoblyYamlKey.RESULT_LOWER.value in doc
          )
      ):
        raw_records.append(doc)
  return raw_records


def _group_records_by_class(
    raw_records: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, list[TestAttemptRun]]],
           collections.Counter[str]]:
  """Groups raw record dicts into test classes and tracks execution totals."""
  classes_map: dict[str, dict[str, list[TestAttemptRun]]] = {}
  exec_counts = collections.Counter()

  for doc in raw_records:
    test_class = str(
        doc.get(MoblyYamlKey.TEST_CLASS.value)
        or doc.get(MoblyYamlKey.TEST_CLASS_LOWER.value)
        or UNKNOWN_CLASS
    )
    test_name = str(
        doc.get(MoblyYamlKey.TEST_NAME.value)
        or doc.get(MoblyYamlKey.TEST_NAME_LOWER.value)
        or UNKNOWN_TEST
    )
    result_status = str(
        doc.get(MoblyYamlKey.RESULT.value)
        or doc.get(MoblyYamlKey.RESULT_LOWER.value)
        or TestResult.UNKNOWN.value
    ).upper()
    stacktrace = (
        doc.get(MoblyYamlKey.STACKTRACE.value)
        or doc.get(MoblyYamlKey.STACKTRACE_LOWER.value)
        or ""
    )
    details = str(
        doc.get(MoblyYamlKey.DETAILS.value)
        or doc.get(MoblyYamlKey.DETAILS_LOWER.value)
        or ""
    )

    is_fixture = is_fixture_or_cleanup(test_name)

    if not is_fixture:
      exec_counts["total"] += 1
      if result_status in (TestResult.PASS.value, TestResult.PASSED.value):
        exec_counts["passed"] += 1
      elif result_status in (TestResult.SKIP.value, TestResult.SKIPPED.value):
        exec_counts["skipped"] += 1
      else:
        exec_counts["failed"] += 1

    if test_class not in classes_map:
      classes_map[test_class] = {}

    if test_name not in classes_map[test_class]:
      classes_map[test_class][test_name] = []

    attempt_run = TestAttemptRun(
        attempt=len(classes_map[test_class][test_name]) + 1,
        result=result_status,
        stacktrace=stacktrace,
        details=details,
        is_fixture=is_fixture,
    )
    classes_map[test_class][test_name].append(attempt_run)

  return classes_map, exec_counts


def _build_test_case_item(
    test_name: str, runs: list[TestAttemptRun]
) -> TestCaseItem:
  """Constructs single test case data object including status and stacktrace."""
  is_fixture = is_fixture_or_cleanup(test_name)
  pass_statuses = (TestResult.PASS.value, TestResult.PASSED.value)
  skip_statuses = (TestResult.SKIP.value, TestResult.SKIPPED.value)

  has_pass = any(r.result in pass_statuses for r in runs)
  all_skip = all(r.result in skip_statuses for r in runs)
  has_fail_before_pass = has_pass and any(
      r.result not in pass_statuses and r.result not in skip_statuses
      for r in runs
  )

  if has_pass:
    overall_status = TestResult.PASS.value
  elif all_skip:
    overall_status = TestResult.SKIP.value
  else:
    overall_status = TestResult.FAIL.value

  latest_run = runs[-1]
  failing_run = next(
      (
          r
          for r in runs
          if r.result not in pass_statuses
          and r.result not in skip_statuses
      ),
      None,
  )
  display_stacktrace = (
      failing_run.stacktrace if failing_run else latest_run.stacktrace
  )

  return TestCaseItem(
      name=test_name,
      status=overall_status,
      is_flaky=has_fail_before_pass,
      attempts_count=len(runs),
      runs=runs,
      stacktrace=display_stacktrace,
      details=latest_run.details,
      is_fixture=is_fixture,
  )


def _build_test_groups(
    class_test_cases: list[TestCaseItem],
) -> list[TestGroup]:
  """Groups repeated test case iterations into base test name groups."""
  base_groups_dict: dict[str, list[TestCaseItem]] = {}
  for tc in class_test_cases:
    base_name, _ = get_base_test_name(tc.name)
    if base_name not in base_groups_dict:
      base_groups_dict[base_name] = []
    base_groups_dict[base_name].append(tc)

  pass_statuses = (TestResult.PASS.value, TestResult.PASSED.value)
  skip_statuses = (TestResult.SKIP.value, TestResult.SKIPPED.value)

  structured_groups = []
  for base_name, iterations in base_groups_dict.items():
    passed_count = sum(
        1 for it in iterations if it.status in pass_statuses
    )
    failed_count = sum(
        1
        for it in iterations
        if it.status not in pass_statuses
        and it.status not in skip_statuses
    )
    skipped_count = sum(
        1 for it in iterations if it.status in skip_statuses
    )
    total_count = len(iterations)

    if failed_count > 0:
      group_status = TestResult.FAIL.value
    elif passed_count > 0:
      group_status = TestResult.PASS.value
    else:
      group_status = TestResult.SKIP.value

    group = TestGroup(
        base_name=base_name,
        status=group_status,
        total_repeats=total_count,
        passed_repeats=passed_count,
        failed_repeats=failed_count,
        skipped_repeats=skipped_count,
        iterations=iterations,
    )
    structured_groups.append(group)

  return structured_groups


def _build_structured_class(
    class_name: str, tests_dict: dict[str, list[TestAttemptRun]]
) -> tuple[TestClassSummary, dict[str, int]]:
  """Assembles class metrics, test cases, cleanups, and base groups."""
  class_test_cases = []
  class_cleanups = []
  cls_passed = 0
  cls_failed = 0
  cls_skipped = 0
  cls_executions = 0

  for test_name, runs in tests_dict.items():
    item_data = _build_test_case_item(test_name, runs)

    if item_data.is_fixture:
      class_cleanups.append(item_data)
    else:
      cls_executions += len(runs)
      status = item_data.status
      if status == TestResult.PASS.value:
        cls_passed += 1
      elif status == TestResult.SKIP.value:
        cls_skipped += 1
      else:
        cls_failed += 1
      class_test_cases.append(item_data)

  structured_groups = _build_test_groups(class_test_cases)

  class_summary = TestClassSummary(
      name=class_name,
      total_test_cases=len(class_test_cases),
      passed_test_cases=cls_passed,
      failed_test_cases=cls_failed,
      skipped_test_cases=cls_skipped,
      total_executions=cls_executions,
      test_cases=class_test_cases,
      test_groups=structured_groups,
      cleanups=class_cleanups,
  )

  unique_counts = {
      "requested": len(class_test_cases),
      "passed": cls_passed,
      "failed": cls_failed,
      "skipped": cls_skipped,
  }

  return class_summary, unique_counts


def parse_mobly_summary(summary_path: str) -> ParseResult | dict[str, Any]:
  """Parses a Mobly test_summary.yaml and groups records by unique test cases.

  Args:
    summary_path: Path to the test_summary.yaml file to parse.

  Returns:
    A ParseResult object containing aggregated test summary metrics and class
    results, or a dictionary containing an 'error' message string if parsing
    fails.
  """
  if not os.path.exists(summary_path):
    return {"error": f"File not found: {summary_path}"}

  raw_records = _extract_raw_records(summary_path)
  classes_map, exec_counts = _group_records_by_class(raw_records)

  structured_classes = {}
  unique_totals = collections.Counter()

  for class_name, tests_dict in classes_map.items():
    cls_summary, cls_counts = _build_structured_class(class_name, tests_dict)
    structured_classes[class_name] = cls_summary
    unique_totals.update(cls_counts)

  summary = TestSummary(
      requested=unique_totals["requested"],
      passed=unique_totals["passed"],
      failed=unique_totals["failed"],
      skipped=unique_totals["skipped"],
      executed=unique_totals["requested"] - unique_totals["skipped"],
      total_executions=exec_counts["total"],
      exec_passed=exec_counts["passed"],
      exec_failed=exec_counts["failed"],
      exec_skipped=exec_counts["skipped"],
  )

  return ParseResult(
      summary=summary,
      test_classes=structured_classes,
  )


def format_file_size(size_bytes: int | float) -> str:
  """Formats byte counts into human-readable file size strings.

  Args:
    size_bytes: The file size in bytes.

  Returns:
    A formatted string representing the file size in B, KB, or MB.
  """
  if size_bytes < 1024:
    return f"{size_bytes} B"
  elif size_bytes < 1024 * 1024:
    return f"{size_bytes / 1024:.1f} KB"
  else:
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def collect_artifacts(results_dir: str) -> list[ArtifactInfo]:
  """Walks results directory and collects artifact file metadata.

  Args:
    results_dir: Path to the root results directory to scan for artifacts.

  Returns:
    A list of ArtifactInfo objects for all non-hidden files found within the
    results directory.
  """
  artifacts = []
  for root, _, files in os.walk(results_dir):
    for f in sorted(files):
      if f.startswith(".") or f == UPLOADED_ZIP_NAME:
        continue
      full_path = os.path.join(root, f)
      try:
        rel_path = os.path.relpath(full_path, results_dir)
        size_b = os.path.getsize(full_path)
      except OSError:
        continue
      art = ArtifactInfo(
          filename=f,
          rel_path=rel_path,
          size_bytes=size_b,
          size_formatted=format_file_size(size_b),
          is_text=f.endswith(TEXT_ARTIFACT_EXTENSIONS),
      )
      artifacts.append(art)
  return artifacts


def safe_extract_zip(zip_ref: zipfile.ZipFile, target_dir: str) -> bool:
  """Extracts zip archive entries verifying no member escapes target_dir.

  Args:
    zip_ref: An open ZipFile object to extract.
    target_dir: Destination directory path where files should be extracted.

  Returns:
    True if all files were safely extracted without directory traversal
    attempts, False otherwise.
  """
  resolved_target = os.path.abspath(target_dir)
  for member in zip_ref.infolist():
    member_path = os.path.abspath(
        os.path.join(resolved_target, member.filename)
    )
    if (
        not member_path.startswith(resolved_target + os.sep)
        and member_path != resolved_target
    ):
      return False
  zip_ref.extractall(target_dir)
  return True


def find_and_parse_results(results_dir: str) -> ParseResult | dict[str, Any]:
  """Finds test_summary.yaml in the directory or zip file and parses it.

  Args:
    results_dir: Path to the results directory or zip file.

  Returns:
    A ParseResult object with parsed metrics and artifact info, or a dictionary
    containing an 'error' key if the file is invalid, unsafe, or not found.
  """
  if not os.path.exists(results_dir):
    return {"error": f"Path not found: {results_dir}"}

  if os.path.isfile(results_dir):
    if not zipfile.is_zipfile(results_dir):
      return {"error": f"File is not a valid ZIP archive: {results_dir}"}

    temp_dir = tempfile.mkdtemp(prefix="betocq_explorer_")
    try:
      with zipfile.ZipFile(results_dir, "r") as zip_ref:
        is_safe = safe_extract_zip(zip_ref, temp_dir)
    except (zipfile.BadZipFile, OSError) as e:
      shutil.rmtree(temp_dir, ignore_errors=True)
      return {"error": f"Invalid ZIP file ({results_dir}): {e}"}

    if not is_safe:
      shutil.rmtree(temp_dir, ignore_errors=True)
      return {
          "error": (
              f"Zip archive contains unsafe path entries: {results_dir}"
          )
      }

    parsed = find_and_parse_results(temp_dir)
    if isinstance(parsed, dict) and "error" in parsed:
      shutil.rmtree(temp_dir, ignore_errors=True)
    return parsed

  for root, _, files in os.walk(results_dir):
    if MOBLY_SUMMARY_FILENAME in files:
      parsed = parse_mobly_summary(os.path.join(root, MOBLY_SUMMARY_FILENAME))
      if isinstance(parsed, ParseResult):
        artifacts = collect_artifacts(results_dir)
        return dataclasses.replace(
            parsed,
            artifacts=artifacts,
            results_dir=os.path.abspath(results_dir),
        )
      return parsed

  return {
      "error": f"{MOBLY_SUMMARY_FILENAME} not found in the provided directory."
  }
