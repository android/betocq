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

"""Setup wizard and station environment diagnostics for BeToCQ Result Viewer.

Provides station readiness diagnostics, hardware checks, and setup verification
by running environment checks (via check_env.sh or modular diagnostic commands).
"""

from collections.abc import Sequence
import dataclasses
import datetime
import os
import pkgutil
import re
import subprocess
import sys
from typing import Any
import zipfile

PACKAGE_NAME = "google3.wireless.android.platform.testing.bettertogether.betocq.tools.results_viewer"
CHECK_ENV_RESOURCE_PATH = "check_env.sh"

_IOS_DEVICECTL_PATTERN = re.compile(
    r"([0-9A-Fa-f\-]{25,40})\s+(.+?)\s+([A-Za-z0-9_,]+)"
    r"\s+((?:iOS|iPadOS)\s+[0-9\.]+.*)"
)
_IOS_UDID_PATTERN = re.compile(r"\b([0-9A-Fa-f\-]{25,40})\b")
_ANDROID_DEVICE_WITH_MODEL_PATTERN = re.compile(
    r"^([^\s]+)\s+(device|offline|unauthorized)\s+.*model:([A-Za-z0-9_]+)"
)
_ANDROID_DEVICE_SIMPLE_PATTERN = re.compile(
    r"^([^\s]+)\s+(device|offline|unauthorized)"
)
_PRODUCT_VERSION_PATTERN = re.compile(r"ProductVersion:\s*([^\n]+)")
_XCODE_VERSION_PATTERN = re.compile(r"(Xcode\s+[0-9\.]+)")
_CODESIGNING_IDENTITIES_PATTERN = re.compile(
    r"([0-9]+)\s+valid identities found"
)
_PYTHON_VERSION_PATTERN = re.compile(r"(Python\s+3\.[0-9\.]+)")

_CHECK_ENV_SCRIPT_FALLBACK = """#!/bin/bash
echo "========================================================"
echo "=== 1. HOST OS & HARDWARE ==="
echo "========================================================"
sw_vers 2>&1 || echo "sw_vers: not available (non-macOS host)"
uname -a

echo ""
echo "========================================================"
echo "=== 2. XCODE & COMMAND LINE TOOLS ==="
echo "========================================================"
echo "xcode-select path: $(xcode-select -p 2>&1 || echo 'not found')"
echo "xcodebuild version:"
xcodebuild -version 2>&1 || echo "xcodebuild: not found or failed"
echo "CLTools package:"
pkgutil --pkg-info=com.apple.pkg.CLTools_Executables 2>/dev/null | grep -E "version|install-time" || echo "CLTools package not registered"
echo "Installed Xcode applications:"
ls -ld /Applications/Xcode*.app 2>/dev/null || echo "None found in /Applications"

echo ""
echo "========================================================"
echo "=== 3. CODESIGNING IDENTITIES ==="
echo "========================================================"
security find-identity -v -p codesigning 2>&1 || echo "security: not available or failed"

echo ""
echo "========================================================"
echo "=== 4. COREDEVICE & DEVICES ==="
echo "========================================================"
echo "devicectl binary: $(xcrun --find devicectl 2>&1 || echo 'not found')"
echo "devicectl list devices:"
xcrun devicectl list devices 2>&1 | head -n 20 || echo "devicectl failed"
echo "idevice_id list:"
which idevice_id 2>/dev/null && idevice_id -l 2>&1 || echo "idevice_id: not found"

echo ""
echo "========================================================"
echo "=== 5. PYTHON RUNTIME ==="
echo "========================================================"
echo "which python3: $(which python3 2>&1)"
echo "python3 version: $(python3 --version 2>&1)"
echo "sys.executable: $(python3 -c 'import sys; print(sys.executable)' 2>&1)"
echo "Environment variables:"
env | grep -E "^(PYTHON|VIRTUAL_ENV|DEVELOPER_DIR|SDKROOT|PATH)" | head -n 5

echo ""
echo "========================================================"
echo "=== 6. UTILITIES & SERVICES ==="
echo "========================================================"
echo "idevice_id -l (USB):"
idevice_id -l 2>&1 || echo "None found"
echo "idevice_id -n (Network):"
idevice_id -n 2>&1 || echo "None found"
which adb 2>/dev/null && adb version 2>&1 | head -n 2 || echo "adb: not found"
echo "Connected ADB devices:"
which adb 2>/dev/null && adb devices -l 2>&1 || echo "adb devices: not found"
echo "Running daemons:"
ps aux | grep -E "usbmuxd|remotepairingd|CoreDeviceService" | grep -v grep || echo "None running"

echo ""
echo "========================================================"
echo "=== 7. FIREWALL & TUNNELS ==="
echo "========================================================"
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>&1 || echo "socketfilterfw: not available"
echo "Active utun tunnel interfaces:"
ifconfig 2>/dev/null | grep -E "^utun[0-9]+" || ip link show 2>/dev/null | grep -E "utun" || echo "None found"
echo "========================================================"
"""


def get_check_env_script() -> bytes:
  """Retrieves the check_env.sh script from disk, par zip, or fallback.

  Returns:
    The raw bytes of check_env.sh.
  """
  base_dir = os.path.dirname(os.path.abspath(__file__))
  candidate_paths = [
      os.path.join(base_dir, "check_env.sh"),
      os.path.join(base_dir, "scripts", "check_env.sh"),
  ]
  for path in candidate_paths:
    if os.path.isfile(path):
      with open(path, "rb") as f:
        return f.read()

  candidate_zips = [
      os.environ.get("_PARFILE", ""),
      getattr(sys, "argv", [""])[0],
      __file__,
  ]
  for zip_candidate in candidate_zips:
    if zip_candidate and os.path.isfile(zip_candidate):
      try:
        with zipfile.ZipFile(zip_candidate, "r") as z:
          for name in z.namelist():
            if name.endswith(CHECK_ENV_RESOURCE_PATH):
              return z.read(name)
      except (OSError, zipfile.BadZipFile, KeyError):
        pass

  try:
    data = pkgutil.get_data(
        PACKAGE_NAME,
        CHECK_ENV_RESOURCE_PATH,
    )
  except (OSError, ImportError, ValueError):
    data = None
  if data:
    return data

  return _CHECK_ENV_SCRIPT_FALLBACK.encode("utf-8")


def _run_single_command_section(script: str, timeout_seconds: int = 15) -> str:
  """Runs a shell snippet and returns combined stdout and stderr."""
  try:
    result = subprocess.run(
        script,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    combined = (result.stdout + result.stderr).strip()
    return combined if combined else "(no output)"
  except subprocess.TimeoutExpired:
    return f"Command timed out after {timeout_seconds}s"
  except Exception as e:  # pylint: disable=broad-exception-caught
    return f"Execution error: {e}"


@dataclasses.dataclass(frozen=True)
class _EnvSectionDef:
  """Definition for a single environment diagnostic section."""

  id: str
  title: str
  icon: str
  commands: Sequence[str]
  script: str


def extract_ios_devices(output: str) -> list[dict[str, str]]:
  """Extracts iOS device model and UDID from devicectl and idevice_id output."""
  devices: list[dict[str, str]] = []
  for line in output.splitlines():
    line = line.strip()
    if (
        not line
        or line.startswith("Identifier")
        or line.startswith("---")
        or line.startswith("devicectl")
    ):
      continue
    # devicectl table: <UDID> <Name> <Model> <Version>
    match = _IOS_DEVICECTL_PATTERN.search(line)
    if match:
      devices.append({
          "udid": match.group(1).strip(),
          "name": match.group(2).strip(),
          "model": match.group(3).strip(),
          "version": match.group(4).strip(),
      })
      continue
    # Check for raw UDID (e.g. from idevice_id -l or idevice_id -n)
    udid_match = _IOS_UDID_PATTERN.search(line)
    if udid_match and not any(
        d["udid"] == udid_match.group(1) for d in devices
    ):
      devices.append({
          "udid": udid_match.group(1).strip(),
          "name": "iPhone",
          "model": "iOS Device",
          "version": "iOS",
      })
  return devices


def extract_android_devices(output: str) -> list[dict[str, str]]:
  """Extracts Android device model and serial from adb devices -l output."""
  devices: list[dict[str, str]] = []
  for line in output.splitlines():
    line = line.strip()
    if not line or line.startswith("List of") or line.startswith("*"):
      continue
    match = _ANDROID_DEVICE_WITH_MODEL_PATTERN.search(line)
    if match:
      devices.append({
          "serial": match.group(1),
          "state": match.group(2),
          "model": match.group(3).replace("_", " "),
      })
      continue
    simple_match = _ANDROID_DEVICE_SIMPLE_PATTERN.search(line)
    if (
        simple_match
        and not simple_match.group(1).startswith("emulator")
        and not any(d["serial"] == simple_match.group(1) for d in devices)
    ):
      devices.append({
          "serial": simple_match.group(1),
          "state": simple_match.group(2),
          "model": "Android Device",
      })
  return devices


def run_environment_checks() -> dict[str, Any]:
  """Runs station environment checks and returns structured diagnostics."""
  section_defs: list[_EnvSectionDef] = [
      _EnvSectionDef(
          id="host_os",
          title="1. Host OS & Hardware",
          icon="💻",
          commands=["sw_vers", "uname -a"],
          script=(
              'sw_vers 2>&1 || echo "sw_vers: not available (non-macOS host)"\n'
              "uname -a"
          ),
      ),
      _EnvSectionDef(
          id="xcode_tools",
          title="2. Xcode & Command Line Tools",
          icon="🛠️",
          commands=[
              "xcode-select -p",
              "xcodebuild -version",
              "pkgutil --pkg-info=com.apple.pkg.CLTools_Executables",
              "ls -ld /Applications/Xcode*.app",
          ],
          script=(
              "echo \"xcode-select path: $(xcode-select -p 2>&1 || echo 'not"
              " found')\"\n"
              'echo "xcodebuild version:"\n'
              'xcodebuild -version 2>&1 || echo "xcodebuild: not found or'
              ' failed"\n'
              'echo "CLTools package:"\n'
              "pkgutil --pkg-info=com.apple.pkg.CLTools_Executables 2>/dev/null"
              ' | grep -E "version|install-time" || echo "CLTools package not'
              ' registered"\n'
              'echo "Installed Xcode applications:"\n'
              'ls -ld /Applications/Xcode*.app 2>/dev/null || echo "None found'
              ' in /Applications"'
          ),
      ),
      _EnvSectionDef(
          id="codesigning",
          title="3. Codesigning Identities",
          icon="🔐",
          commands=["security find-identity -v -p codesigning"],
          script=(
              "security find-identity -v -p codesigning 2>&1 || echo 'security:"
              " not available or failed'"
          ),
      ),
      _EnvSectionDef(
          id="devices",
          title="4. CoreDevice & Devices",
          icon="📱",
          commands=[
              "xcrun --find devicectl",
              "xcrun devicectl list devices",
              "idevice_id -l",
          ],
          script=(
              'echo "devicectl binary: $(xcrun --find devicectl 2>&1 || echo'
              " 'not found')\"\n"
              'echo "devicectl list devices:"\n'
              "xcrun devicectl list devices 2>&1 | head -n 20 || echo"
              ' "devicectl failed"\n'
              'echo "idevice_id list:"\n'
              "which idevice_id 2>/dev/null && idevice_id -l 2>&1 || echo"
              ' "idevice_id: not found"'
          ),
      ),
      _EnvSectionDef(
          id="python_runtime",
          title="5. Python Runtime",
          icon="🐍",
          commands=[
              "which python3",
              "python3 --version",
              "sys.executable",
              (
                  "env | grep -E"
                  " '^(PYTHON|VIRTUAL_ENV|DEVELOPER_DIR|SDKROOT|PATH)'"
              ),
          ],
          script=(
              'echo "which python3: $(which python3 2>&1)"\n'
              'echo "python3 version: $(python3 --version 2>&1)"\n'
              "echo \"sys.executable: $(python3 -c 'import sys;"
              " print(sys.executable)' 2>&1)\"\n"
              'echo "Environment variables:"\n'
              'env | grep -E "^(PYTHON|VIRTUAL_ENV|DEVELOPER_DIR|SDKROOT|PATH)"'
              " | head -n 5"
          ),
      ),
      _EnvSectionDef(
          id="utilities_services",
          title="6. Utilities & Services",
          icon="⚡",
          commands=[
              "idevice_id -l",
              "idevice_id -n",
              "adb version",
              "adb devices -l",
              "ps aux | grep -E 'usbmuxd|remotepairingd|CoreDeviceService'",
          ],
          script=(
              'echo "idevice_id -l (USB):"\n'
              'idevice_id -l 2>&1 || echo "None found"\n'
              'echo "idevice_id -n (Network):"\n'
              'idevice_id -n 2>&1 || echo "None found"\n'
              "which adb 2>/dev/null && adb version 2>&1 | head -n 2 || echo"
              ' "adb: not found"\n'
              'echo "Connected ADB devices:"\n'
              'which adb 2>/dev/null && adb devices -l 2>&1 || echo "adb'
              ' devices: not found"\n'
              'echo "Running daemons:"\n'
              'ps aux | grep -E "usbmuxd|remotepairingd|CoreDeviceService" |'
              ' grep -v grep || echo "None running"'
          ),
      ),
      _EnvSectionDef(
          id="firewall_tunnels",
          title="7. Firewall & Tunnels",
          icon="🛡️",
          commands=[
              "socketfilterfw --getglobalstate",
              "ifconfig | grep -E '^utun[0-9]+'",
          ],
          script=(
              "/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate"
              ' 2>&1 || echo "socketfilterfw: not available"\n'
              'echo "Active utun tunnel interfaces:"\n'
              'ifconfig 2>/dev/null | grep -E "^utun[0-9]+" || ip link show'
              ' 2>/dev/null | grep -E "utun" || echo "None found"'
          ),
      ),
  ]

  sections: list[dict[str, Any]] = []
  raw_parts: list[str] = []
  ios_devices: list[dict[str, str]] = []
  android_devices: list[dict[str, str]] = []

  for sec_def in section_defs:
    output = _run_single_command_section(sec_def.script)
    sec_id = sec_def.id
    status = "INFO"
    summary = ""

    if sec_id == "host_os":
      if "ProductVersion:" in output:
        match = _PRODUCT_VERSION_PATTERN.search(output)
        ver = match.group(1).strip() if match else ""
        summary = f"macOS {ver}".strip()
      else:
        first_line = output.splitlines()[0] if output else "Linux"
        summary = first_line[:60]
      status = "PASS"

    elif sec_id == "xcode_tools":
      if "Xcode " in output:
        match = _XCODE_VERSION_PATTERN.search(output)
        ver = match.group(1) if match else "Xcode installed"
        summary = ver
        status = "PASS"
      elif "version:" in output:
        summary = "CLTools package registered"
        status = "PASS"
      elif "not available" in output or "not found" in output:
        summary = "Xcode / CLI Tools not found (N/A on Linux)"
        status = "INFO" if sys.platform.startswith("linux") else "WARN"
      else:
        summary = "Xcode CLI check completed"
        status = "INFO"

    elif sec_id == "codesigning":
      if "valid identities found" in output:
        match = _CODESIGNING_IDENTITIES_PATTERN.search(output)
        count = int(match.group(1)) if match else 0
        if count > 0:
          summary = f"{count} valid signing identity/identities found"
          status = "PASS"
        else:
          summary = "0 valid codesigning identities found"
          status = "WARN"
      elif "not available" in output or "failed" in output:
        summary = "Codesigning security tool not available"
        status = "INFO"
      else:
        summary = "Codesigning check completed"
        status = "INFO"

    elif sec_id == "devices":
      found_ios = extract_ios_devices(output)
      for d in found_ios:
        if not any(existing["udid"] == d["udid"] for existing in ios_devices):
          ios_devices.append(d)

      if ios_devices:
        first_ios = ios_devices[0]
        model_str = first_ios.get("model", "iOS Device")
        udid_str = first_ios.get("udid", "")
        summary = (
            f"{len(ios_devices)} iOS device(s) connected: {model_str}"
            f" ({udid_str[:8]}...)"
        )
        status = "PASS"
      elif "devicectl binary:" in output and "/devicectl" in output:
        summary = "Apple devicectl available (0 connected)"
        status = "INFO"
      elif "not available" in output or "not found" in output:
        summary = "devicectl / iOS tools not found (N/A on Linux)"
        status = "INFO" if sys.platform.startswith("linux") else "WARN"
      else:
        summary = "CoreDevice check completed"
        status = "INFO"

    elif sec_id == "python_runtime":
      if "Python 3." in output:
        match = _PYTHON_VERSION_PATTERN.search(output)
        ver = match.group(1) if match else "Python 3"
        summary = f"{ver} ready"
        status = "PASS"
      else:
        summary = "Python runtime checked"
        status = "WARN"

    elif sec_id == "utilities_services":
      found_android = extract_android_devices(output)
      for d in found_android:
        if not any(
            existing["serial"] == d["serial"] for existing in android_devices
        ):
          android_devices.append(d)

      found_ios_more = extract_ios_devices(output)
      for d in found_ios_more:
        if not any(existing["udid"] == d["udid"] for existing in ios_devices):
          ios_devices.append(d)

      items = []
      if android_devices:
        first_and = android_devices[0]
        items.append(
            f"{len(android_devices)} Android device(s):"
            f" {first_and.get('model', 'Android')}"
            f" ({first_and.get('serial', '')})"
        )
      elif "Android Debug Bridge" in output or "adb version" in output:
        items.append("ADB detected (0 connected)")
      if "usbmuxd" in output:
        items.append("usbmuxd running")
      if "idevice_id" in output and "not found" not in output:
        items.append("idevice_id active")
      if not items:
        items.append("Services checked")
      summary = ", ".join(items)
      status = (
          "PASS"
          if (android_devices or "Android Debug Bridge" in output)
          else "INFO"
      )

    elif sec_id == "firewall_tunnels":
      if "Firewall is enabled" in output:
        summary = "Application Firewall is ENABLED (check port blocking)"
        status = "WARN"
      elif "Firewall is disabled" in output:
        summary = "Firewall disabled (no port blocking)"
        status = "PASS"
      else:
        summary = "Firewall / tunnel status checked"
        status = "INFO"

    sections.append({
        "id": sec_id,
        "title": sec_def.title,
        "icon": sec_def.icon,
        "status": status,
        "summary": summary,
        "commands": sec_def.commands,
        "output": output,
    })

    raw_parts.append(
        "========================================================\n"
        f"=== {sec_def.title.upper()} ===\n"
        "========================================================\n"
        f"{output}\n"
    )

  overall_status = "PASS"
  if any(s["status"] == "FAIL" for s in sections):
    overall_status = "FAIL"
  elif any(s["status"] == "WARN" for s in sections):
    overall_status = "WARN"

  primary_ios = ios_devices[0] if ios_devices else None
  primary_android = android_devices[0] if android_devices else None

  devices_summary = {
      "ios": {
          "connected": bool(ios_devices),
          "count": len(ios_devices),
          "devices": ios_devices,
          "model": (
              primary_ios.get("model", "No device detected")
              if primary_ios
              else "No device detected"
          ),
          "udid": primary_ios.get("udid", "N/A") if primary_ios else "N/A",
          "version": primary_ios.get("version", "") if primary_ios else "",
          "name": primary_ios.get("name", "") if primary_ios else "",
      },
      "android": {
          "connected": bool(android_devices),
          "count": len(android_devices),
          "devices": android_devices,
          "model": (
              primary_android.get("model", "No device detected")
              if primary_android
              else "No device detected"
          ),
          "serial": (
              primary_android.get("serial", "N/A") if primary_android else "N/A"
          ),
          "state": primary_android.get("state", "") if primary_android else "",
      },
  }

  return {
      "success": True,
      "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      "overall_status": overall_status,
      "sections": sections,
      "raw_output": "\n".join(raw_parts),
      "devices_summary": devices_summary,
  }
