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

"""Unit tests for setup_wizard module."""

from google3.testing.pybase import googletest
from betocq.tools.results_viewer import setup_wizard


class SetupWizardTest(googletest.TestCase):

  def test_get_check_env_script(self):
    script_bytes = setup_wizard.get_check_env_script()
    self.assertIsInstance(script_bytes, bytes)
    self.assertNotEmpty(script_bytes)
    content = script_bytes.decode("utf-8")
    self.assertIn("#!/bin/bash", content)
    self.assertIn("1. HOST OS & HARDWARE", content)
    self.assertIn("2. XCODE & COMMAND LINE TOOLS", content)

  def test_run_environment_checks(self):
    results = setup_wizard.run_environment_checks()
    self.assertIsInstance(results, dict)
    self.assertTrue(results.get("success"))
    self.assertIn("timestamp", results)
    self.assertIn(results.get("overall_status"), ["PASS", "WARN", "FAIL"])
    self.assertIn("sections", results)
    sections = results["sections"]
    self.assertGreaterEqual(len(sections), 7)
    section_ids = [s["id"] for s in sections]
    self.assertIn("host_os", section_ids)
    self.assertIn("xcode_tools", section_ids)
    self.assertIn("python_runtime", section_ids)
    self.assertIn("raw_output", results)
    self.assertIn("devices_summary", results)
    dev_summary = results["devices_summary"]
    self.assertIn("ios", dev_summary)
    self.assertIn("android", dev_summary)
    self.assertIn("model", dev_summary["ios"])
    self.assertIn("udid", dev_summary["ios"])
    self.assertIn("model", dev_summary["android"])
    self.assertIn("serial", dev_summary["android"])

  def test_extract_ios_devices(self):
    devicectl_output = """
.     UDID                                  Name             Model         OS
1     00008110-001234567890ABCD             Partner iPhone   iPhone15,2    iOS 18.0 (22A3354)
2     12345678-ABCD-1234-EF01-234567890ABC  Lab iPad         iPad14,1      iPadOS 17.5
"""
    devices = setup_wizard.extract_ios_devices(devicectl_output)
    self.assertLen(devices, 2)
    self.assertEqual(devices[0]["udid"], "00008110-001234567890ABCD")
    self.assertEqual(devices[0]["name"], "Partner iPhone")
    self.assertEqual(devices[0]["model"], "iPhone15,2")
    self.assertIn("iOS 18.0", devices[0]["version"])

    idevice_output = "00008110-001234567890ABCD\n00008120-0099887766554433\n"
    devices_idevice = setup_wizard.extract_ios_devices(idevice_output)
    self.assertLen(devices_idevice, 2)
    self.assertEqual(devices_idevice[0]["udid"], "00008110-001234567890ABCD")
    self.assertEqual(devices_idevice[1]["udid"], "00008120-0099887766554433")

    idevice_dual_output = (
        "idevice_id -l (USB):\n"
        "00008110-001234567890ABCD\n"
        "idevice_id -n (Network):\n"
        "None found\n"
    )
    devices_dual = setup_wizard.extract_ios_devices(idevice_dual_output)
    self.assertLen(devices_dual, 1)
    self.assertEqual(devices_dual[0]["udid"], "00008110-001234567890ABCD")

  def test_extract_android_devices(self):
    adb_output = """
List of devices attached
39281FDJG001           device usb:337641472X product:husky model:Pixel_8_Pro device:husky transport_id:1
4A121FDEE00002         device usb:337641473X product:caiman model:Pixel_9_Pro device:caiman transport_id:2
192.168.1.50:5555      offline transport_id:3
"""
    devices = setup_wizard.extract_android_devices(adb_output)
    self.assertLen(devices, 3)
    self.assertEqual(devices[0]["serial"], "39281FDJG001")
    self.assertEqual(devices[0]["model"], "Pixel 8 Pro")
    self.assertEqual(devices[0]["state"], "device")
    self.assertEqual(devices[1]["serial"], "4A121FDEE00002")
    self.assertEqual(devices[1]["model"], "Pixel 9 Pro")
    self.assertEqual(devices[2]["serial"], "192.168.1.50:5555")
    self.assertEqual(devices[2]["state"], "offline")


if __name__ == "__main__":
  googletest.main()
