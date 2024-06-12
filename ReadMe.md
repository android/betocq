# Better Together Connectivity Quality (BeToCQ) Test Suite

Better Together Connectivity Quality (BeToCQ) is a new test tool built by
Android to test the cross-device connectivity performance that isn't covered
by the existing Android tests.

This tool is built on the top of the Nearby Connections API. Under Nearby
Connections, it has Android connectivity stack including Bluetooth, Wi-Fi, NFC,
and UWB technologies.

BeToCQ is designed to catch connectivity software and hardware performance
issues by measuring detailed quality signals including the discovery, connection
latency, transfer speed, and overall success rate.

Depending on the device capabilities, the test takes two to six hours to
complete.

## Test types {:#test-types}

BeToCQ consists of three parts:

- Function test

  The function test ensures hardware and software readiness for each radio
  technology.

- Directed test

  The directed test measures performance of each wireless medium against
  expectations. To discover the radio concurrency issue, sometimes multiple
  mediums are enabled at the same time during the test.

  The function and direct tests are the foundational tests running with
  fixed wireless mediums. This helps isolate the issue to an individual medium
  and makes the debugging process more straightforward.

- Critical user journey (CUJ) test

  The CUJ test tests the real use case. Different from function and
  directed test, the CUJ test can use multiple radios in a more dynamic way. So the
  debugging is typically more difficult in CUJ tests. That's why CUJ tests run as
  the last step when the other tests have already passed.

  CUJ test are implemented as the test cases defined in the `compound_test`
  directory, and are dynamically configured based on the CUJ requirements. The
  term `compound_test` refers to the fact that it uses multiple radios in a
  dynamic way.

  The test suite currently supports three CUJs: Quick Start, Quick Share, and eSIM
  transfer. We plan to add more CUJs in later releases.

## Device capabilities {:#device-capabilities}

The exact connectivity performance depends on the device capability.
For example, the low-cost 2&nbsp;GHz-only Wi-Fi device achieves a lower speed
than the dual-band Wi-Fi device. On the other hand, the dual-band-simultaneous
(DBS) capable device can support a 2G infrastructure-STA connection and 5G
device-to-device connection in parallel and thus can support higher
device-to-device transfer speed.

As a result, this test suite uses the wireless capabilities of test devices as
inputs to customize the test case and set the right performance expectations.

## Test cases {:#test-cases}

In the directed and CUJ tests, depending on the device capabilities,
test cases are defined to cover:

- Different Wi-Fi concurrencies: single-channel concurrency (SCC) versus
  multi-channel concurrency (MCC)
- Different wireless channels: 2G, 5G, 5G DFS, and 5G indoor

The test cases uses the following naming convention:

```
 ConcurrencyMode_MediumBand_MediumName_StaBand_sta_test
```

For example, `scc_indoor_5g_wfd_sta_test` means:

- WLAN and Wi-Fi Direct (WFD) concurrency mode operates in the same channel.
- Transfer medium is WFD.
- Both STA and WFD are connected to 5G indoor channel (for example, 5180 in JP).

Similarly, `mcc_5g_all_wifi_non_dbs_2g_sta_test` means:
outmod betocq_test_suite

- Transfer medium can be any 5G Wi-Fi medium.
- STA is connected to the 2G band and the transfer medium is connected to the 5G band.
- Device isn't capable of DBS and so it operates in MCC mode.

Note that some test cases are skipped if they aren't supported by the device
capabilities. For example:

- `scc_indoor_5g_wfd_sta_test` is skipped if the device doesn't
 support WFD group owner (GO) at the 5G indoor channel.

- `mcc_5g_all_wifi_non_dbs_2g_sta_test` is skipped for DBS capable devices.

Each test case runs multiple iterations to collect the following stats:

- Success rate
- Failure reason for each failed iteration
- Discovery latency stats
- Connection latency stats
- Wi-Fi upgrade latency stats
- Transfer speed stats

MCC test cases run more iterations than SCC test cases.
5G test cases transfer larger files than 2G test cases.

The test cases execution depends on the device capability, so it's
important to fill in the device capabilities section correctly in the test
configuration file. We'll discuss this in more detail in the following sections.

## Actionable test results {:#actional-test-results}

Running the test is straightforward, but it can be difficult to get insights out
of the test results and determine further action to take.

BetoCQ takes three steps to address this issue:

- Simplifies the test report review with the visualized test summary.

- Sets the proper performance expectations based
  on devices capabilities.  The test results are compared against the expectations
  so that there are clear pass/failure signals.

- Makes debugging job more straightforward, with the test isolating each failure
  to a single component. The tool also provides the most likely failure
  reasons and suggest next steps for debugging and appropriate component owner.

## Prerequisites {:#test-prerequisites}

*   **Environment.**

    We recommend an RF shielding box or room to run the test.

*   **Wi-Fi Access Point (AP) and network.**

    The test AP must be a dual-band capable Wi-Fi AP with two SSIDs (one at
    2&nbsp;GHz and one at 5&nbsp;GHz) with support for DFS channels. Example of
    routers that meet the testing requirements include NETGEAR RAX50 AX5400,
    NETGEAR RAX120 AX6000, and NETGEAR R8000b AC3200. It's ideal to use two APs
    to support all test cases. The test AP must have the access to
    google.com. Note that in China, this test requires an office VPN network or
    installing a VPN app in devices.

*   **Target device.**

    The target device must run a userdebug image of the latest Android version,
    for example, Android 14. **This is the device that is being validated.**

*   **Source device.**

    Run the suite and pass the quality bar with one source device
    running a userdebug image of the latest Android version. We recommend a
    model with known good connectivity performance. Some options are:
    - A model that already passed the automated test suite as a target.
    - A flagship model with no known major Bluetooth and Wi-Fi issues.
    - A Google Pixel 8

*   **Prepare devices.**

    Before you run the automated test, prepare all devices by completing the
    device setup processes. After the new devices are set up, connect them to
    the internet for at least one hour to ensure each is properly configured.

    Follow the instructions listed in [Google Play Protect]
    (https://support.google.com/googleplay/answer/2812853)
    to turn off Google Play Protect so that the test APK can run properly.

    Keep the device awake while charging so that the operating system doesn't
    suspend the test snippet process.

    To avoid the strong signal issue, keep two devices at least 10 cm away. This
    is especially important for 2G test as the 2G signal is typically stronger
    than 5G or 6G signal.


## Test steps {:#test-steps}

Follow these steps to prepare and execute tests and review test results.

### Prepare the test {:#test-prep}

Prepare the following materials to be used for the tests.

#### Get the test codes, tools, and configure build {:#test-codes}

1.  Download the release test binary files (see release instructions) and save them
in a local directory:
  - `betocq_test_suite` (Linux and macOS)
  - `betocq_test_suite_windows.zip` (Windows only)
  - `local_mobly_runner.py`
  - `cuj_and_test_config.yml`

2. Make these two files executable (Linux and macOS only):

  ```
  chmod +x betocq_test_suite
  chmod +x local_mobly_runner.py
  ```

3.  Check and install Python version 3.11 or later:
    -   Check your Python 3 version number:

      ```
      python3 --version
      ```

    -   If your version is lower than Python 3.11, install Python 3.11 or later:

      ```
      sudo apt install python3
      ```
      Or install the latest version from
      [python.org](https://www.python.org/downloads/windows) for Windows.

4. Windows only: Download [adb](https://developer.android.com/tools/releases/platform-tools)
   and add its path to the [`Path` environment variable](https://stackoverflow.com/questions/44272416/how-to-add-a-folder-to-path-environment-variable-in-windows-10-with-screensho).

#### Configure Wi-Fi AP and test {:#config}

1. Configure Wi-Fi AP channel frequency:

  -   There are three Wi-Fi channels to be tested: 2437, 5180, and 5260.
      5260 is a [DFS channel]
        (https://en.wikipedia.org/wiki/List_of_WLAN_channels).

  -   If there are two dual-band APs, all three Wi-Fi channels can be supported.


2. Modify the test config file `cuj_and_test_config.yml` as follows:
    -  Find device serial numbers:

        ```
        adb devices -l
        List of devices attached
          17011FDEE0002N  device usb:1-1 product:raven model:Pixel_6_Pro
          R3CN90YNAR      device usb:1-2 product:p3sksx model:SM_G998N
        ```

        In this example, the source device is 17011FDEE0002N and the target
        device is R3CN90YNAR.

    -  Specify the target and source device serial numbers:

        ```
        - serial: "17011FDEE0002N"
          role: "source_device"
        ```

        ```
        - serial: "R3CN90YNAR"
          role: "target_device"
        ```

    -  Specify `wifi_ssid` and `wifi_password` for each Wi-Fi channel:

        ```
          wifi_2g_ssid: "NETGEAR62-2G"
          wifi_2g_password: "yourpassword"
          wifi_5g_ssid: "NETGEAR62-5G-1"
          wifi_5g_password: "yourpassword"
          wifi_dfs_5g_ssid: "ASUS_5G"
          wifi_dfs_5g_password: "yourpassword"
        ```

        Where `wifi_2g_ssid` is for the channel of 2437, `wifi_2g_ssid` is for
        the channel of 5180 and `wifi_dfs_5g_ssid` is for the channel of 5260.

        Leave `wifi_password` as an empty string `""` if it's an open network.

    - Split the test into two runs if the required channels can't be supported
      at the same time:

      1. In the first run, define 2G and 5G SSID but leave the 5G DFS SSID to an empty
         string `""` so that the 5G DFS test cases are skipped.
      2. In the second run, define the 5G DFS SSID but leave the 2G and 5G SSID as empty
         strings to cover the 5G DFS test case.

3. Configure device capabilities for both source and target devices.

      For example, the following configuration means the device uses Wi-Fi
      chipset WCN6710, and supports two spatial streams with the maximum PHY rate of
      2402&nbsp;Mbps (2x2, 11AX, 160&nbsp;MHz) at 5G and 287&nbsp;Mbps (2x2, 11AX,
      20&nbsp;MHz) at 2G. This device doesn't support STA + WFD concurrency in DBS mode.
      It doesn't support starting WFD group owner mode at an STA-associated DFS or
      indoor channel.

      ```
        wifi_chipset: "wcn6710"
        # The max number of spatial streams
        max_num_streams: 2
        # The max PHY rate at 5G, in Mbps
        max_phy_rate_5g_mbps: 2402
        # The max PHY rate at 2G, in Mbps
        max_phy_rate_2g_mbps: 287
        # if the device supports 5G Wi-Fi
        supports_5g: True
        # if the device supports DBS in STA and Wi-Fi Direct concurrency mode
        supports_dbs_sta_wfd: False
        # The max number of spatial streams in DBS mode.
        max_num_streams_dbs: 1
        # if the device supports to start WFD group owner at a STA-associated DFS channel
        enable_sta_dfs_channel_for_peer_network: False
        # if the device supports to start WFD group owner at a STA-associated indoor channel
        enable_sta_indoor_channel_for_peer_network: False
      ```

      For the last two parameters, review `config_wifiEnableStaDfsChannelForPeerNetwork`
      and `config_wifiEnableStaIndoorChannelForPeerNetwork` in the Wi-Fi device
      overlay file [`config.xml`] (https://cs.android.com/android/platform/superproject/main/+/main:packages/modules/Wifi/service/ServiceWifiResources/res/values/config.xml).

      Check with the Wi-Fi engineering team about device capabilities details.


### Run the test {:#run-test}
To run the test on Linux directly from AOSP repo:

  - Refer to release instructions below to set up the build environment.

    ```
    source build/envsetup.sh
    lunch aosp_arm-trunk_staging-eng
    ```

  - Run the test with atest:

    ```
    atest -v betocq_test_suite -- --config <local_testbed_directory>/cuj_and_test_config.yml --testbed Quickstart
    ```

To run the test on Linux and macOS with test binary, run the following commands from the local
directory:

  ```
  python3 local_mobly_runner.py -p ./betocq_test_suite -tb Quickstart -i --novenv -c cuj_and_test_config.yml
  ```

Note that `Quickstart` is the CUJ test name and there are
a few other supported CUJ tests listed in `cuj_and_test_config.yml`.

If there are more than two devices connected to USB ports, specify the device
serial number explicitly:

  ```
  python3 local_mobly_runner.py -p ./betocq_test_suite -tb Quickstart -i --novenv -s <serial1>,<serial2> -c cuj_and_test_config.yml
  ```

Note that no space is allowed between
two device serial numbers in the above commafnd.

To run the test on Windows:

  ```
  python3 local_mobly_runner.py -p ./betocq_test_suite_windows.zip -tb Quickstart -i -c cuj_and_test_config.yml
  ```

### Check the test result and debug failure {:#check-result}

1.  Verify that these lines appear at the end of the test console output:

  ```
  Artifacts are saved in <TestResultDirectory>
  Test summary saved in <TestResultDirectory>/test_summary.yaml
  ```

    Where `<TestResultDirectory>` is something like
    `/tmp/logs/mobly/<CujTestName>/<TestDateTime>`.

2.  Use Result Uploader to upload the artifact folder to Google's result storage
  service so that the test results are visualized. The latest version of the tool
  and instructions are provided in the
 [results_uploader](https://cs.android.com/android/platform/superproject/main/+/main:tools/test/mobly_extensions/tools/results_uploader/).
    -   If this is your first time using the tool, file an issue with Google to
        get onboarded.
    -   Once you upload the artifacts, a link is displayed in the console
        output. Click the link, then click **betocq_test_suite** to display
        a dashboard view of your test results.

3.  Click **MoblyTest** to display the overall test results.
    -   Review the source and target device capability summary.
    -   Review the completed function test result summary.
    -   Review the completed directed and CUJ result summary.

4. If the test passes, no further action is required.

5.  Click each test case (for example, `test_scc_5g_wfd_sta`) to display the
   status of each iteration under **Repeats**.
    -   Green squares indicate passed tests, red squares indicate failed tests.

6. If the test fails, follow the following steps to triage the results:
   1. For each failed test case:

      - Review the test case details including the transfer medium, concurrency
        mode, the channel bands of STA, and the transfer medium.

      - Check if the device capabilities are configured correctly.

      - Review the failed iterations and reasons. Follow the debugging tips to
        triage and work with the internal engineering team.

   2. Click the failed (red) iterations to see the timestamp and detailed
     failure signatures. Here is the list of failure signatures:
      - Wi-Fi STA connection failure signature:

          ```
          Failed to connect to SSID
          ```
          or

          ```
          Failed to remove networks
          ```
      - Discovery failure signature:

          ```
          Timed out after waiting 30.0s for event "onEndpointFound" triggered by startDiscovery
          ```
      - BT connection failure signature:

          ```
          com.google.android.gms.common.api.ApiException: 8007: STATUS_RADIO_ERROR
          at com.google.android.nearby.mobly.snippet.connection.ConnectionsClientSnippet.requestConnection(
          ```
      - Wi-Fi medium upgrade failure signature:

          ```
          Timed out after waiting 25.0s for event "onBandwidthChanged" triggered by requestConnection
          ```
      - Transfer failure signature:

          ```
          Timed out after 110.0s waiting for an "onPayloadTransferUpdate" event
          ```

      - Failure signature due to the GMS updates, which repeats a few times before the test exits:

          ```
          test_log.INFO:
          In send_rpc_request
          No response from server. Check the device logcat for crashes.
          ```

          ```
          logcat and bug report:
          stop com.google.android.gms due to installPackage
          ```
   3. Review the logcat and bug report of each failing iteration on both
    source and target sides. You can find them as boxed links under the test
    name.

   4. Search the following keywords for the related logs in the bug report:
    `WifiP2pService`, `wpa_supplicant`, `NearbyConnections`, and `NearbyMediums`.

   5. Review the Wi-Fi Direct logs in the bug report if the `WIFI_DIRECT` medium is used.
    Check if it's a group owner or client side error when bandwidth upgrade
    fails.

      ```
      DUMP OF SERVICE wifip2p:
      WifiP2pMetrics:
      mConnectionEvents:
      connectionType=FAST, groupRole=CLIENT, freq=5745, sta freq=2437, connectivityLevelFailureCode=NONE
      ```

   6. Check the above STA frequency and P2P frequency values. If both have valid
    values but the values are different, the device likely operates in multiple
    channel concurrency (MCC) mode unless it supports 2G + 5G concurrency.
    In MCC mode, firmware could have the bugs resulting in bandwidth
    upgrade failure or transfer issues. Check with the Wi-Fi chip vendor if there
    are any known bug fixes for MCC mode.

7. To rule out the test setup issue or device issue, repeat the test with a pair
  of known good devices (or a pair of new devices).
    - If the failure persists, check the test setup because it likely has the
  issue. If possible, move the test to a clean environment to rule out the
  interference issue.
    - If the failure disappears, DUT likely has the issue. Work with the Wi-Fi/BT
    engineering team to resolve the device issue. This might require getting
    help from the Wi-Fi/BT chip vendor.

8. If the issue can't be resolved by the internal engineering team and there is
  strong evidence that there might be an issue on the Google side, create an issue
  for Google. Be sure to include all test artifacts.

## Linux and Windows release instructions {:#test-codes}

Skip this unless you want to release the test binary from AOSP.

- Get AOSP codes from
  [AOSP](https://cs.android.com/android/platform/superproject/+/master:platform_testing/tests/bettertogether/betocq/;l=1).

- Build the test binary for Linux and macOS:

  ```
  source build/envsetup.sh
  lunch aosp_arm-trunk_staging-eng
  make betocq_test_suite
  outmod betocq_test_suite
  ```

- Upload these files to a shared drive:

  ```
  tools/test/mobly_extensions/scripts/local_mobly_runner.py
  out/host/linux-x86/nativetest64/betocq_test_suite/betocq_test_suite
  out/host/linux-x86/nativetest64/betocq_test_suite/cuj_and_test_config.yml
  ```

- Generate the zip file for Windows execution:

  ```
  mkdir ~/betocq_windows
  cp platform_testing/tests/bettertogether/betocq/betocq_test_suite.py ~/betocq_windows/__main__.py
  echo mobly > ~/betocq_windows/requirements.txt
  cp -r platform_testing/tests/bettertogether/betocq ~/betocq_windows
  cp out/host/linux-x86/nativetest64/betocq_test_suite/*.apk ~/betocq_windows
  cd ~/betocq_windows
  zip -r ~/betocq_test_suite_windows.zip ./
  ```

- Upload these files to a shared drive:

  ```
  tools/test/mobly_extensions/scripts/local_mobly_runner.py
  out/host/linux-x86/nativetest64/betocq_test_suite/cuj_and_test_config.yml
  ~/betocq_test_suite_windows.zip
  ```
