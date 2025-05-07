# BetoCQ test suite release history

## 2.4.1 (05/07/2025)

## New
* Add Android Auto test suite and test cases.
* Increase SCC test iterations from 10 to 20 and reduce MCC test iterations from 100 to 50.
* Add WiFi Direct capability check.

## Bug fixes
* Fix GMS flag overrides on Windows.

## 2.4.0 (12/20/2024)

## New
* Update Triage tips for the WLAN upgrade failure.
* Add multi-payload test parameters and optimize multi-payload transfer tests.
* Open source Mobly snippet APK codes.

## Bug fixes
* Lower MCC Hotspot speed target as the speed is further degraded due to out-of-sync between source and target devices.
* Move to use hermetic override for P/H flag configuration.

## 2.3.3 (08/27/2024)

## New
* Add TDLS support check and cut the WLAN speed target by half if TDLS is not supported.
* Add Aware device capability check in Aware test which is disabled by default.
* Add Payload.Type.STREAM mode in the function test in addition to the existing FILE mode.

## Bug fixes
* Use upgrade_medium_under_test to set up the speed bar as
  quality_info.upgrade_medium sometimes is not updated correctly.
* Include iperf speed (if available) in the low throughput triaging tips.
* Add the missing space to failure reasons.
* bug fix of instant_connection_count with the correct rounding.
* Add iperf test for WLAN medium as its current speed check is too loose.
* Add a new test parameter check_iperf_speed to check iperf speed if it is available.
* Allow NC speed to be 20% lower than iperf speed.
  
## 2.3.2 (07/29/2024)

## New
* Enable scc_indoor_5g_wfd_sta_test only if both sides support indoor channel feature.
* Add the support of sending multiple files and enable them in function test.
* Add the support of instant connection. This is disabled by default.

## Bug fixes
* Fix the occasional connection issue by disabling WiFi before removing all
  network. When WiFi is active, it is sometimes too busy and leads to the
  network removal or config read timing out after 4s.
* Lower WLAN medium speed from 20 to 15MB/s as it is limited by the encryption
  overhead.
* Disable USB medium to avoid interfering ADB connection.
* Add high RSSI check and warning after the connection failure.

## 2.3.1 (06/24/2024)

## New
* Reformat and unify the test summary field definitions for all tests
* Enable WiFi/BT verbose logging and BT HCI full log.
* Add target model, build_id, wifi_chipset, gms_versions to suite-level
  properties.
* Add the devices-too-close issue to the common known issue list.
* Set AP's country code when using OpenWrt AP device.


### Bug fixes
* Add idle time after wifi connection for WLAN function test.
* Fix the keepAlive timeout and interval for BLE/BT performance tests which now
  use 30s timeout instead of 10s.
* Report per-iteration test info with a separate line for each field.
* Don't force telephony country code by default as it changes timestamp which
  makes debugging difficult.
* Add an option to run iperf test only if NC speed is low.
* Disable iperf speed test by default.
* Disable iperf speed check even if the test is done.
* Disable max_link_speed check in AP frequency check.

## 2.3 (05/28/2024)

## New
* Skip test if wifi_chipset is empty.
* Add MCC Aware test case with STAs connected to 2G/5G.
* Make connection, advertising/discovery mediums configurable.
* Allow the two devices connect to different SSIDs.
* Raise NC speed bar back to 40MB/s except for WLAN.
* Generate per-test openwrt syslog.
* Add 3p api function into nearby_connections_function_test.py.
* Report the suite name to the test summary.
* Enable individual test selection from the command-line.

### Bug fixes
* Add 10s delay after sta connection to allow scan, DHCP and internet
  validation to complete.
* Fix the bug that it can not run the test cases of eSIM and Quick Share.
* Clarify the failure reasons for some test failures.
* Fix the issue that wlan1 is not correctly detected.
* Fix the timestamp in failed iteration logs.
* Reduce wait time between iteration from 13s to 3s.

## 2.2 (05/10/2024)

## New
* Add iperf test for Aware, hotspot modes.
* Disable WLAN deny list so that the past failure won't affect the new runs.
* Add the key test info in test summary.
* Add the STA and medium info of failed iterations.
* Add P2P frequency check for MCC test cases.
* Add more failure triage tips.

### Bug fixes
* Improve the format of common triaging tips.
* Don't check max link speed for the disconnection check.
* Fix the format of triaging tips.
* Fix the control in test config.
* Fall back to use "adb shell cmd wifi status" when wifiGetConnectionInfo() fails.

## 2.1 (05/02/2024)

## New
* Add iperf test for WFD mode. iperf test speed requirement is 40MB/s while Nearby
  Connections speed requirement is 20MB/s in 2-stream 80MHz mode.
* Add the BT coex performance test.
* Add the support of BLE scan throttling during 2G transfer (enabled by default)
* Change the success rate target to 98%.
* Add Aware test case and enable it for QuickShare CUJ.
* Enable scc_2g_wfd_sta_tests for all devices.

### Bug fixes
* Fix the missing data of failed test cases by replacing all "sponge_properties"
  with "properties".
* Remove the unnecessary flag overriding and rely on the production config instead.
* Add the check of AP connection. If AP is disconnected or connect to a wrong
  frequency on the target side, mark the test as failed.
* Consolidate AP connection and speed check codes to one function.
* Add P2P frequency check for WFD/HS SCC test cases.
* Reduce 2G speed check from 3 to 1 MB/s until it is improved in NC.
* Remove AP frequency check for the test cases with empty wifi_ssid.
* Fix typo in DFS test cases and reduce BT transfer size by 50%.
* Skip p2p frequency check if wifi speed check is disabled or it is a DBS test.
* Add the method overriding annotation.
* Add more triaging tips for AP disconnected, wrong AP frequency and P2P/STA
  frequency mismatch cases.

## 2.0 (04/10/2024)

### New
* BetoCQ test suite: improved test coverage with the right quality bar taking into
  device capabilities
  * CUJ tests: Connectivity performance evaluation for the specific CUJs, such
  as Quickstart, Quickshare, etc.
  * Directed tests: Performance test with fixed D2D medium.
  * Function tests: Tests for the basic functions used by D2D connection.

## 1.6

### New
* `nearby_share_stress_test.py` for testing Nearby Share using Wifi only.

### Fixes
* Change discovery medium to BLE only.
* Increase 1G file transfer timeout to 400s.
* Disable GMS auto-updates for the duration of the test.

## 1.5

### New
* `esim_transfer_stress_test.py` for testing eSIM transfer using Bluetooth only.
* `quick_start_stress_test.py` for testing the Quickstart flow using both
   Bluetooth and Wifi.
