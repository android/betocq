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

"""Mobly base test class of all BeToCQ tests."""

import logging

import os
import traceback

from mobly import base_test
from mobly import records
from mobly import utils
from mobly.controllers import android_device
from mobly.controllers.android_device_lib import errors
from mobly.controllers.wifi import local_sniffer_device
from mobly.controllers.wifi import openwrt_device
from mobly.controllers.wifi.lib import wifi_configs
import yaml

from betocq import ap_utils
from betocq import nc_constants
from betocq import setup_utils

NEARBY_SNIPPET_PACKAGE_NAME = 'com.google.android.nearby.mobly.snippet'
NEARBY_SNIPPET_2_PACKAGE_NAME = 'com.google.android.nearby.mobly.snippet.second'
NEARBY_SNIPPET_3P_PACKAGE_NAME = (
    'com.google.android.nearby.mobly.snippet.thirdparty'
)

# TODO: Need to design external path for OEM.
_CONFIG_EXTERNAL_PATH = 'TBD'
_CUTTLEFISH_VIRTUALIZATION_TYPE = 6


def _load_android_hw_capability(ad: android_device.AndroidDevice) -> None:
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


class BaseTestClass(base_test.BaseTestClass):
  """The base test class of all BeToCQ tests."""

  _run_identifier_is_set = False
  _ap: openwrt_device.OpenWrtDevice | None = None
  _sniffer: local_sniffer_device.LocalSnifferDevice | None = None
  _sniffer_config: wifi_configs.WiFiConfig | None = None

  def __init__(self, configs):
    super().__init__(configs)
    self.ads: list[android_device.AndroidDevice] = []
    self.advertiser: android_device.AndroidDevice = None
    self.discoverer: android_device.AndroidDevice = None
    self.test_parameters: nc_constants.TestParameters = (
        nc_constants.TestParameters.from_user_params(self.user_params)
    )
    logging.info('all test parameters: %s', self.test_parameters)
    self.num_bug_reports: int = 0
    # Skip the device clean up steps if the test class is skipped.
    self.__skipped_test_class = True
    self.is_using_gms_api = True

  def setup_class(self) -> None:
    if (
        not self.test_parameters.use_programmable_ap
        and self.test_parameters.abort_all_if_any_ap_not_ready
    ):
      error_messages = ''
      if not self.test_parameters.wifi_2g_ssid:
        error_messages += '2G AP is not ready for this test.\n'
        logging.warning('2G AP is not ready for this test.')
      if not self.test_parameters.wifi_5g_ssid:
        error_messages += '5G AP is not ready for this test.\n'
        logging.warning('5G AP is not ready for this test.')
      if not self.test_parameters.wifi_dfs_5g_ssid:
        error_messages += '5G DFS AP is not ready for this test.\n'
        logging.warning('5G DFS AP is not ready for this test.')
      if error_messages:
        setup_utils.abort_all_and_report_error_on_setup(self, error_messages)
    try:
      self.ads = self.register_controller(android_device, min_number=2)
    except errors.Error as e:
      setup_utils.abort_all_and_report_error_on_setup(
          self,
          'Failed to get Android devices with error: %s,'
          f' {traceback.format_exception(e)}',
      )
    for ad in self.ads:
      if hasattr(ad, 'dimensions') and 'role' in ad.dimensions:
        ad.role = ad.dimensions['role']
      if self.is_using_gms_api:
        ad.gms_info = nc_constants.GmsInfo()
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
    self.advertiser.debug_tag = '{serial}({model})'.format(
        serial=self.advertiser.serial,
        model=self.advertiser.adb.getprop('ro.product.model'),
    )
    self.discoverer.debug_tag = '{serial}({model})'.format(
        serial=self.discoverer.serial,
        model=self.discoverer.adb.getprop('ro.product.model'),
    )

    self._set_run_identifier()

    utils.concurrent_exec(
        _load_android_hw_capability,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

    self._assert_general_nc_test_conditions()
    self._assert_test_conditions()
    self.__skipped_test_class = False

  def _assert_general_nc_test_conditions(self):
    if not self.test_parameters.allow_unrooted_device:
      logging.info('The test is not allowed to run on unrooted device.')
      if not self.advertiser.is_adb_root or not self.discoverer.is_adb_root:
        logging.warning('The test is aborted because the device is unrooted.')
        setup_utils.abort_all_and_report_error_on_setup(
            self, 'The test only can run on rooted device.'
        )
    if not self.advertiser.wifi_chipset or not self.discoverer.wifi_chipset:
      setup_utils.abort_all_and_report_error_on_setup(
          self, 'wifi_chipset is empty in the config file'
      )

  def _assert_test_conditions(self) -> None:
    """Asserts the test conditions for all devices."""

  def _get_snippet_apk_path(self, snippet_name: str) -> str:
    """Gets the APK path for the given snippet name from user params.

    Args:
      snippet_name: The snippet name used to find the snippet
      APK in user_params (e.g., 'nearby_snippet').

    Returns:
      The path to the snippet APK.

    Raises:
      ValueError: If the snippet APK is not configured correctly.
    """
    file_tag = 'files' if 'files' in self.user_params else 'mh_files'
    apk_paths = self.user_params.get(file_tag, {}).get(snippet_name, [''])
    if not apk_paths or not apk_paths[0]:
      raise ValueError(f'{snippet_name} is not configured correctly.')
    return apk_paths[0]

  @property
  def nearby_snippet_config(self) -> nc_constants.SnippetConfig:
    """Snippet config for loading the first nearby snippet instance."""
    return nc_constants.SnippetConfig(
        snippet_name='nearby',
        package_name=nc_constants.NEARBY_SNIPPET_PACKAGE_NAME,
        apk_path=self._get_snippet_apk_path('nearby_snippet'),
    )

  @property
  def nearby2_snippet_config(self) -> nc_constants.SnippetConfig:
    """Snippet config for loading the second nearby snippet instance."""
    return nc_constants.SnippetConfig(
        snippet_name='nearby2',
        package_name=nc_constants.NEARBY_SNIPPET_2_PACKAGE_NAME,
        apk_path=self._get_snippet_apk_path('nearby_snippet_2'),
    )

  def setup_wifi_env(
      self, d2d_type: nc_constants.WifiD2DType, country_code: str
  ):
    """Sets up the WiFi environment with given d2d type and country code.

    If switches are on, the programmable AP and sniffer will be set up and WiFi
    SSID and password specified in the test parameters will be ignored.

    This should be called in the `setup_class` phase of the test class.

    Args:
      d2d_type: The Wi-Fi D2D type.
      country_code: The country code of the test.
    """
    if d2d_type == nc_constants.WifiD2DType.MCC_5G_AND_5G_DFS_STA and (
        self.test_parameters.use_programmable_ap
        or self.test_parameters.use_sniffer
    ):
      logging.debug(
          'Programmable AP and sniffer are not for d2d type %s which requires'
          ' WiFi networks with different 5G channels.',
          d2d_type,
      )
      return

    wifi_channel = nc_constants.get_wifi_channel(d2d_type)
    if self.test_parameters.use_programmable_ap:
      self._setup_programmable_ap(wifi_channel, country_code)

    if self.test_parameters.use_sniffer:
      self._setup_sniffer(wifi_channel, country_code)

  def _setup_programmable_ap(self, wifi_channel: int, country_code: str):
    """Sets up the programmable AP and starts a WiFi network on it."""
    if self._ap is not None:
      raise RuntimeError('Programmable AP is already set.')
    self._ap = self.register_controller(openwrt_device)[0]
    logging.debug('Using device %s as router.', self._ap)
    ap_utils.start_wifi(
        self._ap, wifi_channel, country_code, self.test_parameters
    )

  def _setup_sniffer(self, wifi_channel: int, country_code: str):
    """Sets up the sniffer to capture packets for each test case."""
    if self._sniffer is not None:
      raise RuntimeError('Sniffer is already set.')
    self._sniffer = self.register_controller(local_sniffer_device)[0]
    self._sniffer_config = wifi_configs.WiFiConfig(
        channel=wifi_channel,
        country_code=country_code,
    )

  def setup_test(self):
    self.record_data({
        'Test Name': self.current_test_info.name,
        'properties': {
            'beto_team': 'Nearby Connections',
            'beto_feature': 'Nearby Connections',
        },
    })
    self._stop_packet_capture(ignore_packets=True)
    self._start_packet_capture()
    self._log_test_start_on_device(self.advertiser)
    self._log_test_start_on_device(self.discoverer)
    if self.is_using_gms_api:
      utils.concurrent_exec(
          lambda ad: ad.gms_info.update_pids(ad),
          param_list=[[ad] for ad in self.ads],
          raise_on_exception=True,
      )

  def _log_test_start_on_device(self, ad: android_device.AndroidDevice):
    setup_utils.log_message_to_logcat(
        ad,
        f'TEST START: {self.current_test_info.name}',
    )

  def _log_test_end_on_device(self, ad: android_device.AndroidDevice):
    setup_utils.log_message_to_logcat(
        ad,
        f'TEST END: {self.current_test_info.name}',
    )

  def _teardown_device(self, ad: android_device.AndroidDevice) -> None:
    ad.nearby.transferFilesCleanup()
    # run it before clear_hermetic_overrides to make sure the GMS restart will
    # not impact on the update of GMS.
    setup_utils.enable_gms_auto_updates(ad)
    # TODO: should it give GMS some time to enable the auto updates?
    setup_utils.clear_hermetic_overrides(ad)

  def teardown_test(self) -> None:
    self._log_test_end_on_device(self.advertiser)
    self._log_test_end_on_device(self.discoverer)
    utils.concurrent_exec(
        lambda d: d.services.create_output_excerpts_all(self.current_test_info),
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

  def teardown_class(self) -> None:
    if self.__skipped_test_class:
      logging.info('Skipping teardown class.')
      return

    utils.concurrent_exec(
        self._teardown_device,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=True,
    )

  def on_fail(self, record: records.TestResultRecord) -> None:
    if self.__skipped_test_class:
      logging.info('Skipping on_fail.')
      return
    logging.info(
        'on_fail with result %s, termination_signal_type %s, stacktrace %s',
        record.result,
        record.termination_signal_type,
        record.stacktrace,
    )
    # abort all test if ProtocolError or BrokenPipeError found in traceback
    if record.result is records.TestResultEnums.TEST_RESULT_ERROR and (
        record.termination_signal_type == 'ProtocolError'
        or (
            record.termination_signal_type == 'AdbError'
            and 'not found' in record.stacktrace
        )
        or (
            'Error' in record.termination_signal_type
            and (
                'mobly.snippet.errors.ProtocolError' in record.stacktrace
                or 'BrokenPipeError' in record.stacktrace
            )
        )
    ):
      error_message = (
          f'Abort all test due to the following error happened during the'
          ' test:\n'
          f'{record.stacktrace}\n'
          'it could be one of the following issues:\n'
          '1. system crashed;\n'
          '2. GMS updating happened, check if the "com.google.android.gms" was'
          ' killed from the logcat, disable the GMS auto update from the play'
          ' store (Settings -> Network perferences) and retry the test;\n'
          '3. The test snippet might be killed by a security app or service'
          ' from the device, especially if this happens very frequently, check'
          ' the logcat to verify if '
          f' {nc_constants.NEARBY_SNIPPET_PACKAGE_NAME} or'
          f' {nc_constants.NEARBY_SNIPPET_2_PACKAGE_NAME} or'
          f' {nc_constants.DCT_SNIPPET_PACKAGE_NAME} or'
          f' {nc_constants.DCT_SNIPPET_2_PACKAGE_NAME} was killed; you should'
          ' put them to the allowlist of the security app.\n'
          '4. The USB cable or port is not stable, change the USB cable or the'
          ' connection portal and try again;\n'
          '5. The "Play protect" in the play store might disable the test'
          ' snippets, disable the "Play Protect" and retry the test.\n'
      )
      logging.error(error_message)
      # show the error in setup_class clearly.
      setup_utils.abort_all_and_report_error_on_setup(self, error_message)

    # Reset the Nearby Connection state to ensure the testbed is in a good
    # state for the next test.
    utils.concurrent_exec(
        setup_utils.reset_nearby_connection,
        param_list=[[ad] for ad in self.ads],
        raise_on_exception=False,
    )

    self._stop_packet_capture(ignore_packets=False)
    if self.test_parameters.skip_bug_report:
      logging.info('skip bug report for failure')
    else:
      self.num_bug_reports = self.num_bug_reports + 1
      if self.num_bug_reports <= nc_constants.MAX_NUM_BUG_REPORT:
        logging.info('take bug report for failure')
        android_device.take_bug_reports(
            self.ads,
            destination=self.current_test_info.output_path,
        )
      else:
        logging.info('reach the max number of bug reports, skip the rest')

  def on_pass(self, record: records.TestResultRecord) -> None:
    # Ignore captured packets when the test passes.
    self._stop_packet_capture(ignore_packets=True)

  def _start_packet_capture(self) -> None:
    """Starts packet capture if this test is using a sniffer."""
    if self._sniffer is not None and self._sniffer_config is not None:
      self._sniffer.start_packet_capture(wifi_config=self._sniffer_config)

  def _stop_packet_capture(self, ignore_packets: bool):
    """Stops packet capture if this test is using a sniffer."""
    if self._sniffer is not None:
      test_info = None if ignore_packets else self.current_test_info
      self._sniffer.stop_packet_capture(test_info)

  def _set_run_identifier(self) -> None:
    """Set a run_identifier property describing the test run context.

    This property is only set once, even if multiple test classes are run as
    part of a test suite.
    """
    if BaseTestClass._run_identifier_is_set:
      return
    suite_name_items = [
        nc_constants.BETOCQ_NAME,
    ]
    if 'suite_name' in self.user_params:
      suite_name_items.append(self.user_params['suite_name'])
    if 'suite_version' in self.user_params:
      suite_name_items.append(f'v{self.user_params['suite_version']}')
    suite_name_items.append(self.test_parameters.target_cuj_name)
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
    BaseTestClass._run_identifier_is_set = True
