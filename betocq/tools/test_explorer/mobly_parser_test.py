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

"""Unit tests for mobly_parser."""

import os
import zipfile

from absl.testing import absltest
import yaml

from betocq.tools.test_explorer import mobly_parser


class MoblyParserTest(absltest.TestCase):

  def test_is_fixture_or_cleanup(self) -> None:
    self.assertTrue(mobly_parser.is_fixture_or_cleanup("setup_class"))
    self.assertTrue(mobly_parser.is_fixture_or_cleanup("teardown_test"))
    self.assertTrue(mobly_parser.is_fixture_or_cleanup("clean_up"))
    self.assertTrue(mobly_parser.is_fixture_or_cleanup("cleanup"))
    self.assertTrue(mobly_parser.is_fixture_or_cleanup("setup_custom"))

    self.assertFalse(mobly_parser.is_fixture_or_cleanup("test_connect"))
    self.assertFalse(mobly_parser.is_fixture_or_cleanup("test_ble_scan"))

  def test_get_base_test_name(self) -> None:
    base_name, repeat = mobly_parser.get_base_test_name("test_wifi_connect_0")
    self.assertEqual(base_name, "test_wifi_connect")
    self.assertEqual(repeat, 0)

    base_name, repeat = mobly_parser.get_base_test_name("test_wifi_connect_19")
    self.assertEqual(base_name, "test_wifi_connect")
    self.assertEqual(repeat, 19)

    base_name, repeat = mobly_parser.get_base_test_name("test_wifi_connect")
    self.assertEqual(base_name, "test_wifi_connect")
    self.assertEqual(repeat, 0)

  def test_format_file_size(self) -> None:
    self.assertEqual(mobly_parser.format_file_size(512), "512 B")
    self.assertEqual(mobly_parser.format_file_size(1536), "1.5 KB")
    self.assertEqual(mobly_parser.format_file_size(2097152), "2.0 MB")

  def test_parse_mobly_summary_valid(self) -> None:
    records = [
        {
            "Type": "Record",
            "Test Class": "SampleTestClass",
            "Test Name": "test_pass",
            "Result": "PASS",
            "Details": "Passed successfully",
        },
        {
            "Type": "Record",
            "Test Class": "SampleTestClass",
            "Test Name": "test_fail",
            "Result": "FAIL",
            "Stacktrace": "AssertionError: failed",
            "Details": "Failed assertion",
        },
        {
            "Type": "Record",
            "Test Class": "SampleTestClass",
            "Test Name": "test_skip",
            "Result": "SKIP",
            "Details": "Skipped test",
        },
        {
            "Type": "Record",
            "Test Class": "SampleTestClass",
            "Test Name": "test_flaky_0",
            "Result": "FAIL",
            "Stacktrace": "Attempt 1 failed",
        },
        {
            "Type": "Record",
            "Test Class": "SampleTestClass",
            "Test Name": "test_flaky_0",
            "Result": "PASS",
            "Details": "Attempt 2 passed",
        },
        {
            "Type": "Record",
            "Test Class": "SampleTestClass",
            "Test Name": "setup_class",
            "Result": "PASS",
        },
    ]

    temp_dir = self.create_tempdir()
    summary_file = temp_dir.create_file(
        "test_summary.yaml", content=yaml.safe_dump_all(records)
    ).full_path

    result = mobly_parser.parse_mobly_summary(summary_file)

    self.assertIsInstance(result, mobly_parser.ParseResult)
    self.assertEqual(
        result.summary,
        mobly_parser.TestSummary(
            requested=4,
            passed=2,
            failed=1,
            skipped=1,
            executed=3,
            total_executions=5,
            exec_passed=2,
            exec_failed=2,
            exec_skipped=1,
        ),
    )

    classes = result.test_classes
    self.assertIn("SampleTestClass", classes)
    cls_info = classes["SampleTestClass"]
    self.assertLen(cls_info.test_cases, 4)
    self.assertLen(cls_info.cleanups, 1)

    flaky_case = next(
        tc for tc in cls_info.test_cases if tc.name == "test_flaky_0"
    )
    self.assertTrue(flaky_case.is_flaky)
    self.assertEqual(flaky_case.status, "PASS")

  def test_parse_mobly_summary_not_found(self) -> None:
    result = mobly_parser.parse_mobly_summary("/non/existent/summary.yaml")
    self.assertIsInstance(result, dict)
    self.assertIn("error", result)

  def test_collect_artifacts(self) -> None:
    temp_dir = self.create_tempdir()
    temp_dir.create_file("test.log", content="Log line 1\nLog line 2\n")
    temp_dir.create_file("screenshot.png", content=b"\x89PNG\r\n\x1a\n")
    temp_dir.create_file(".hidden", content="hidden")
    temp_dir.create_file("uploaded.zip", content=b"PK\x03\x04")

    artifacts = mobly_parser.collect_artifacts(temp_dir.full_path)
    filenames = [a.filename for a in artifacts]

    self.assertIn("test.log", filenames)
    self.assertIn("screenshot.png", filenames)
    self.assertNotIn(".hidden", filenames)
    self.assertNotIn("uploaded.zip", filenames)

    log_art = next(a for a in artifacts if a.filename == "test.log")
    self.assertTrue(log_art.is_text)

    img_art = next(a for a in artifacts if a.filename == "screenshot.png")
    self.assertFalse(img_art.is_text)

  def test_find_and_parse_results(self) -> None:
    records = [
        {
            "Type": "Record",
            "Test Class": "SubClass",
            "Test Name": "test_sub",
            "Result": "PASS",
        }
    ]
    temp_dir = self.create_tempdir()
    temp_dir.create_file(
        "run_123/test_summary.yaml", content=yaml.safe_dump_all(records)
    )

    res = mobly_parser.find_and_parse_results(temp_dir.full_path)
    self.assertIsInstance(res, mobly_parser.ParseResult)
    self.assertTrue(res.artifacts)
    self.assertEqual(res.results_dir, os.path.abspath(temp_dir.full_path))

  def test_find_and_parse_results_missing(self) -> None:
    temp_dir = self.create_tempdir()
    res = mobly_parser.find_and_parse_results(temp_dir.full_path)
    self.assertIsInstance(res, dict)
    self.assertIn("error", res)

  def test_find_and_parse_results_zip_file_success(self) -> None:
    records = [
        {
            "Type": "Record",
            "Test Class": "ZipClass",
            "Test Name": "test_in_zip",
            "Result": "PASS",
        }
    ]
    temp_dir = self.create_tempdir()
    zip_path = os.path.join(temp_dir.full_path, "results.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
      zf.writestr("run_1/test_summary.yaml", yaml.safe_dump_all(records))
      zf.writestr("run_1/test.log", "Zip test log content")

    res = mobly_parser.find_and_parse_results(zip_path)
    self.assertIsInstance(res, mobly_parser.ParseResult)
    self.assertIn("ZipClass", res.test_classes)
    self.assertTrue(res.artifacts)

  def test_find_and_parse_results_zip_file_invalid(self) -> None:
    temp_dir = self.create_tempdir()
    bad_zip_path = temp_dir.create_file(
        "bad.zip", content="not a zip file"
    ).full_path

    res = mobly_parser.find_and_parse_results(bad_zip_path)
    self.assertIsInstance(res, dict)
    self.assertIn("error", res)
    self.assertIn("not a valid ZIP", res["error"])

  def test_find_and_parse_results_zip_file_unsafe_path(self) -> None:
    temp_dir = self.create_tempdir()
    zip_path = os.path.join(temp_dir.full_path, "unsafe.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
      zf.writestr("../../evil.txt", "malicious content")

    res = mobly_parser.find_and_parse_results(zip_path)
    self.assertIsInstance(res, dict)
    self.assertIn("error", res)
    self.assertIn("unsafe path", res["error"])


if __name__ == "__main__":
  absltest.main()
