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

## Test types

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

## Device capabilities

The exact connectivity performance depends on the device capability.
For example, the low-cost 2&nbsp;GHz-only Wi-Fi device achieves a lower speed
than the dual-band Wi-Fi device. On the other hand, the dual-band-simultaneous
(DBS) capable device can support a 2G infrastructure-STA connection and 5G
device-to-device connection in parallel and thus can support higher
device-to-device transfer speed.

As a result, this test suite uses the wireless capabilities of test devices as
inputs to customize the test case and set the right performance expectations.

## Test cases definition

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

- Transfer medium can be any 5G Wi-Fi medium.
- STA is connected to the 2G band and the transfer medium is connected to the 5G band.
- Device isn't capable of DBS and so it operates in MCC mode.

Each test case runs multiple iterations to collect the following stats:

- Success rate
- Failure reason for each failed iteration
- Discovery latency stats
- Connection latency stats
- Wi-Fi upgrade latency stats
- Transfer speed stats

MCC test cases run more iterations than SCC test cases.
5G test cases transfer larger files than 2G test cases.

Note that some test cases are skipped if they aren't supported by the device
capabilities. For example:

- `scc_indoor_5g_wfd_sta_test` is skipped if the device doesn't
 support WFD group owner (GO) at the 5G indoor channel.

- `mcc_5g_all_wifi_non_dbs_2g_sta_test` is skipped for DBS capable devices.

The test cases execution depends on the device capability, so it's
important to fill in the device capabilities section correctly in the test
configuration file. We'll discuss this in more detail in the following sections.

The DBS capable device pair with both `enable_sta_dfs_channel_for_peer_network`
and `enable_sta_indoor_channel_for_peer_network` set to `False` executes
the following list of test cases:

<table>
  <tr>
   <th>Test case</th>
   <th>Medium</th>
   <th>Wi-Fi STA channel (MHz)</th>
   <th>Wi-Fi country code</th>
  </tr>
  <tr>
   <td>BetoCqFunctionGroupTest</td>
   <td>Various</td>
   <td>Various</td>
   <td>US</td>
  </tr>
  <tr>
   <td>Bt2GWifiCoexTest</td>
   <td>WFD</td>
   <td>2437</td>
   <td>US</td>
  </tr>
  <tr>
   <td>BtPerformanceTest</td>
   <td>BT classic</td>
   <td>N/A</td>
   <td>US</td>
  </tr>
  <tr>
   <td>Mcc2gWfdIndoor5gStaTest</td>
   <td>WFD</td>
   <td>5180</td>
   <td>JP</td>
  </tr>
  <tr>
   <td>Mcc5gHotspotDfs5gStaTest</td>
   <td>Hotspot</td>
   <td>5260</td>
   <td>GB</td>
  </tr>
  <tr>
   <td>Mcc5gWfdDfs5gStaTest</td>
   <td>WFD</td>
   <td>5260</td>
   <td>GB</td>
  </tr>
  <tr>
   <td>Scc2gWfdStaTest</td>
   <td>WFD</td>
   <td>2437</td>
   <td>US</td>
  </tr>
  <tr>
   <td>Scc5gWfdDbs2gStaTest</td>
   <td>WFD</td>
   <td>2437</td>
   <td>US</td>
  </tr>
  <tr>
   <td>Scc5gWfdStaTest</td>
   <td>WFD</td>
   <td>5180</td>
   <td>US</td>
  </tr>
  <tr>
   <td>Scc5gWifiLanStaTest</td>
   <td>WLAN</td>
   <td>5180</td>
   <td>US</td>
  </tr>
  <tr>
   <td>Scc5GAllWifiStaTest</td>
   <td>All Wi-Fi mediums</td>
   <td>5180</td>
   <td>US</td>
  </tr>
  <tr>
   <td>Scc5gAllWifiDbs2gStaTest</td>
   <td>All Wi-Fi mediums</td>
   <td>2437</td>
   <td>US</td>
  </tr>
</table>

As explained in [Configure Wi-Fi AP and test](#Configure-Wi-Fi-AP-and-test), 
if `wifi_dfs_5g_ssid` is empty or commented out,
all DFS test cases with STA channel = 5260 are skipped.

## Actionable test results

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

## Prerequisites

*   **Environment.**

    We recommend an RF shielding box or room to run the test.

*   **Wi-Fi Access Point (AP) and network.**

    - The test AP must be a dual-band capable Wi-Fi AP with two SSIDs (one at
    2&nbsp;GHz and one at 5&nbsp;GHz) with support for DFS channels. There are 
    three Wi-Fi channels to be tested: 2437, 5180, and 5260.
      - 5260 is a [DFS channel](https://en.wikipedia.org/wiki/List_of_WLAN_channels).
    - Examples of routers that meet the testing requirements include NETGEAR 
    RAX50 AX5400, NETGEAR RAX120 AX6000, and NETGEAR R8000b AC3200. It's ideal
    to use two APs to support all test cases.
    - The test AP must have the access to google.com. Note that in China, this
    test requires an office VPN network or installing a VPN app in devices.

*   **Test host.**
    
    The test host should have the following libraries installed:
    - python3.12 or later
      - Check your Python 3 version number:

      ```
      python3 --version
      ```

      - If your version is lower than Python 3.12, install the latest version
      following https://wiki.python.org/moin/BeginnersGuide/Download.
    - ADB
      - If you don't already have the `adb` command-line tool, download and
        install it from
        [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools#downloads).
      - Make sure that the installed binary is in the host's `PATH`, so it can
        be run directly with `adb` in the command line.

*   **Target device.**

    The target device must run a userdebug image of the latest Android version,
    for example, Android 14. **This is the device that is being validated.**

*   **Source device.**

    Run the suite and pass the quality bar with one source device
    running a userdebug image of the latest Android version. We recommend a
    model with known good connectivity performance. Some options are:
    - A model that already passed the automated test suite as a target.
    - A flagship model with no known major Bluetooth and Wi-Fi issues.

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


## Test steps

Follow these steps to prepare and execute tests and review test results.

### Prepare the test

Prepare the following materials to be used for the tests.

#### Get the test suite and tools

Download the latest release test binary files from
https://github.com/android/betocq/releases and save them in a local directory:
   - `betocq_x.y.z-py3-none-any.whl` where `x.y.z` stands for the latest release version
   - `cuj_and_test_config.yml`

#### Set up Python virtual environment and install test runner

Create a new local Python virtual environment as follows.

On Linux:
```
python3 -m venv venv
source venv/bin/activate
```

On Windows:
```
python -m venv venv                                                                                                                                                                                               
venv\Scripts\activate
```

If successful, you will see a `(venv)` at the beginning of your command prompt.

Then, install the BeToCQ test runner, substituting in the correct `.whl` file.

On Linux:
```
python3 -m pip install <betocq_x.y.z-py3-none-any.whl>
```

On Windows:
```
python -m pip install <betocq_x.y.z-py3-none-any.whl>
```

#### Configure Wi-Fi AP and test

1. Modify the test config file `cuj_and_test_config.yml` as follows:
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

2. Configure device capabilities for both source and target devices.

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


### Set up results uploader  (first time use only)
Follow instructions in [`results_uploader`](https://github.com/android/mobly-android-partner-tools) to get the test results.

### Run the test
Run the following command to run the test.

```
mobly_runner betocq_test_suite -tb CUJ_name -i -c cuj_and_test_config.yml -u [-- your-test-label]
```

Note that `CUJ_name` is one of the supported CUJ tests listed in `cuj_and_test_config.yml`, e.g., "Quickstart".


### Debugging test failures

If you encounter test failures, you could reference the
[debugging playbook](./doc/debugging_playbook.md) to help analyze them.
