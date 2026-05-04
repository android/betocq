# Guideline: How to Add a New Test to BeToCQ

This guide provides step-by-step instructions for adding a new test to the
Better Together Connectivity Quality (BeToCQ) suite, specifically focusing on
the `beto_core` and its snippets.

---

## 1. High-Level Architecture

BeToCQ uses a **Controller/Snippet** architecture:

1.  **Mobly (Python)**: Runs on your workstation (the "Host"). It orchestrates
the test, manages device discovery, and issues commands.
2.  **Android Snippets (Kotlin/Java)**: Small Android APKs installed on the
    devices under test (DUTs). They expose system level APIs as
    **Remote Procedure
    Calls (RPCs)** over ADB.

**The Flow**:
`Python Test` -> `RPC Call` -> `ADB` -> `Snippet APK` ->
`Nearby API` -> `Hardware`

---

## 2. Code Structure Deep Dive

Understanding where files live is crucial:

### Root Directory: `wireless/android/platform/testing/bettertogether/betocq/`

-   [constants.py](https://source.corp.google.com/piper///depot/google3/wireless/android/platform/testing/bettertogether/betocq/constants.py): Common constants for the entire suite (timeouts, medium enums, file sizes).
-   [setup_utils.py](https://source.corp.google.com/piper///depot/google3/wireless/android/platform/testing/bettertogether/betocq/setup_utils.py): Essential tools for loading snippets, setting country codes, and clearing Wi-Fi configs.

### The Snippet: `.../betocq/app/`

-   [BeToCoreSnippet.kt](https://source.corp.google.com/piper///depot/google3/wireless/android/platform/testing/bettertogether/betocq/app/src/main/com/google/android/nearby/mobly/snippet/betocore/BeToCoreSnippet.kt): The main entry point for Beto Core RPCs. Define your `@Rpc` methods here.
-   **Adapters**: BeToCQ supports multiple API implementations (surfaces).
    -   `GmsBeToCoreAdapter.kt`: For GMS Core based Nearby.
    -   `MainlineBeToCoreAdapter.kt`: For Android Mainline module (AOSP) based Nearby.
    -   `OxideBeToCoreAdapter.kt`: For the "Oxide" (next gen) implementation.

### Beto Core Tests: `.../betocq/beto_core/`

-   [bc_constants.py](https://source.corp.google.com/piper///depot/google3/wireless/android/platform/testing/bettertogether/betocq/beto_core/bc_constants.py): Beto-specific constants (APK paths, API surface names).
-   [utils.py](https://source.corp.google.com/piper///depot/google3/wireless/android/platform/testing/bettertogether/betocq/beto_core/utils.py): Helper to load the correct snippet configuration for the test.
-   `function_tests/`: Basic functional validation (e.g. "Can I broadcast?").
-   `performance_tests/`: In-depth quality metrics (e.g. "What is the 50th percentile connection latency?").

---

## 3. The API Surface Pattern

BeToCQ is designed to test different implementations of the same Nearby API
seamlessly.

### Switching Surfaces in Python
In your test's `setup_test` or directly in a test method:

```python
from betocq.beto_core import bc_constants

def setup_test(self):
  # Set the device to use the OXIDE implementation
  self.ad.betocore.setBeToCoreApiSurface(bc_constants.BETO_CORE_API_SURFACE_OXIDE)
```

-   **Cross-Surface Tests**: If a test should run on GMS, Mainline, and Oxide, use a loop or parameterized tests.
-   **Implementation-Specific Tests**: If a test only applies to `GMS`, simply set the surface once in `setup_class` and skip other surfaces.

---

## 4. Snippet Development (Kotlin)

### Synchronous vs. Asynchronous RPCs

-   **@Rpc**: For methods that return immediately or have a clear result (e.g., `stopBroadcast()`).
-   **@AsyncRpc**: For long-running operations that use callbacks (e.g., `startDiscovery()`).

#### Adding an Async Method in Kotlin:
```kotlin
@AsyncRpc(description = "Starts discovery.")
fun startDiscovery(callbackId: String, targetTxPower: Int) {
  // Use the callbackId to create a SnippetEvent to signal results back to Python
  getAdapter().startDiscovery(SnippetEvent(callbackId, "onEndpointFound"), targetTxPower)
}
```

> IMPORTANT:
> The `callbackId: String` parameter is **implicitly added by Mobly** as the
first argument of any `@AsyncRpc` method. You do not need to pass it from your
Python test code; Mobly handles this automatically to track asynchronous events.

### Shared Tests (GMS, Mainline, Oxide)

If your test logic is applicable to multiple API implementations (surfaces), add your `@Rpc` or `@AsyncRpc` methods to the shared [BeToCoreSnippet.kt](https://source.corp.google.com/piper///depot/google3/wireless/android/platform/testing/bettertogether/betocq/app/src/main/com/google/android/nearby/mobly/snippet/betocore/BeToCoreSnippet.kt).

1.  **Define the RPC in `BeToCoreSnippet`**: Call `getAdapter()` to access the underlying interface.
2.  **Add to the Interface**: Update `IBeToCoreAdapter.kt`.
3.  **Implement in Adapters**: Add the specific logic to `GmsBeToCoreAdapter`, `MainlineBeToCoreAdapter`, and `OxideBeToCoreAdapter`.

This allows Python tests to switch implementations dynamically
via `setBeToCoreApiSurface(surface)`.

### Implementation-Specific Tests

If a test only applies to a specific implementation (e.g., testing internal
AOSP-only APIs), use the dedicated snippets:

-   [GmsBeToCoreSnippet.kt](https://source.corp.google.com/piper///depot/google3/wireless/android/platform/testing/bettertogether/betocq/app/src/main/com/google/android/nearby/mobly/snippet/betocore/GmsBeToCoreSnippet.kt)
-   [MainlineBeToCoreSnippet.kt](https://source.corp.google.com/piper///depot/google3/wireless/android/platform/testing/bettertogether/betocq/app/src/main/com/google/android/nearby/mobly/snippet/betocore/MainlineBeToCoreSnippet.kt)
-   [OxideBeToCoreSnippet.kt](https://source.corp.google.com/piper///depot/google3/wireless/android/platform/testing/bettertogether/betocq/app/src/main/com/google/android/nearby/mobly/snippet/betocore/OxideBeToCoreSnippet.kt)

> TIP:
> Prefix implementation-specific RPC methods (e.g., `mainlineStartBroadcast`)
to avoid naming collisions if multiple snippets are loaded simultaneously.

#### Mainline: Calling System APIs with Shell Permissions
Mainline tests often require restricted System APIs.
Use `ShellPermissionManager` to adopt the necessary permissions:

```kotlin
import com.google.android.nearby.mobly.snippet.utils.ShellPermissionManager

@Rpc(description = "Calls a system-only API.")
fun mainlineSystemAction() {
  ShellPermissionManager.executeWithShellPermission {
    // Your restricted System API call goes here
    systemService.restrictedMethod()
  }
}
```
This ensures the snippet has the required privileges to
perform system-level operations.

---

## 5. Test Development (Python)

### Handling Asynchronous Callbacks
When calling an `@AsyncRpc`, Mobly returns a `callback` object that connects to
the **EventCache**.

```python
# In Python
discovery_callback = self.discoverer.betocore.startDiscovery(TX_POWER)

# Wait for the event "onEndpointFound" triggered by the snippet
# If it doesn't arrive within 20s, Mobly raises a TimeoutError
event = discovery_callback.waitAndGet("onEndpointFound", timeout=20)

# Access data passed from the snippet in the event.data dictionary
discovery_info = event.data["my_info"]
```

### Using the BeToCQ Toolbox

#### `setup_utils.py`

-   `setup_utils.load_nearby_snippet(ad, config)`: MUST be called in `setup_class`. It installs the APK and prepares the RPC bridge.
-   `setup_utils.set_country_code(ad, 'US')`: Ensures consistent Wi-Fi channel regulatory behavior.

#### `constants.py`

-   Always prefer using `constants.FIRST_DISCOVERY_TIMEOUT` instead of hardcoding `30`.
-   Use `constants.NearbyMedium` enums for connection requests.

---

## 6. Function vs. Performance Tests

> NOTE:
> **To Be Updated**: we are refactoring to make it generic; but you may refer to
them for your tests, we prefer to have metrics shown in mobly properties for
performance tests.

### Function Tests

-   Inherit from `mobly_base_test.BaseTestClass`.
-   Focus on **Pass/Fail** logic.
-   Fast execution, might be used for presubmit tests.

### Performance Tests

-   Inherit from `PerformanceTestBase`.
-   Run multiple iterations (defined in `constants.py` or `cuj_and_test_config.yml`).
-   Automatically summarize results (latencies, speeds) into Sponge properties.

---

## 7. Build Configuration (Bazel/Blaze)

BeToCQ uses a custom macro `betocq_integration_test` to define test
targets that run in MobileHarness labs, locally, or in virtual environments.

### Defining a New Test Suite in `BUILD`

1.  **Load the rule and devices**:
    ```python
    load(
        "//wireless/android/platform/testing/bettertogether/betocq:betocq_integration_test.bzl",
        "DEFAULT_TIMEOUT",
        "betocq_integration_test",
    )
    load(
        "//wireless/android/platform/testing/bettertogether/betocq:mh_device.bzl",
        "BETO_SOURCE_DEVICE",
        "BETO_TARGET_DEVICE",
        "BETO_WIFI_AP_DEVICE",
    )
    ```

2.  **Add the target**:
    ```python
    betocq_integration_test(
        name = "my_new_test_suite",
        timeout = DEFAULT_TIMEOUT,
        srcs = ["my_new_test_suite.py"],
        mh_devices = [
            BETO_WIFI_AP_DEVICE,
            BETO_SOURCE_DEVICE,
            BETO_TARGET_DEVICE,
        ],
        deps = [
            ":my_test_lib",
            "//wireless/android/platform/testing/bettertogether/betocq/beto_core:beto_core_test_suite_lib",
        ],
    )
    ```

-   **`name`**: Generates multiple targets: `[name]` (Lab), `[name]_local` (Workstation), `[name]_cf` (Cuttlefish).
-   **`mh_devices`**: Specifies the hardware requirements for the MobileHarness lab.
-   **`deps`**: Include your test logic libraries and BeToCQ common utilities.

---

## 8. Execution Guide

### Local Execution (Iterative Development)
```bash
blaze test //wireless/android/platform/testing/bettertogether/betocq/beto_core:beto_core_test_suite_local \
  --notest_loasd \
  --test_output=streamed \
  --nofake_stamp_data \
  --test_arg=--mobly_testbed=LocalDev
```

## 9. Tips for New Members

-   **Check Logcat**: If an RPC fails, the snippet APK might have crashed.
Use `adb logcat | grep MoblySnippet`.
-   **Unrooted Devices**: BeToCQ prefers rooted (`userdebug`) devices for clearing Wi-Fi state and setting flags. If using unrooted, check `setup_utils.allow_unrooted_device`.
-   **Thermal Issues**: Performance tests are sensitive to heat. Ensure devices are cool before running long suites.
