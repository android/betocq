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

"""Unit tests for betocq_to_apa."""

import json
import os
from xml.etree import ElementTree as ET
import zipfile

from absl.testing import absltest
import yaml

from betocq.tools.apa_package import betocq_to_apa


def _write_run_dir(
    root_dir: str,
    run_name: str,
    *,
    apa_module_name: str = "betocq_directed_suite",
    apa_suite_plan: str = "betocq_daily",
    all_test_must_pass: bool = True,
    build_fingerprint: str = "google/husky/husky:15/AP3A.241005.015/123456:userdebug/dev-keys",
    serial: str = "HUSKY001",
    records_list: list[dict[str, object]] | None = None,
    metrics_payload: dict[str, object] | None = None,
) -> str:
  """Creates a synthetic Mobly/BeToCQ run directory with YAML and metrics JSON."""
  run_dir = os.path.join(root_dir, run_name)
  os.makedirs(os.path.join(run_dir, "report-log-files"), exist_ok=True)

  docs: list[dict[str, object]] = [
      {
          "Type": "UserData",
          "properties": {
              "apa_module_name": apa_module_name,
              "apa_suite_plan": apa_suite_plan,
              "all_test_must_pass": all_test_must_pass,
              "apa_target_device": serial,
              "test_script_version": "2.4.0",
              "suite_version": "999",
          },
      },
      {
          "Type": "ControllerInfo",
          "Controller Name": "AndroidDevice",
          "Controller Info": [{
              "serial": serial,
              "model": "Pixel 8 Pro",
              "build_info": {
                  "build_fingerprint": build_fingerprint,
              },
          }],
      },
  ]
  if records_list:
    docs.extend(records_list)

  yaml_path = os.path.join(run_dir, "test_summary.yaml")
  with open(yaml_path, "w", encoding="utf-8") as f:
    yaml.safe_dump_all(docs, f)

  if metrics_payload is not None:
    metrics_path = os.path.join(
        run_dir, "report-log-files", f"{apa_module_name}.reportlog.json"
    )
    with open(metrics_path, "w", encoding="utf-8") as f:
      json.dump(metrics_payload, f)

  return run_dir


class BetocqToApaTest(absltest.TestCase):

  def test_same_suite_retry_merging_passing_supersedes_failure_and_warning(
      self,
  ):
    work_dir = self.create_tempdir().full_path
    out_dir = os.path.join(work_dir, "out")

    # Run 1: test_alpha fails, test_beta warns (non-fatal fail when
    # all_test_must_pass=False or explicit signal), test_gamma passes.
    run1_dir = _write_run_dir(
        work_dir,
        "run1",
        all_test_must_pass=True,
        records_list=[
            {
                "Type": "Record",
                "Test Class": "DirectedTests",
                "Test Name": "test_alpha_0",
                "Result": "FAIL",
                "Begin Time": 1700000001000,
                "End Time": 1700000002000,
                "Details": "Transient RF interference",
            },
            {
                "Type": "Record",
                "Test Class": "DirectedTests",
                "Test Name": "test_gamma_0",
                "Result": "PASS",
                "Begin Time": 1700000002000,
                "End Time": 1700000003000,
            },
        ],
        metrics_payload={
            "suite_name": "betocq_directed_suite",
            "test_classes": [{
                "key": "DirectedTests",
                "value": {
                    "scenarios": [
                        {
                            "key": "test_alpha",
                            "value": {"throughput_mbps": 12.5},
                        },
                        {
                            "key": "test_gamma",
                            "value": {"throughput_mbps": 88.0},
                        },
                    ],
                },
            }],
        },
    )

    # Run 2 (retry): test_alpha passes with high throughput.
    run2_dir = _write_run_dir(
        work_dir,
        "run2",
        all_test_must_pass=True,
        records_list=[
            {
                "Type": "Record",
                "Test Class": "DirectedTests",
                "Test Name": "test_alpha_0",
                "Result": "PASS",
                "Begin Time": 1700000010000,
                "End Time": 1700000012000,
            },
        ],
        metrics_payload={
            "suite_name": "betocq_directed_suite",
            "test_classes": [{
                "key": "DirectedTests",
                "value": {
                    "scenarios": [
                        {
                            "key": "test_alpha",
                            "value": {"throughput_mbps": 95.2},
                        },
                    ],
                },
            }],
        },
    )

    betocq_to_apa.package_for_apa(
        input_dir=[run1_dir, run2_dir],
        output_dir=out_dir,
    )

    zips = [
        os.path.join(out_dir, f)
        for f in os.listdir(out_dir)
        if f.endswith(".zip")
    ]
    self.assertLen(zips, 1)
    zip_path = zips[0]

    with zipfile.ZipFile(zip_path, "r") as zf:
      names = set(zf.namelist())
      self.assertIn("test_result.xml", names)
      self.assertIn(
          "report-log-files/betocq_directed_suite.reportlog.json", names
      )
      non_tf_summaries = [
          n
          for n in names
          if n.startswith("non-tradefed_results/betocq_directed_suite/")
          and n.endswith("/test_summary.yaml")
      ]
      self.assertLen(non_tf_summaries, 2)

      xml_root = ET.fromstring(zf.read("test_result.xml"))
      self.assertEqual(xml_root.attrib["suite_version"], "2.4.0")
      tests_by_name = {
          t.attrib["name"]: t.attrib["result"]
          for t in xml_root.findall(".//Test")
      }
      self.assertEqual(
          tests_by_name,
          {"test_alpha": "pass", "test_gamma": "pass"},
      )

      merged_metrics = json.loads(
          zf.read("report-log-files/betocq_directed_suite.reportlog.json")
      )
      scenarios = betocq_to_apa._get_scenarios_for_class(
          merged_metrics, "DirectedTests"
      )
      self.assertEqual(scenarios["test_alpha"], {"throughput_mbps": 95.2})
      self.assertEqual(scenarios["test_gamma"], {"throughput_mbps": 88.0})

  def test_split_run_merging_unites_disjoint_classes_and_scenarios(self):
    work_dir = self.create_tempdir().full_path
    out_dir = os.path.join(work_dir, "out")

    run1_dir = _write_run_dir(
        work_dir,
        "split_part1",
        records_list=[
            {
                "Type": "Record",
                "Test Class": "ClassOne",
                "Test Name": "test_c1_a_0",
                "Result": "PASS",
                "Begin Time": 1700000001000,
                "End Time": 1700000002000,
            },
            {
                "Type": "Record",
                "Test Class": "SharedClass",
                "Test Name": "test_shared_first_0",
                "Result": "PASS",
                "Begin Time": 1700000002000,
                "End Time": 1700000003000,
            },
        ],
        metrics_payload={
            "suite_name": "betocq_directed_suite",
            "test_classes": [
                {
                    "key": "ClassOne",
                    "value": {
                        "scenarios": [{"key": "test_c1_a", "value": {"ok": 1}}]
                    },
                },
                {
                    "key": "SharedClass",
                    "value": {
                        "scenarios": [
                            {"key": "test_shared_first", "value": {"ok": 2}}
                        ]
                    },
                },
            ],
        },
    )

    run2_dir = _write_run_dir(
        work_dir,
        "split_part2",
        records_list=[
            {
                "Type": "Record",
                "Test Class": "SharedClass",
                "Test Name": "test_shared_second_0",
                "Result": "PASS",
                "Begin Time": 1700000005000,
                "End Time": 1700000006000,
            },
            {
                "Type": "Record",
                "Test Class": "ClassTwo",
                "Test Name": "test_c2_b_0",
                "Result": "PASS",
                "Begin Time": 1700000006000,
                "End Time": 1700000008000,
            },
        ],
        metrics_payload={
            "suite_name": "betocq_directed_suite",
            "test_classes": [
                {
                    "key": "SharedClass",
                    "value": {
                        "scenarios": [
                            {"key": "test_shared_second", "value": {"ok": 3}}
                        ]
                    },
                },
                {
                    "key": "ClassTwo",
                    "value": {
                        "scenarios": [{"key": "test_c2_b", "value": {"ok": 4}}]
                    },
                },
            ],
        },
    )

    betocq_to_apa.package_for_apa(
        input_dir=f"{run1_dir},{run2_dir}",
        output_dir=out_dir,
    )

    zips = [
        os.path.join(out_dir, f)
        for f in os.listdir(out_dir)
        if f.endswith(".zip")
    ]
    self.assertLen(zips, 1)
    zip_path = zips[0]
    with zipfile.ZipFile(zip_path, "r") as zf:
      xml_root = ET.fromstring(zf.read("test_result.xml"))
      classes_in_xml = {
          tc.attrib["name"]: {t.attrib["name"] for t in tc.findall("Test")}
          for tc in xml_root.findall(".//TestCase")
      }
      self.assertEqual(
          classes_in_xml,
          {
              "ClassOne": {"test_c1_a"},
              "SharedClass": {"test_shared_first", "test_shared_second"},
              "ClassTwo": {"test_c2_b"},
          },
      )

      merged_metrics = json.loads(
          zf.read("report-log-files/betocq_directed_suite.reportlog.json")
      )
      self.assertEqual(
          betocq_to_apa._get_scenarios_for_class(merged_metrics, "SharedClass"),
          {
              "test_shared_first": {"ok": 2},
              "test_shared_second": {"ok": 3},
          },
      )

  def test_merge_same_suite_metrics_consolidates_winners_and_classes(self):
    run0_metrics = {
        "suite_name": "suite_a",
        "result_store_link": "PLACEHOLDER",
        "test_classes": [{
            "key": "ClassA",
            "value": {
                "test_info": {"start_time": "100", "end_time": "200"},
                "class_metrics": [{"key": "m1", "value": 10}],
                "scenarios": [
                    {"key": "scen_keep_run0", "value": {"score": 99}},
                    {"key": "scen_override_run1", "value": {"score": 10}},
                ],
            },
        }],
    }
    run1_metrics = {
        "suite_name": "suite_a",
        "result_store_link": "https://btx.cloud.google.com/invocations/inv-2",
        "test_classes": [
            {
                "key": "ClassA",
                "value": {
                    "test_info": {"start_time": "300", "end_time": "400"},
                    "class_metrics": [{"key": "m2", "value": 20}],
                    "scenarios": [
                        {"key": "scen_keep_run0", "value": {"score": 1}},
                        {"key": "scen_override_run1", "value": {"score": 95}},
                    ],
                },
            },
            {
                "key": "ClassB",
                "value": {
                    "scenarios": [{"key": "scen_b", "value": {"score": 80}}],
                },
            },
        ],
    }

    merged = betocq_to_apa._merge_same_suite_metrics(
        [run0_metrics, run1_metrics],
        winning_run_by_scenario={
            ("ClassA", "scen_keep_run0"): 0,
            ("ClassA", "scen_override_run1"): 1,
            ("ClassB", "scen_b"): 1,
        },
    )

    self.assertEqual(
        merged["result_store_link"],
        "https://btx.cloud.google.com/invocations/inv-2",
    )
    class_a_scenarios = betocq_to_apa._get_scenarios_for_class(merged, "ClassA")
    self.assertEqual(class_a_scenarios["scen_keep_run0"], {"score": 99})
    self.assertEqual(class_a_scenarios["scen_override_run1"], {"score": 95})
    class_b_scenarios = betocq_to_apa._get_scenarios_for_class(merged, "ClassB")
    self.assertEqual(class_b_scenarios["scen_b"], {"score": 80})

  def test_validation_failures_mismatched_fingerprint_and_suite_plan(self):
    work_dir = self.create_tempdir().full_path
    out_dir = os.path.join(work_dir, "out")

    # 1. Empty apa_suite_plan must raise ValueError.
    empty_plan_dir = _write_run_dir(
        work_dir,
        "empty_plan",
        apa_suite_plan="",
    )
    with self.assertRaisesRegex(ValueError, "apa_suite_plan cannot be empty"):
      betocq_to_apa.package_for_apa(
          input_dir=empty_plan_dir, output_dir=out_dir
      )

    # 2. Mismatched apa_suite_plan across runs must raise ValueError.
    plan_a_dir = _write_run_dir(
        work_dir,
        "plan_a",
        apa_suite_plan="betocq_daily",
    )
    plan_b_dir = _write_run_dir(
        work_dir,
        "plan_b",
        apa_suite_plan="betocq_release",
    )
    with self.assertRaisesRegex(ValueError, "same apa_suite_plan"):
      betocq_to_apa.package_for_apa(
          input_dir=[plan_a_dir, plan_b_dir],
          output_dir=out_dir,
      )

    # 3. Mismatched build_fingerprint across runs must raise ValueError.
    fp_other_dir = _write_run_dir(
        work_dir,
        "fp_other",
        apa_suite_plan="betocq_daily",
        build_fingerprint=(
            "google/shiba/shiba:15/AP3A.241005.015/999999:userdebug/dev-keys"
        ),
    )
    with self.assertRaisesRegex(ValueError, "same build_fingerprint"):
      betocq_to_apa.package_for_apa(
          input_dir=[plan_a_dir, fp_other_dir],
          output_dir=out_dir,
      )


if __name__ == "__main__":
  absltest.main()
