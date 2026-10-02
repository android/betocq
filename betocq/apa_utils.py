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

"""Utilities for APA integration, including device info and metrics collection."""

from collections.abc import Sequence
import json
import logging
import os

from mobly import base_test
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import adb


def _collect_generic_device_info(
    ad: android_device.AndroidDevice, edi_dir: str
) -> None:
  """Collects generic device build properties and writes GenericDeviceInfo JSON."""
  props = {
      'build_id': 'ro.build.id',
      'build_product': 'ro.build.product',
      'build_device': 'ro.product.device',
      'build_board': 'ro.product.board',
      'build_manufacturer': 'ro.product.manufacturer',
      'build_brand': 'ro.product.brand',
      'build_model': 'ro.product.model',
      'build_type': 'ro.build.type',
      'build_fingerprint': 'ro.build.fingerprint',
      'build_abi': 'ro.product.cpu.abi',
      'build_abi2': 'ro.product.cpu.abi2',
      'build_abis': 'ro.product.cpu.abilist',
      'build_abis_32': 'ro.product.cpu.abilist32',
      'build_abis_64': 'ro.product.cpu.abilist64',
      'build_serial': 'ro.serialno',
      'build_version_release': 'ro.build.version.release',
      'build_version_sdk': 'ro.build.version.sdk',
      'build_version_security_patch': 'ro.build.version.security_patch',
  }
  info = {key: ad.adb.getprop(prop) for key, prop in props.items()}

  if not info.get('build_serial'):
    info['build_serial'] = ad.serial

  if info.get('build_version_sdk'):
    info['build_version_sdk_int'] = info['build_version_sdk']

  filepath = os.path.join(edi_dir, 'GenericDeviceInfo.deviceinfo.json')
  try:
    with open(filepath, 'w') as f:
      json.dump(info, f, indent=2)
  except OSError as e:
    logging.warning('Failed to write generic device info: %s', e)


def _collect_feature_device_info(
    ad: android_device.AndroidDevice, edi_dir: str
) -> None:
  """Collects device features via pm and writes FeatureDeviceInfo JSON."""
  try:
    output = ad.adb.shell(['pm', 'list', 'features']).decode('utf-8')
  except (adb.AdbError, UnicodeDecodeError) as e:
    logging.warning('Failed to collect feature device info: %s', e)
    return

  features = []
  for line in output.splitlines():
    if not line.startswith('feature:'):
      continue
    feature_str = line.removeprefix('feature:')
    if '=' in feature_str:
      name, version_str = feature_str.split('=', 1)
      try:
        version = int(version_str)
      except ValueError:
        version = 0
    else:
      name = feature_str
      version = 0

    features.append({
        'name': name,
        'type': 'sdk' if name.startswith('android.') else 'other',
        'available': True,
        'version': version,
    })

  info = {'feature': features}
  filepath = os.path.join(edi_dir, 'FeatureDeviceInfo.deviceinfo.json')
  try:
    with open(filepath, 'w') as f:
      json.dump(info, f, indent=2)
  except OSError as e:
    logging.warning('Failed to write feature device info: %s', e)


def _collect_property_device_info(
    ad: android_device.AndroidDevice, edi_dir: str
) -> None:
  """Collects system properties via getprop and writes PropertyDeviceInfo JSON."""
  try:
    output = ad.adb.shell(['getprop']).decode('utf-8')
  except (adb.AdbError, UnicodeDecodeError) as e:
    logging.warning('Failed to collect property device info: %s', e)
    return

  properties = []
  for line in output.splitlines():
    if ']: [' not in line:
      continue
    name_value = line.strip()[1:-1]
    if ']: [' not in name_value:
      continue
    name, value = name_value.split(']: [', 1)
    properties.append({'name': name, 'value': value})

  info = {'ro_property': properties}
  filepath = os.path.join(edi_dir, 'PropertyDeviceInfo.deviceinfo.json')
  try:
    with open(filepath, 'w') as f:
      json.dump(info, f, indent=2)
  except OSError as e:
    logging.warning('Failed to write property device info: %s', e)


def _collect_package_device_info(
    ad: android_device.AndroidDevice, edi_dir: str
) -> None:
  """Collects installed packages via pm and writes PackageDeviceInfo JSON."""
  try:
    output = ad.adb.shell(['pm', 'list', 'packages']).decode('utf-8')
  except (adb.AdbError, UnicodeDecodeError) as e:
    logging.warning('Failed to collect package device info: %s', e)
    return

  packages = []
  for line in output.splitlines():
    if not line.startswith('package:'):
      continue
    package_name = line.removeprefix('package:')
    packages.append({
        'name': package_name,
    })

  info = {'package': packages}
  filepath = os.path.join(edi_dir, 'PackageDeviceInfo.deviceinfo.json')
  try:
    with open(filepath, 'w') as f:
      json.dump(info, f, indent=2)
  except OSError as e:
    logging.warning('Failed to write package device info: %s', e)


class ApaInfoMixin(base_test.BaseTestClass):
  """Mixin to enable apa_info configuration in test summary for APA ingestion."""

  # Class-level state is mutated intentionally so APA metadata is resolved and
  # recorded to test_summary.yaml only once across all test classes in a suite.
  _apa_info_recorded = False
  _resolved_apa_target_device: str | None = None

  def setup_test(self) -> None:
    super().setup_test()
    if not ApaInfoMixin._apa_info_recorded:
      self.resolve_and_record_apa_info()

  def resolve_and_record_apa_info(self) -> None:
    """Resolves apa_target_device to a device serial and records apa_info."""
    if 'apa_info' not in self.user_params:
      ApaInfoMixin._apa_info_recorded = True
      return

    if ApaInfoMixin._apa_info_recorded:
      if ApaInfoMixin._resolved_apa_target_device and isinstance(
          self.user_params.get('apa_info'), dict
      ):
        self.user_params['apa_info'][
            'apa_target_device'
        ] = ApaInfoMixin._resolved_apa_target_device
      return

    ads = getattr(self, 'ads', None)
    if not ads:
      raise RuntimeError(
          'No Android devices found in self.ads. Please register all Android'
          ' devices to self.ads.'
      )

    apa_info = dict(self.user_params.get('apa_info', {}))
    if (
        'all_test_must_pass' in self.user_params
        and 'all_test_must_pass' not in apa_info
    ):
      apa_info['all_test_must_pass'] = self.user_params['all_test_must_pass']

    target_device_ident = apa_info.get('apa_target_device')
    target_ad = None

    if target_device_ident:
      for ad in ads:
        if ad.serial == target_device_ident:
          target_ad = ad
          break

    if not target_ad and target_device_ident:
      for ad in ads:
        role = getattr(ad, 'role', None)
        if (
            not role
            and hasattr(ad, 'dimensions')
            and isinstance(ad.dimensions, dict)
        ):
          role = ad.dimensions.get('role')
        if role == target_device_ident:
          target_ad = ad
          break

    if not target_ad:
      target_ad = ads[0]
      logging.warning(
          'apa_target_device "%s" not found by serial or role; '
          'choosing device %s as target device.',
          target_device_ident,
          target_ad.serial,
      )

    apa_info['apa_target_device'] = target_ad.serial
    ApaInfoMixin._resolved_apa_target_device = target_ad.serial

    if isinstance(self.user_params.get('apa_info'), dict):
      self.user_params['apa_info'].update(apa_info)
    else:
      self.user_params['apa_info'] = apa_info

    self.record_data({'properties': apa_info})
    ApaInfoMixin._apa_info_recorded = True


class EdiCollectionMixin(base_test.BaseTestClass):
  """Mixin to collect EDI files for APA ingestion."""

  # Class-level state is mutated intentionally so EDI files are collected only
  # once per suite execution across multiple Mobly test classes.
  _edi_collected = False

  def setup_test(self) -> None:
    super().setup_test()
    if EdiCollectionMixin._edi_collected:
      return

    if isinstance(self, ApaInfoMixin):
      self.resolve_and_record_apa_info()

    ads = getattr(self, 'ads', None)
    if not ads:
      raise RuntimeError(
          'No Android devices found in self.ads. Please register all Android'
          ' devices to self.ads.'
      )

    try:
      self._collect_edi_if_needed(ads)
    except Exception:  # pylint: disable=broad-exception-caught
      logging.warning('Exception during EDI collection.', exc_info=True)
    finally:
      EdiCollectionMixin._edi_collected = True

  def _collect_edi_if_needed(
      self, ads: Sequence[android_device.AndroidDevice]
  ) -> None:
    if 'apa_info' not in self.user_params:
      return

    apa_info = self.user_params.get('apa_info', {})
    target_serial = apa_info.get('apa_target_device')
    if not target_serial:
      logging.warning(
          'apa_target_device not specified in apa_info, skipping EDI'
          ' collection.'
      )
      return

    target_ad = None
    for ad in ads:
      if ad.serial == target_serial:
        target_ad = ad
        break

    if not target_ad:
      logging.warning(
          'Could not find device with serial %s, skipping EDI collection.',
          target_serial,
      )
      return

    self._collect_edi_for_device(target_ad)

  def _collect_edi_for_device(self, ad: android_device.AndroidDevice) -> None:
    edi_dir = os.path.join(self.root_output_path, 'device-info-files')
    os.makedirs(edi_dir, exist_ok=True)
    logging.info('Collecting EDI files to %s for device %s', edi_dir, ad.serial)

    _collect_generic_device_info(ad, edi_dir)
    _collect_feature_device_info(ad, edi_dir)
    _collect_property_device_info(ad, edi_dir)
    _collect_package_device_info(ad, edi_dir)
    logging.info('EDI files collection completed.')
