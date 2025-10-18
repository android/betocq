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

"""class to enable/disable GMS auto update."""

import logging
import os
import tempfile
from xml.etree import ElementTree
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import adb


_FINSKY_CONFIG_FILE = '/data/data/com.android.vending/shared_prefs/finsky.xml'
_FINSKY_CONFIG_NAME = 'auto_update_enabled'
_FINSKY_CONFIG_VALUE_DISABLE = 'false'
_FINSKY_CONFIG_VALUE_ENABLE = 'true'
_VENDING_CONFIG_FILE = '/data/data/com.android.vending/shared_prefs/com.android.vending_preferences.xml'
_VENDING_CONFIG_NAME = 'auto-update-mode'
_VENDING_CONFIG_VALUE_DISABLE = 'AUTO_UPDATE_NEVER'
_VENDING_CONFIG_VALUE_ENABLE = 'AUTO_UPDATE_WIFI'
_BLANK_CONFIG = '<?xml version="1.0" encoding="utf-8"?><map></map>'
_XML_BOOL_TYPE = 'boolean'
_XML_STRING_TYPE = 'string'
_ENABLE_GSERVICES_CMD_TEMPLATE = [
    (
        'am broadcast '
        '-a com.google.gservices.intent.action.GSERVICES_OVERRIDE '
        '-e finsky.play_services_auto_update_enabled {}'
    ),
    (
        'am broadcast '
        '-a com.google.gservices.intent.action.GSERVICES_OVERRIDE '
        '-e finsky.setup_wizard_additional_account_vpa_enable {}'
    ),
]

_ENABLE_GMS_CORE_CHECKINS_AND_UPDATES = [
    (
        'am broadcast -a com.google.android.gms.phenotype.FLAG_OVERRIDE '
        '--es package com.google.android.gms --es user "*" '
        '--esa flags Chimera__config_checkin_enabled --esa values true '
        '--esa types boolean com.google.android.gms'
    ),
    (
        'am broadcast -a com.google.android.gms.phenotype.FLAG_OVERRIDE '
        '--es package com.google.android.gms --es user "*" '
        '--esa flags "Chimera__disable_config_checkin_for_tests" '
        '--esa values false --esa types boolean com.google.android.gms'
    ),
    (
        'am broadcast -a com.google.android.finsky.shellservice.COMMAND '
        '-p com.android.vending --es command override_phenotype_flags '
        '--es flag_type regular --es SelfUpdate__do_not_schedule true'
    ),
    (
        'am broadcast -a com.google.android.finsky.shellservice.COMMAND '
        '-p com.android.vending --es command override_phenotype_flags '
        '--es flag_type regular '
        '--es AutoUpdateCodegen__gms_auto_update_enabled true'
    )
]

_DISABLE_GMS_CORE_CHECKINS_AND_UPDATES = [
    (
        'am broadcast -a com.google.android.gms.phenotype.FLAG_OVERRIDE '
        '--es package com.google.android.gms --es user "*" '
        '--esa flags Chimera__config_checkin_enabled --esa values false '
        '--esa types boolean com.google.android.gms'
    ),
    (
        'am broadcast -a com.google.android.gms.phenotype.FLAG_OVERRIDE '
        '--es package com.google.android.gms --es user "*" '
        '--esa flags "Chimera__disable_config_checkin_for_tests" '
        '--esa values true --esa types boolean com.google.android.gms'
    ),
    (
        'am broadcast -a com.google.android.finsky.shellservice.COMMAND '
        '-p com.android.vending --es command override_phenotype_flags '
        '--es flag_type regular --es SelfUpdate__do_not_schedule false'
    ),
    (
        'am broadcast -a com.google.android.finsky.shellservice.COMMAND '
        '-p com.android.vending --es command override_phenotype_flags '
        '--es flag_type regular '
        '--es AutoUpdateCodegen__gms_auto_update_enabled false'
    )
]


class GmsAutoUpdatesUtil:
  """class to enable/disable GMS auto updates."""

  def __init__(self, ad: android_device.AndroidDevice):
    self._device: android_device.AndroidDevice = ad

  def enable_gms_auto_updates(self) -> None:
    self._config_gms_auto_updates(True)

  def disable_gms_auto_updates(self) -> None:
    self._config_gms_auto_updates(False)

  def _config_gms_auto_updates(self, enable_updates: bool) -> None:
    """Configures GMS auto updates."""
    if not self._device.is_adb_root:
      self._device.log.info(
          f'failed to set the play store auto updates as {enable_updates}'
          'you should enable/disable it manually on an unrooted device.')
    else:
      if enable_updates:
        self._configure_play_store_updates(
            _FINSKY_CONFIG_VALUE_ENABLE, _VENDING_CONFIG_VALUE_ENABLE
        )
      else:
        self._configure_play_store_updates(
            _FINSKY_CONFIG_VALUE_DISABLE, _VENDING_CONFIG_VALUE_DISABLE
        )
    self._configure_gservice_updates(enable_updates)
    self._configure_gms_core_checkins_and_updates(enable_updates)

  def _configure_gms_core_checkins_and_updates(
      self, enable_updates: bool
  ) -> None:
    if enable_updates:
      for cmd in _ENABLE_GMS_CORE_CHECKINS_AND_UPDATES:
        self._device.adb.shell(cmd)
    else:
      for cmd in _DISABLE_GMS_CORE_CHECKINS_AND_UPDATES:
        self._device.adb.shell(cmd)

  def _configure_gservice_updates(self, enable_updates: bool) -> None:
    """Overwites Gservice to enable/disable updates."""
    for cmd in _ENABLE_GSERVICES_CMD_TEMPLATE:
      self._device.adb.shell(
          cmd.format('true' if enable_updates else 'false')
      )

  def _create_or_update_play_store_config(
      self,
      tmp_dir: str,
      value_type: str,
      name: str,
      value: str,
      device_path: str,
  ) -> str:
    """Creates or updates a Play Store configuration file.

    The function retrieves the Play Store configuration file from the device
    then update it. If the file does not exist, it creates a new one.

    Args:
        tmp_dir: The temporary directory to store the configuration file.
        value_type: The type of the configuration field.
        name: The name of the configuration field.
        value: The value of the configuration field.
        device_path: The path to the configuration file on the device.

    Returns:
        The path to the updated configuration file.
    """
    path = os.path.join(tmp_dir, f'play_store_config_{name}.xml')
    try:
      self._device.adb.pull([device_path, path])
    except adb.AdbError as e:
      self._device.log.warning('failed to pull %s: %s', device_path, e)

    config_doc = ElementTree.parse(path) if os.path.isfile(path) else None

    changing_element = None
    root = (
        ElementTree.fromstring(_BLANK_CONFIG.encode())
        if config_doc is None
        else config_doc.getroot()
    )

    # find the element, xPath doesn't work as the name is a reserved word.
    for child in root:
      if child.attrib['name'] == name:
        changing_element = child
        break
    if changing_element is None:
      if value_type == _XML_BOOL_TYPE:
        changing_element = ElementTree.SubElement(root, 'boolean')
      else:
        changing_element = ElementTree.SubElement(root, 'string')
    logging.info('element for %s is %s, %s', name, changing_element.tag,
                 changing_element.attrib)
    if value_type == _XML_BOOL_TYPE:
      changing_element.set('name', name)
      changing_element.set('value', value)
    else:
      changing_element.attrib['name'] = name
      changing_element.text = value

    tree = ElementTree.ElementTree(root)
    tree.write(path, xml_declaration=True, encoding='utf-8')
    return path

  def _configure_play_store_updates(
      self, finsky_config_value: str, vending_config_value: str
  ) -> None:
    """Configures the Play Store update related settings."""
    with tempfile.TemporaryDirectory() as tmp_dir:
      finsky_config = self._create_or_update_play_store_config(
          tmp_dir,
          _XML_BOOL_TYPE,
          _FINSKY_CONFIG_NAME,
          finsky_config_value,
          _FINSKY_CONFIG_FILE,
      )
      self._device.adb.push([finsky_config, _FINSKY_CONFIG_FILE])
      try:
        os.remove(finsky_config)
      except OSError as e:
        logging.warning('failed to remove %s: %s', finsky_config, e)

      vending_config = self._create_or_update_play_store_config(
          tmp_dir,
          _XML_STRING_TYPE,
          _VENDING_CONFIG_NAME,
          vending_config_value,
          _VENDING_CONFIG_FILE,
      )
      self._device.adb.push([vending_config, _VENDING_CONFIG_FILE])
      try:
        os.remove(vending_config)
      except OSError as e:
        logging.warning('failed to remove %s: %s', vending_config, e)
