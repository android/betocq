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

"""Mobly base test class for Neaby Connections.

Override the NCBaseTestClass#_get_country_code method if the test requires
a special country code, the 'US' is used by default.
"""

import logging
import os
import time

from mobly import asserts
from mobly import base_test
from mobly import records
from mobly import utils
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import apk_utils
from mobly.controllers.android_device_lib import errors
from mobly.controllers.wifi import openwrt_device
from mobly.controllers.wifi.lib import wifi_configs
import yaml

from betocq import android_wifi_utils
from betocq import nc_constants
from betocq import setup_utils
from betocq import version

NEARBY_SNIPPET_PACKAGE_NAME = 'com.google.android.nearby.mobly.snippet'
NEARBY_SNIPPET_2_PACKAGE_NAME = 'com.google.android.nearby.mobly.snippet.second'
NEARBY_SNIPPET_3P_PACKAGE_NAME = (
    'com.google.android.nearby.mobly.snippet.thirdparty'
)

# TODO: Need to design external path for OEM.
_CONFIG_EXTERNAL_PATH = 'TBD'
_CUTTLEFISH_VIRTUALIZATION_TYPE = 6


class NCBaseTestClass(base_test.BaseTestClass):
  """The Base of Nearby Connection E2E tests."""

  _run_identifier_is_set = False

  def __init__(self, configs):
    super().__init__(configs)
    self.ads: list[android_device.AndroidDevice] = []
    self.advertiser: android_device.AndroidDevice = None
    self.discoverer: android_device.AndroidDevice = None
    self.test_parameters: nc_constants.TestParameters = (
        nc_constants.TestParameters.from_user_params(self.user_params)
    )
    self._test_result_messages: dict[str, str] = {}
    self._nearby_snippet_apk_path: str = None
    self._nearby_snippet_2_apk_path: str = None
    self._nearby_snippet_3p_apk_path: str = None
    self._openwrt: openwrt_device.OpenWrtDevice | None = None
    self._sniffer: openwrt_device.OpenWrtDevice | None = None
    self._wifi_info: wifi_configs.WiFiConfig | None = None
    self._openwrt_wifi_config: wifi_configs.WiFiConfig | None = None
    self.performance_test_iterations: int = 1
    self.num_bug_reports: int = 0
    self._requires_2_snippet_apks = False
    self._requires_3p_snippet_apks = False
    self.__loaded_2_nearby_snippets = False
    self.__loaded_3p_nearby_snippets = False
    self.__skipped_test_class = False

  def _get_skipped_test_class_reason(self) -> str | None:
    return None

  def setup_class(self) -> None:
    self._setup_openwrt_wifi()
    self._register_sniffer_controller()
    self.ads = self.register_controller(android_device, min_number=2)
    for ad in self.ads:
      if hasattr(ad, 'dimensions') and 'role' in ad.dimensions:
        ad.role = ad.dimensions['role']
    try:
      self.discoverer = android_device.get_device(
          self.ads, role='source_device'
      )
      self.advertiser = android_device.get_device(
          self.ads, role='target_device'
      )
    except errors.Error:
      logging.warning(
          'The source,target devices are not specified in testbed;'
          'The result may not be expected.'
      )
      self.advertiser, self.discoverer = self.ads

    utils.concurrent_exec(
        self._setup_android_hw_capability,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    file_tag = 'files' if 'files' in self.user_params else 'mh_files'
    self._nearby_snippet_apk_path = self.user_params.get(file_tag, {}).get(
        'nearby_snippet', ['']
    )[0]
    if self.test_parameters.requires_bt_multiplex:
      self._requires_2_snippet_apks = True
      self._nearby_snippet_2_apk_path = self.user_params.get(file_tag, {}).get(
          'nearby_snippet_2', ['']
      )[0]
    if self.test_parameters.requires_3p_api_test:
      self._requires_3p_snippet_apks = True
      self._nearby_snippet_3p_apk_path = self.user_params.get(file_tag, {}).get(
          'nearby_snippet_3p', ['']
      )[0]

    # disconnect from all wifi automatically
    utils.concurrent_exec(
        android_wifi_utils.forget_all_wifi,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    utils.concurrent_exec(
        self._setup_android_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    skipped_test_class_reason = self._get_skipped_test_class_reason()
    for ad in self.ads:
      if (
          not ad.wifi_chipset
          and self.test_parameters.skip_test_if_wifi_chipset_is_empty
      ):
        skipped_test_class_reason = 'wifi_chipset is empty in the config file'
        ad.log.warning(skipped_test_class_reason)

    if skipped_test_class_reason:
      self.__skipped_test_class = True
      asserts.abort_class(skipped_test_class_reason)

    self._set_run_identifier()

  def _set_run_identifier(self) -> None:
    """Set a run_identifier property describing the test run context.

    This property is only set once, even if multiple test classes are run as
    part of a test suite.
    """
    if NCBaseTestClass._run_identifier_is_set:
      return
    suite_name_items = [
        nc_constants.BETOCQ_SUITE_NAME,
        self.test_parameters.target_cuj_name,
    ]
    suite_name = '-'.join(suite_name_items)
    run_identifier_items = [
        self.advertiser.adb.getprop('ro.product.manufacturer'),
        self.advertiser.model,
    ]
    run_identifier = '-'.join(run_identifier_items)
    self.record_data({
        'properties': {
            'suite_name': f'[{suite_name}]',
            'run_identifier': run_identifier,
        }
    })
    NCBaseTestClass._run_identifier_is_set = True

  def _setup_openwrt_wifi(self):
    """Sets up the wifi connection with OpenWRT."""
    if not self.user_params.get('use_auto_controlled_wifi_ap', False):
      return

    self._openwrt = self.register_controller(openwrt_device)[0]
    logging.debug('Using device %s as router.', self._openwrt)

    if 'wifi_channel' in self.user_params:
      wifi_channel = self.user_params['wifi_channel']
      self._openwrt_wifi_config = wifi_configs.WiFiConfig(
          channel=wifi_channel,
          country_code=self._get_country_code(),
      )
    else:
      wifi_channel = None
      self._openwrt_wifi_config = wifi_configs.WiFiConfig(
          country_code=self._get_country_code(),
      )
    self._wifi_info = self._openwrt.start_wifi(config=self._openwrt_wifi_config)

    if wifi_channel is None:
      self.test_parameters.wifi_ssid = self._wifi_info.ssid
      self.test_parameters.wifi_password = self._wifi_info.password
    elif wifi_channel == nc_constants.CHANNEL_2G:
      self.test_parameters.wifi_2g_ssid = self._wifi_info.ssid
      self.test_parameters.wifi_2g_password = self._wifi_info.password
    elif wifi_channel == nc_constants.CHANNEL_5G:
      self.test_parameters.wifi_5g_ssid = self._wifi_info.ssid
      self.test_parameters.wifi_5g_password = self._wifi_info.password
    elif wifi_channel == nc_constants.CHANNEL_5G_DFS:
      self.test_parameters.wifi_dfs_5g_ssid = self._wifi_info.ssid
      self.test_parameters.wifi_dfs_5g_password = self._wifi_info.password
    else:
      raise ValueError('Unknown Wi-Fi channel: %s' % wifi_channel)

  def _register_sniffer_controller(self):
    if not self.test_parameters.use_local_sniffer:
      return

    self._sniffer = self.register_controller(local_sniffer_device)[0]
    logging.debug('Using device %s as sniffer.', self._sniffer)

    # Set self._openwrt_wifi_config, which will be used to start packet capture
    # for each test case.
    if 'wifi_channel' in self.user_params:
      wifi_channel = self.user_params['wifi_channel']
      self._openwrt_wifi_config = wifi_configs.WiFiConfig(
          channel=wifi_channel,
          country_code=self._get_country_code(),
      )
    else:
      self._openwrt_wifi_config = wifi_configs.WiFiConfig(
          country_code=self._get_country_code(),
      )

  def _setup_android_hw_capability(
      self, ad: android_device.AndroidDevice
  ) -> None:
    ad.android_version = int(ad.adb.getprop('ro.build.version.release'))

    if not os.path.isfile(_CONFIG_EXTERNAL_PATH):
      return
    config_path = _CONFIG_EXTERNAL_PATH

    with open(config_path, 'r') as f:
      rule = yaml.safe_load(f).get(ad.model, None)
      if rule is None:
        ad.log.warning(f'{ad} Model {ad.model} is not supported in config file')
        return
      for key, value in rule.items():
        ad.log.debug('Setting capability %s to %s', repr(key), repr(value))
        setattr(ad, key, value)

  def _get_country_code(self) -> str:
    return 'US'

  def _disable_play_protect(self, ad: android_device.AndroidDevice) -> None:
    """Disables play protect."""
    ad.adb.shell('settings put global verifier_engprod 1')

  def _is_cuttlefish_device(self, ad: android_device.AndroidDevice) -> bool:
    lease_info = getattr(ad, 'lease_info', None)
    if lease_info is None:
      return False
    virtualization_type = lease_info.leased_device_spec.virtualization_type
    return virtualization_type == _CUTTLEFISH_VIRTUALIZATION_TYPE

  def _setup_android_device(self, ad: android_device.AndroidDevice) -> None:
    ad.debug_tag = ad.serial + '(' + ad.adb.getprop('ro.product.model') + ')'
    if self._is_cuttlefish_device(ad):
      ad.adb.shell(
          ['settings', 'put', 'global', 'verifier_verify_adb_installs', '0']
      )
      self._disable_play_protect(ad)
    if not ad.is_adb_root:
      if self.test_parameters.allow_unrooted_device:
        ad.log.info('Unrooted device is detected. Test coverage is limited')
      else:
        asserts.abort_all('The test only can run on rooted device.')

    setup_utils.disable_gms_auto_updates(ad)

    ad.debug_tag = ad.serial + '(' + ad.adb.getprop('ro.product.model') + ')'
    ad.log.info('try to install nearby_snippet_apk')
    if self._nearby_snippet_apk_path:
      apk_utils.install(ad, self._nearby_snippet_apk_path)
    else:
      ad.log.warning(
          'nearby_snippet apk is not specified, '
          'make sure it is installed in the device'
      )
    ad.log.info('grant manage external storage permission')
    setup_utils.grant_manage_external_storage_permission(
        ad, NEARBY_SNIPPET_PACKAGE_NAME
    )
    ad.load_snippet('nearby', NEARBY_SNIPPET_PACKAGE_NAME)

    if self._requires_2_snippet_apks:
      ad.log.info('try to install nearby_snippet_2_apk')
      if self._nearby_snippet_2_apk_path:
        apk_utils.install(ad, self._nearby_snippet_2_apk_path)
      else:
        ad.log.warning(
            'nearby_snippet_2 apk is not specified, '
            'make sure it is installed in the device'
        )
      setup_utils.grant_manage_external_storage_permission(
          ad, NEARBY_SNIPPET_2_PACKAGE_NAME
      )
      ad.load_snippet('nearby2', NEARBY_SNIPPET_2_PACKAGE_NAME)
      self.__loaded_2_nearby_snippets = True
    if self._requires_3p_snippet_apks:
      ad.log.info('try to install nearby_snippet_3p_apk')
      if self._nearby_snippet_3p_apk_path:
        apk_utils.install(ad, self._nearby_snippet_3p_apk_path)
      else:
        ad.log.warning(
            'nearby_snippet_3p apk is not specified, '
            'make sure it is installed in the device'
        )
      setup_utils.grant_manage_external_storage_permission(
          ad, NEARBY_SNIPPET_3P_PACKAGE_NAME
      )
      ad.load_snippet('nearby3p', NEARBY_SNIPPET_3P_PACKAGE_NAME)
      self.__loaded_3p_nearby_snippets = True

    setup_utils.remove_disconnect_wifi_network(ad)
    setup_utils.enable_logs(ad)
    if not self.test_parameters.skip_flag_override_in_base_test:
      setup_utils.set_flags(
          ad,
          self.current_test_info.output_path,
          self.test_parameters.enable_instant_connection,
          self.test_parameters.enable_2g_ble_scan_throttling,
      )

    setup_utils.set_country_code(
        ad, self._get_country_code(), self.test_parameters.force_telephony_cc
    )
    if not self.test_parameters.bypass_airplane_mode_toggling:
      setup_utils.toggle_airplane_mode(ad)
    if not ad.nearby.wifiIsEnabled():
      ad.nearby.wifiEnable()

  def setup_test(self):
    self.record_data({
        'Test Name': self.current_test_info.name,
        'properties': {
            'beto_team': 'Nearby Connections',
            'beto_feature': 'Nearby Connections',
        },
    })
    self._reset_nearby_connection()
    self._stop_packet_capture(ignore_packets=True)
    self._start_packet_capture()

  def _start_packet_capture(self) -> None:
    """Starts packet capture if this test is using a sniffer."""
    if self._sniffer is not None:
      self._sniffer.start_packet_capture(wifi_config=self._openwrt_wifi_config)

  def _stop_packet_capture(self, ignore_packets: bool):
    """Stops packet capture if this test is using a sniffer."""
    if self._sniffer is not None:
      test_info = None if ignore_packets else self.current_test_info
      self._sniffer.stop_packet_capture(test_info)

  def _reset_wifi_connection(self) -> None:
    """Resets wifi connections on both devices."""
    ads = [self.discoverer, self.advertiser]
    utils.concurrent_exec(
        setup_utils.remove_disconnect_wifi_network,
        param_list=[[ad] for ad in ads],
        raise_on_exception=True,
    )

  def _reset_nearby_connection(self) -> None:
    """Resets nearby connection."""
    self.discoverer.nearby.stopDiscovery()
    self.discoverer.nearby.stopAllEndpoints()
    self.advertiser.nearby.stopAdvertising()
    self.advertiser.nearby.stopAllEndpoints()
    if self.__loaded_2_nearby_snippets:
      self.discoverer.nearby2.stopDiscovery()
      self.discoverer.nearby2.stopAllEndpoints()
      self.advertiser.nearby2.stopAdvertising()
      self.advertiser.nearby2.stopAllEndpoints()
    if self.__loaded_3p_nearby_snippets:
      self.discoverer.nearby3p.stopDiscovery()
      self.discoverer.nearby3p.stopAllEndpoints()
      self.advertiser.nearby3p.stopAdvertising()
      self.advertiser.nearby3p.stopAllEndpoints()
    time.sleep(nc_constants.NEARBY_RESET_WAIT_TIME.total_seconds())

  def _teardown_device(self, ad: android_device.AndroidDevice) -> None:
    ad.nearby.transferFilesCleanup()
    setup_utils.enable_gms_auto_updates(ad)

    if self.test_parameters.disconnect_wifi_after_test:
      setup_utils.remove_disconnect_wifi_network(ad)

    ad.unload_snippet('nearby')
    if self.__loaded_2_nearby_snippets:
      ad.unload_snippet('nearby2')
    if self.__loaded_3p_nearby_snippets:
      ad.unload_snippet('nearby3p')

  def teardown_test(self) -> None:
    utils.concurrent_exec(
        lambda d: d.services.create_output_excerpts_all(self.current_test_info),
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )
    if self._openwrt is not None:
      self._openwrt.services.create_output_excerpts_all(self.current_test_info)

  def teardown_class(self) -> None:
    if self.__skipped_test_class:
      logging.info('Skipping teardown class.')
      return

    # handle summary results
    self._summary_test_results()

    utils.concurrent_exec(
        self._teardown_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    if self._openwrt is not None and self._wifi_info is not None:
      self._openwrt.stop_wifi(self._wifi_info)

  def _dict_to_list(self, dic_str_str: dict[str, str]) -> list[str]:
    return [f' {str1}: {str2}' for str1, str2 in dic_str_str.items()]

  def _get_device_attributes(
      self, ad: android_device.AndroidDevice
  ) -> list[str]:
    return [
        f'serial: {ad.serial}',
        f'model: {ad.model}',
        f'build_info: {ad.build_info}',
        f'gms_version: {setup_utils.dump_gms_version(ad)}',
        f'wifi_chipset: {ad.wifi_chipset}',
        f'wifi_fw: {ad.adb.getprop("vendor.wlan.firmware.version")}',
        f'support_5g: {ad.supports_5g}',
        f'support_dbs_sta_wfd: {ad.supports_dbs_sta_wfd}',
        (
            'enable_sta_dfs_channel_for_wfd:'
            f' {ad.enable_sta_dfs_channel_for_peer_network}'
        ),
        (
            'enable_sta_indoor_channel_for_wfd:'
            f' {ad.enable_sta_indoor_channel_for_peer_network}'
        ),
        f'max_num_streams: {ad.max_num_streams}',
        f'max_num_streams_dbs: {ad.max_num_streams_dbs}',
        f'support_aware: {setup_utils.is_wifi_aware_available(ad)}',
    ]

  def _get_test_summary_dict(self, test_result: str) -> dict[str, str]:
    """Returns test summary dictionary."""
    return {
        '00_test_script_verion': version.TEST_SCRIPT_VERSION,
        '01_test_result': test_result,
        '02_device_source': '\n'.join(
            self._get_device_attributes(self.discoverer)
        ),
        '03_device_target': '\n'.join(
            self._get_device_attributes(self.advertiser)
        ),
        '04_target_build_id': f'{self.advertiser.build_info["build_id"]}',
        '05_target_model': f'{self.advertiser.model}',
        '06_target_gms_version': (
            f'{setup_utils.dump_gms_version(self.advertiser)}'
        ),
        '07_target_wifi_chipset': f'{self.advertiser.wifi_chipset}',
    }

  def _summary_test_results(self):
    """Summarizes test results of all tests."""

    test_result = '\n'.join(self._dict_to_list(self._test_result_messages))
    self.record_data({
        'Test Class': self.TAG,
        'properties': self._get_test_summary_dict(test_result),
    })

  def on_fail(self, record: records.TestResultRecord) -> None:
    if self.__skipped_test_class:
      logging.info('Skipping on_fail.')
      return
    self._stop_packet_capture(ignore_packets=False)
    if self.test_parameters.skip_bug_report:
      logging.info('Skipping bug report.')
      return
    self.num_bug_reports = self.num_bug_reports + 1
    if self.num_bug_reports <= nc_constants.MAX_NUM_BUG_REPORT:
      logging.info('take bug report for failure')
      android_device.take_bug_reports(
          self.ads,
          destination=self.current_test_info.output_path,
      )

  def on_pass(self, record: records.TestResultRecord) -> None:
    self._stop_packet_capture(ignore_packets=True)
