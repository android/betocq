/**
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
**/

package com.google.android.nearby.mobly.snippet.utils;

import static java.util.concurrent.TimeUnit.SECONDS;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.ProxyInfo;
import android.net.Uri;
import android.net.wifi.MloLink;
import android.net.wifi.ScanResult;
import android.net.wifi.SupplicantState;
import android.net.wifi.WifiAvailableChannel;
import android.net.wifi.WifiConfiguration;
import android.net.wifi.WifiEnterpriseConfig;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.text.TextUtils;
import android.util.Base64;
import androidx.annotation.Nullable;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.android.mobly.snippet.Snippet;
import com.google.android.mobly.snippet.bundled.utils.JsonSerializer;
import com.google.android.mobly.snippet.bundled.utils.Utils;
import com.google.android.mobly.snippet.connectivity.common.WifiConstants;
import com.google.android.mobly.snippet.rpc.Rpc;
import com.google.android.mobly.snippet.util.Log;
import com.google.common.base.Ascii;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.lang.reflect.Field;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeoutException;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Snippet to interact with the <a
 * href="https://developer.android.com/reference/android/net/wifi/WifiManager">WifiManager API</a>.
 */
public final class WifiManagerSnippet implements Snippet {

  /* event identifier */
  private static final int TOGGLE_STATE_TIMEOUT_IN_SEC = 30;
  private static final int CONNECT_TIMEOUT_IN_SEC = 90;
  private static final int FORGET_NETWORK_TIMEOUT_IN_SEC = 10;
  private static final int SCAN_TIMEOUT_IN_SEC = 30;

  private final Context context;
  private final WifiManager wifiManager;
  private final JsonSerializer jsonSerializer = new JsonSerializer();

  /** Exception thrown by WifiManagerSnippet. */
  public static class WifiManagerSnippetException extends Exception {
    private static final long serialVersionUID = 1L;

    public WifiManagerSnippetException(String msg, Throwable err) {
      super(msg, err);
    }

    public WifiManagerSnippetException(String msg) {
      super(msg);
    }
  }

  /**
   * Action listener passed to WiFi Manager APIs.
   *
   * <p>With different types of events triggered when executing WiFi Manager APIs, corresponding
   * method will be invoked. The method and its caller leverage latch to achieve synchronized call.
   */
  private static class WifiActionListener implements WifiManager.ActionListener {
    private final CountDownLatch latch;
    private int failureReason = -1;
    private boolean failed = false;

    WifiActionListener(CountDownLatch latch) {
      this.latch = latch;
    }

    @Override
    public void onSuccess() {
      Log.d("WifiActionListener onSuccess callback is triggered.");
      latch.countDown();
    }

    @Override
    public void onFailure(int reason) {
      Log.d("WifiActionListener onFailure callback is triggered: " + reason);
      this.failureReason = reason;
      this.failed = true;
      latch.countDown();
    }

    boolean hasFailed() {
      return failed;
    }

    int getFailureReason() {
      return failureReason;
    }
  }

  /**
   * Broadcast receiver for WiFi scan result.
   *
   * <p>Some Android APIs don't require a callback or listener. If the API will send out a Broadcast
   * message, we can register a Broadcast receiver to monitor the broadcast.
   */
  private static class WifiScanReceiver extends BroadcastReceiver {
    private final CountDownLatch latch;
    private boolean isExtraResultUpdated;

    WifiScanReceiver(CountDownLatch latch) {
      this.latch = latch;
    }

    private boolean isExtraResultsUpdated() {
      return this.isExtraResultUpdated;
    }

    @Override
    public void onReceive(Context ctx, Intent intent) {
      String action = intent.getAction();
      if (action.equals(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION)) {
        this.isExtraResultUpdated =
            intent.getBooleanExtra(WifiManager.EXTRA_RESULTS_UPDATED, false);
        Log.d("WifiScanReceiver scan result: " + this.isExtraResultUpdated);
        ctx.unregisterReceiver(this);
        this.latch.countDown();
      }
    }
  }

  /** Default constructor. */
  public WifiManagerSnippet() {
    context = InstrumentationRegistry.getInstrumentation().getContext();
    wifiManager =
        (WifiManager) context.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
  }

  private static byte[] base64StrToBytes(String input) {
    return Base64.decode(input, Base64.DEFAULT);
  }

  /** Transforms certificate string to {@link X509Certificate}. */
  private static X509Certificate strToX509Cert(String certStr) throws CertificateException {
    byte[] certBytes = base64StrToBytes(certStr);
    InputStream certStream = new ByteArrayInputStream(certBytes);
    CertificateFactory cf = CertificateFactory.getInstance("X509");
    return (X509Certificate) cf.generateCertificate(certStream);
  }

  /**
   * Constructs a {@link WifiEnterpriseConfig} based on {@code jsonConfig}.
   *
   * <p>This function supports many capacities of WiFi enterprise configuration. The generated
   * {@link WifiEnterpriseConfig} will be attached to the {@link WifiConfiguration} which is used to
   * call {@code wifiManager.connect()}.
   *
   * @param jsonConfig WiFi enterprise configuration in JSON format (easier for maintenance in test
   *     scripts)
   * @return a {@link WifiEnterpriseConfig}
   */
  private static WifiEnterpriseConfig genWifiEnterpriseConfig(JSONObject jsonConfig)
      throws Throwable {
    WifiEnterpriseConfig eConfig = new WifiEnterpriseConfig();
    String firstAttrKey;

    boolean trustOnFirstUse = jsonConfig.optBoolean("trust_on_first_use", false);
    // The default setting of Trust On First Use is disabled.
    if (trustOnFirstUse) {
      eConfig.enableTrustOnFirstUse(trustOnFirstUse);
      String trustOnFirstUseEnabled = eConfig.isTrustOnFirstUseEnabled() ? "Enabled" : "Disabled";
      Log.v("Trust On First Use is " + trustOnFirstUseEnabled);
    }

    /* iterate over single-use (non-combo) attributes */
    for (String hideAttr : WifiConstants.WIFI_ENT_CONFIG_SINGLE_HIDE_ATTR_ARRAY) {
      firstAttrKey = (String) eConfig.getClass().getField(hideAttr).get(eConfig);
      if (!jsonConfig.has(firstAttrKey)) {
        continue;
      }

      switch (hideAttr) {
        case WifiConstants.WIFI_ENT_CONFIG_HIDE_ATTR_EAP_KEY -> {
          int eap = jsonConfig.getInt(firstAttrKey);
          eConfig.setEapMethod(eap);
        }
        case WifiConstants.WIFI_ENT_CONFIG_HIDE_ATTR_PHASE2_KEY -> {
          int p2Method = jsonConfig.getInt(firstAttrKey);
          eConfig.setPhase2Method(p2Method);
        }
        case WifiConstants.WIFI_ENT_CONFIG_HIDE_ATTR_CA_CERT_KEY -> {
          String certStr = jsonConfig.getString(firstAttrKey);
          Log.v("CA Cert String is " + certStr);
          eConfig.setCaCertificate(strToX509Cert(certStr));
        }
        case WifiConstants.WIFI_ENT_CONFIG_HIDE_ATTR_IDENTITY_KEY -> {
          String identity = jsonConfig.getString(firstAttrKey);
          Log.v("Setting identity to " + identity);
          eConfig.setIdentity(identity);
        }
        case WifiConstants.WIFI_ENT_CONFIG_HIDE_ATTR_PASSWORD_KEY -> {
          String pwd = jsonConfig.getString(firstAttrKey);
          Log.v("Setting password to " + pwd);
          eConfig.setPassword(pwd);
        }
        case WifiConstants.WIFI_ENT_CONFIG_HIDE_ATTR_ALTSUBJECT_MATCH_KEY -> {
          String altSub = jsonConfig.getString(firstAttrKey);
          Log.v("Setting Alt Subject to " + altSub);
          eConfig.setAltSubjectMatch(altSub);
        }
        case WifiConstants.WIFI_ENT_CONFIG_HIDE_ATTR_DOM_SUFFIX_MATCH_KEY -> {
          String domSuffix = jsonConfig.getString(firstAttrKey);
          Log.v("Setting Domain Suffix Match to " + domSuffix);
          eConfig.setDomainSuffixMatch(domSuffix);
        }
        case WifiConstants.WIFI_ENT_CONFIG_HIDE_ATTR_REALM_KEY -> {
          String realm = jsonConfig.getString(firstAttrKey);
          Log.v("Setting Realm to " + realm);
          eConfig.setRealm(realm);
        }
        case WifiConstants.WIFI_ENT_CONFIG_HIDE_ATTR_OCSP_KEY -> {
          int ocsp = jsonConfig.getInt(firstAttrKey);
          Log.v("Setting OCSP to " + ocsp);
          Utils.invokeByReflection(eConfig, "setOcsp", ocsp);
        }
        default ->
            throw new WifiManagerSnippetException(
                "Unsupported WiFi Enterprise config attribute " + hideAttr);
      }
    }

    return eConfig;
  }

  /**
   * Constructs a {@link WifiConfiguration} based on {@code jsonConfig}.
   *
   * <p>This function supports many general capacities of WiFi configuration. The generated {@link
   * WifiConfiguration} can be used for {@code wifiManager.connect()}.
   *
   * @param jsonConfig general WiFi configuration in JSON format
   * @throws JSONException if the config is not valid JSON
   * @throws NoSuchFieldException if {@link WifiConfiguration} is missing an expected field
   * @throws IllegalAccessException if there is a reflection access error
   * @return {@link WifiConfiguration} if a JSON config has been passed, otherwise null
   */
  private WifiConfiguration genWifiConfig(JSONObject jsonConfig)
      throws JSONException, NoSuchFieldException, IllegalAccessException {
    if (jsonConfig == null) {
      return null;
    }
    WifiConfiguration config = new WifiConfiguration();
    String rawSsid = null;
    if (jsonConfig.has("SSID")) {
      rawSsid = jsonConfig.getString("SSID");
    } else if (jsonConfig.has("ssid")) {
      rawSsid = jsonConfig.getString("ssid");
    }

    // The network's SSID can either be quoted UTF-8 string (e.g., "MyNetwork"), or an unquoted
    // string of hex digits (e.g., 01a243f405).
    // See WifiConfiguration#SSID for more details.
    if (rawSsid != null) {
      boolean isHex = jsonConfig.optBoolean("ssid_is_hex", false);
      config.SSID = isHex ? rawSsid : "\"" + rawSsid + "\"";
    }

    if (jsonConfig.has("password")) {
      config.preSharedKey = "\"" + jsonConfig.getString("password") + "\"";
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        /* Check if new security type SAE (WPA3) is present. Default to PSK. */
        if (jsonConfig.has("security")
            && TextUtils.equals(jsonConfig.getString("security"), "SAE")) {
          config.setSecurityParams(WifiConfiguration.SECURITY_TYPE_SAE);
        } else { // Default to PSK if password exists and not explicitly SAE
          config.setSecurityParams(WifiConfiguration.SECURITY_TYPE_PSK);
        }
      } else {
        // Before Q, PSK is implied by preSharedKey. SAE is not supported.
        if (jsonConfig.has("security")
            && TextUtils.equals(jsonConfig.getString("security"), "SAE")) {
          Log.w("SAE security type is not supported before API level 29.");
        }
      }
    } else if (jsonConfig.has("preSharedKey")) {
      config.preSharedKey = jsonConfig.getString("preSharedKey");
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        config.setSecurityParams(WifiConfiguration.SECURITY_TYPE_PSK);
      }
    } else {
      // No password or preSharedKey
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        if (jsonConfig.has("security")
            && TextUtils.equals(jsonConfig.getString("security"), "OWE")) {
          config.setSecurityParams(WifiConfiguration.SECURITY_TYPE_OWE);
        } else {
          config.setSecurityParams(WifiConfiguration.SECURITY_TYPE_OPEN);
        }
      } else {
        // Before Q, OPEN is the default when no keys are provided. OWE is not supported.
        if (jsonConfig.has("security")
            && TextUtils.equals(jsonConfig.getString("security"), "OWE")) {
          Log.w("OWE security type is not supported before API level 29.");
        }
      }
    }
    if (jsonConfig.has("BSSID")) {
      config.BSSID = jsonConfig.getString("BSSID");
    }
    if (jsonConfig.has("hiddenSSID")) {
      config.hiddenSSID = jsonConfig.getBoolean("hiddenSSID");
    }
    if (jsonConfig.has("priority")) {
      config.priority = jsonConfig.getInt("priority");
    }
    if (jsonConfig.has("apBand")) {
      Field apBandField = config.getClass().getDeclaredField("apBand");
      apBandField.setAccessible(true);
      apBandField.setInt(config, jsonConfig.getInt("apBand"));
    }
    if (jsonConfig.has("wepKeys")) {
      /* Looks like we only support static WEP. */
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        config.setSecurityParams(WifiConfiguration.SECURITY_TYPE_WEP);
      }
      JSONArray keys = jsonConfig.getJSONArray("wepKeys");
      String[] wepKeys = new String[keys.length()];
      for (int i = 0; i < keys.length(); i++) {
        wepKeys[i] = keys.getString(i);
      }
      config.wepKeys = wepKeys;
    }
    if (jsonConfig.has("wepTxKeyIndex")) {
      config.wepTxKeyIndex = jsonConfig.getInt("wepTxKeyIndex");
    }
    if (jsonConfig.has("meteredOverride")) {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        config.meteredOverride = jsonConfig.getInt("meteredOverride");
      } else {
        Log.w("meteredOverride is not supported before API level 28.");
      }
    }
    if (jsonConfig.has("macRand")) {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        config.macRandomizationSetting = jsonConfig.getInt("macRand");
      } else {
        Log.w("macRandomizationSetting is not supported before API level 29.");
      }
    }
    if (jsonConfig.has("carrierId")) {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        config.carrierId = jsonConfig.getInt("carrierId");
      } else {
        Log.w("carrierId is not supported before API level 30.");
      }
    }
    if (jsonConfig.has("pacProxy")) {
      Uri pacUri = Uri.parse(jsonConfig.getString("pacProxy"));
      config.setHttpProxy(ProxyInfo.buildPacProxy(pacUri));
    }
    return config;
  }

  /**
   * Construct {@link WifiConfiguration} along with enterprise config based on {@code jsonConfig}.
   *
   * <p>This function generates a {@link WifiConfiguration} with a {@link WifiEnterpriseConfig}
   * attached. The generated instance can be used for {@code wifiManager.connect()}.
   *
   * @param jsonConfig general WiFi configuration in JSON format
   * @return {@link WifiConfiguration}
   */
  private WifiConfiguration genWifiConfigWithEnterpriseConfig(JSONObject jsonConfig)
      throws Throwable {
    if (jsonConfig == null) {
      return null;
    }
    WifiConfiguration config = new WifiConfiguration();
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
      config.setSecurityParams(WifiConfiguration.SECURITY_TYPE_EAP);
      if (jsonConfig.has("security")
          && TextUtils.equals(jsonConfig.getString("security"), "SUITE_B_192")) {
        config.setSecurityParams(WifiConfiguration.SECURITY_TYPE_EAP_SUITE_B);
      }
    } else {
      // EAP is implicitly handled by setting enterpriseConfig before Q.
      if (jsonConfig.has("security")
          && TextUtils.equals(jsonConfig.getString("security"), "SUITE_B_192")) {
        Log.w("SUITE_B_192 is not supported before API level 29.");
      }
    }

    if (jsonConfig.has("SSID")) {
      config.SSID = "\"" + jsonConfig.getString("SSID") + "\"";
    } else if (jsonConfig.has("ssid")) {
      config.SSID = "\"" + jsonConfig.getString("ssid") + "\"";
    }
    if (jsonConfig.has("FQDN")) {
      config.FQDN = jsonConfig.getString("FQDN");
    }
    if (jsonConfig.has("providerFriendlyName")) {
      config.providerFriendlyName = jsonConfig.getString("providerFriendlyName");
    }
    if (jsonConfig.has("roamingConsortiumIds")) {
      JSONArray ids = jsonConfig.getJSONArray("roamingConsortiumIds");
      long[] rIds = new long[ids.length()];
      for (int i = 0; i < ids.length(); i++) {
        rIds[i] = ids.getLong(i);
      }
      config.roamingConsortiumIds = rIds;
    }
    if (jsonConfig.has("carrierId")) {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        config.carrierId = jsonConfig.getInt("carrierId");
      } else {
        Log.w("carrierId is not supported before API level 30.");
      }
    }
    config.enterpriseConfig = genWifiEnterpriseConfig(jsonConfig);
    return config;
  }

  /**
   * Enables/disables auto join for a network.
   *
   * @param netId id of the target network
   * @param enableAutojoin {@code true} to enable, {@code false} to disable it
   */
  @Rpc(description = "Enable/disable auto join for a network.")
  public void wifiEnableAutojoin(int netId, boolean enableAutojoin) {
    ShellPermissionManager.executeWithShellPermission(
        () -> wifiManager.allowAutojoin(netId, enableAutojoin));
  }

  /** Enable Wi-Fi verbose logging. */
  @Rpc(description = "Enable Wi-Fi verbose logging.")
  public void wifiSetVerboseLogging(int level) {
    ShellPermissionManager.executeWithShellPermission(
        () -> wifiManager.setVerboseLoggingEnabled(level > 0));
  }

  /**
   * Checks if the chipset supports the 6GHz frequency band.
   *
   * @return {@code true} if the chipset supports the 6GHz frequency band
   */
  @Rpc(description = "Check if the chipset supports the 6GHz frequency band.")
  public boolean wifiIs6GHzBandSupported() {
    return wifiManager.is6GHzBandSupported();
  }

  /**
   * Checks if the chipset supports the 5GHz frequency band.
   *
   * @return {@code true} if the chipset supports the 5GHz frequency band
   */
  @Rpc(description = "Check if the chipset supports the 5GHz frequency band.")
  public boolean wifiIs5GHzBandSupported() {
    return wifiManager.is5GHzBandSupported();
  }

  /**
   * Checks if the chipset supports the 2GHz frequency band.
   *
   * @return {@code true} if the chipset supports the 2GHz frequency band
   */
  @Rpc(description = "Check if the chipset supports the 2GHz frequency band.")
  public boolean wifiIs2GHzBandSupported() {
    return wifiManager.is24GHzBandSupported();
  }

  /** Get all configured WiFi networks. */
  @Rpc(description = "Get all configured WiFi networks.")
  public List<JSONObject> wifiGetConfiguredNetworks() throws JSONException {
    List<JSONObject> networks = new ArrayList<>();
    for (WifiConfiguration config : getConfiguredNetworks()) {
      networks.add(jsonSerializer.toJson(config));
    }
    return networks;
  }

  /**
   * Removes a configured WiFi network, and returns {@code true} on success.
   *
   * @param netId network id
   * @return {@code true} if the operation succeeded
   */
  @Rpc(description = "Remove a configured network.")
  public boolean wifiRemoveNetwork(int netId) {
    return ShellPermissionManager.executeWithShellPermission(
        () -> wifiManager.removeNetwork(netId));
  }

  /**
   * Connects to the network with the given configuration.
   *
   * @param jsonConfig {@link JSONObject} of WiFi connection parameters.
   */
  @Rpc(description = "Connect to the network with the given configuration.")
  public void wifiConnect(JSONObject jsonConfig) throws Throwable {
    Log.d("Got network config: " + jsonConfig);
    WifiConfiguration wifiConfig;
    CountDownLatch latch = new CountDownLatch(1);

    // Check if this is 802.1x or 802.11x config.
    if (jsonConfig.has(WifiConstants.WIFI_ENT_CONFIG_HIDE_ATTR_OCSP_VALUE)) {
      wifiConfig = genWifiConfigWithEnterpriseConfig(jsonConfig);
    } else {
      wifiConfig = genWifiConfig(jsonConfig);
    }
    if (wifiConfig == null) {
      throw new WifiManagerSnippetException(
          "Failed to generate WifiConfiguration from: " + jsonConfig);
    }

    WifiInfo connectionInfo = getConnectionInfo();
    if (connectionInfo.getNetworkId() != -1
        && connectionInfo.getSSID().equals(wifiConfig.SSID)
        && connectionInfo.getSupplicantState().equals(SupplicantState.COMPLETED)) {
      String connectionBssid = connectionInfo.getBSSID();
      if (wifiConfig.BSSID == null
          || (connectionBssid != null
              && wifiConfig
                  .BSSID
                  .toLowerCase(Locale.getDefault())
                  .equals(connectionBssid.toLowerCase(Locale.getDefault())))) {
        Log.d(
            "Network "
                + connectionInfo.getSSID()
                + " is already connected. ConnectionInfo: "
                + connectionInfo);
        return;
      }
    }

    WifiActionListener listener = new WifiActionListener(latch);

    ShellPermissionManager.executeWithShellPermission(
        () -> {
          wifiManager.connect(wifiConfig, listener);
          try {
            if (!latch.await(50, SECONDS)) {
              throw new TimeoutException("WiFi connect call timed out.");
            }
          } catch (Exception e) {
            if (e instanceof InterruptedException) {
              Thread.currentThread().interrupt();
            }
            throw new RuntimeException("WiFi connection failed.", e);
          }
          if (listener.hasFailed()) {
            throw new RuntimeException(
                "WifiActionListener onFailure callback is triggered: "
                    + listener.getFailureReason());
          }
        });

    String skipVerificationAttr = "skip_verification";
    if (jsonConfig.has(skipVerificationAttr)) {
      if (jsonConfig.getBoolean(skipVerificationAttr)) {
        Log.d("Skip verification of WifiInfo.");
        return;
      }
    }

    if (!Utils.waitUntil(
        () -> {
          WifiInfo currentConnectionInfo = getConnectionInfo();
          boolean verifySsid =
              jsonConfig.optBoolean("ssid_is_hex", false)
                  // If the SSID can be decoded as UTF-8, WifiInfo#getSSID() will return a quoted
                  // UTF-8 string. Otherwise, return an unquoted string of hex digits in lowercase.
                  // See WifiInfo#getSSID() and WifiSsid#toString() for more details.
                  ? Ascii.equalsIgnoreCase(currentConnectionInfo.getSSID(), wifiConfig.SSID)
                  : Objects.equals(currentConnectionInfo.getSSID(), wifiConfig.SSID);
          return currentConnectionInfo.getNetworkId() != -1
              && verifySsid
              && currentConnectionInfo.getSupplicantState().equals(SupplicantState.COMPLETED);
        },
        CONNECT_TIMEOUT_IN_SEC)) {
      throw new WifiManagerSnippetException(
          "Failed to connect to '"
              + jsonConfig
              + "', timeout! Current connection: '"
              + getConnectionInfo().getSSID()
              + "'");
    }
  }

  /**
   * Connects to a Wi-Fi network by simply giving a SSID and a password.
   *
   * @param ssid the SSID of the network to connect to
   * @param password the password of the network to connect to
   */
  @Rpc(description = "Connect to a Wi-Fi network by simply giving a SSID and a password.")
  public void wifiConnectSimple(String ssid, String password) throws Throwable {
    wifiConnectSimpleWithHidden(ssid, password, /* hidden= */ false);
  }

  /** Connects to a Wi-Fi network by simply giving a SSID and a password. */
  @Rpc(description = "Connect to a Wi-Fi network by simply giving a SSID and a password.")
  public void wifiConnectSimpleWithHidden(String ssid, String password, boolean hidden)
      throws Throwable {
    JSONObject jsonConfig = new JSONObject();
    jsonConfig.put("SSID", ssid);
    if (password != null) {
      jsonConfig.put("password", password);
    }
    jsonConfig.put("hiddenSSID", hidden);
    wifiConnect(jsonConfig);
  }

  /**
   * Checks if the device is connected to the given SSID.
   *
   * @param ssid the SSID of the network to check
   * @return {@code true} if the device is connected to the given SSID
   */
  @Rpc(description = "Check if the device is connected to the given SSID.")
  public boolean wifiIsConnected(String ssid) {
    SupplicantState state = wifiGetSupplicantState();
    String connectedSsid = wifiGetConnectionSsid();
    // WifiInfo#getSSID() returns a quoted string for SSIDs that can be decoded as UTF-8.
    if (connectedSsid.startsWith("\"") && connectedSsid.endsWith("\"")) {
      connectedSsid = connectedSsid.substring(1, connectedSsid.length() - 1);
    }

    String unquotedSsid = ssid;
    if (unquotedSsid.startsWith("\"") && unquotedSsid.endsWith("\"")) {
      unquotedSsid = unquotedSsid.substring(1, unquotedSsid.length() - 1);
    }
    return (state == SupplicantState.COMPLETED) && connectedSsid.equals(unquotedSsid);
  }

  /**
   * Toggles Wi-Fi scan always available when location service is on.
   *
   * @param enabled {@code true} to enable, {@code false} to disable
   */
  @Rpc(description = "Toggle Wi-Fi scan always available when location service is on.")
  public void wifiToggleScanAlwaysAvailable(boolean enabled) {
    ShellPermissionManager.executeWithShellPermission(
        () -> wifiManager.setScanAlwaysAvailable(enabled));
  }

  private boolean latchWrapper(CountDownLatch latch, Runnable runnable, int timeoutSec) {
    runnable.run();
    try {
      Log.d("Latch wrapper waits till operation is done.");
      return latch.await(timeoutSec, SECONDS);
    } catch (InterruptedException e) {
      Log.e("Latch wrapper gets interrupted.", e);
      return false;
    }
  }

  /**
   * Forgets a WiFi network, and returns {@code true} on success.
   *
   * @param networkId the id of the network
   * @return {@code true} if the operation succeeded
   */
  @Rpc(description = "Forget a WiFi network.")
  public boolean wifiForgetNetwork(int networkId) {
    CountDownLatch latch = new CountDownLatch(1);
    WifiActionListener listener = new WifiActionListener(latch);

    Log.d("Forget a WiFi network with ID " + networkId + ".");
    return ShellPermissionManager.executeWithShellPermission(
        () ->
            latchWrapper(
                latch,
                () -> wifiManager.forget(networkId, listener),
                FORGET_NETWORK_TIMEOUT_IN_SEC));
  }

  /**
   * Starts a scan for WiFi access points.
   *
   * @return {@code true} if the operation succeeded
   */
  @Rpc(description = "Start a scan for WiFi access points.")
  public boolean wifiStartScan() {
    CountDownLatch latch = new CountDownLatch(1);
    IntentFilter filter = new IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION);
    WifiScanReceiver wifiScanReceiver = new WifiScanReceiver(latch);
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      context.registerReceiver(wifiScanReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
    } else {
      context.registerReceiver(wifiScanReceiver, filter);
    }

    Log.d("Start WiFi scan.");
    boolean isStartSucceeded = false;
    try {
      isStartSucceeded =
          ShellPermissionManager.executeWithShellPermission(
              () -> latchWrapper(latch, wifiManager::startScan, SCAN_TIMEOUT_IN_SEC));
    } finally {
      // Always unregister the receiver, even if the latch times out.
      try {
        context.unregisterReceiver(wifiScanReceiver);
      } catch (IllegalArgumentException e) {
        // This can happen if the receiver was already unregistered within onReceive.
        Log.d("WifiScanReceiver was already unregistered.", e);
      }
    }

    if (!isStartSucceeded) {
      Log.d("Start failed.");
      return false;
    }
    return wifiScanReceiver.isExtraResultsUpdated();
  }

  /**
   * Returns the WiFi scan results from the most recent scan in JSON format.
   *
   * @return {@link List} of scan results in JSON format
   */
  @Rpc(description = "Get the WiFi scan results from the most recent scan in JSON format.")
  public JSONArray wifiGetScanResults() throws JSONException {
    JSONArray results = new JSONArray();
    for (ScanResult result :
        ShellPermissionManager.executeWithShellPermission(wifiManager::getScanResults)) {
      results.put(jsonSerializer.toJson(result));
    }
    return results;
  }

  /**
   * Starts scan, and return results in JSON format when the scan is done.
   *
   * @return {@link List} of scan results in JSON format
   */
  @Rpc(description = "Start scan, wait for scan to complete, and return results in JSON format.")
  @Nullable
  public JSONArray wifiScanAndGetResults() throws JSONException {
    if (wifiStartScan()) {
      return wifiGetScanResults();
    } else {
      return null;
    }
  }

  /**
   * Toggles WiFi on and off.
   *
   * @param enabled {@code true} to turn on, {@code false} to turn off
   */
  @Rpc(description = "Toggle WiFi on and off.")
  public void wifiToggleState(boolean enabled) throws WifiManagerSnippetException {
    int expectedWifiState =
        enabled ? WifiManager.WIFI_STATE_ENABLED : WifiManager.WIFI_STATE_DISABLED;

    if (wifiManager.getWifiState() == expectedWifiState) {
      return;
    }

    int wifiStateNeededToWait =
        enabled ? WifiManager.WIFI_STATE_DISABLING : WifiManager.WIFI_STATE_ENABLING;
    if (wifiManager.getWifiState() == wifiStateNeededToWait) {
      if (!Utils.waitUntil(
          () -> wifiManager.getWifiState() == expectedWifiState, TOGGLE_STATE_TIMEOUT_IN_SEC)) {
        Log.e("Wi-Fi failed to stabilize after " + TOGGLE_STATE_TIMEOUT_IN_SEC + "s.");
      }
    }

    if (!ShellPermissionManager.executeWithShellPermission(
        () -> wifiManager.setWifiEnabled(enabled))) {
      throw new WifiManagerSnippetException("Failed to initiate toggling Wi-Fi to " + enabled);
    }
    if (!Utils.waitUntil(
        () -> wifiManager.getWifiState() == expectedWifiState, TOGGLE_STATE_TIMEOUT_IN_SEC)) {
      throw new WifiManagerSnippetException(
          "Failed to toggle Wi-Fi to "
              + enabled
              + " after "
              + TOGGLE_STATE_TIMEOUT_IN_SEC
              + "s timeout");
    }
  }

  /** Turns on Wi-Fi. */
  @Rpc(description = "Turn on Wi-Fi.")
  public void wifiEnable() throws WifiManagerSnippetException {
    wifiToggleState(true);
  }

  /** Turns off Wi-Fi. */
  @Rpc(description = "Turn off Wi-Fi.")
  public void wifiDisable() throws WifiManagerSnippetException {
    wifiToggleState(false);
  }

  /** Checks if the device supports Wi-Fi Direct(p2p). */
  @Rpc(description = "Check if the device supports Wi-Fi Direct(p2p).")
  public boolean wifiIsP2pSupported() {
    return wifiManager.isP2pSupported();
  }

  /**
   * Checks if WiFi is in a given state, and returns {@code true} on success.
   *
   * @param wifiState state
   * @return {@code true} if the operation succeeded
   */
  @Rpc(description = "Check if WiFi is in a given state.")
  public boolean wifiCheckState(int wifiState) {
    return wifiManager.getWifiState() == wifiState;
  }

  /** Checks if WiFi is enabled. */
  @Rpc(description = "Check if WiFi is enabled.")
  public boolean wifiIsEnabled() {
    return wifiManager.getWifiState() == WifiManager.WIFI_STATE_ENABLED;
  }

  /** Get the country code. */
  @Rpc(description = "Get the country code.")
  public String wifiGetCountryCode() {
    return ShellPermissionManager.executeWithShellPermission(wifiManager::getCountryCode);
  }

  private WifiInfo getConnectionInfo() {
    return ShellPermissionManager.executeWithShellPermission(wifiManager::getConnectionInfo);
  }

  private List<WifiConfiguration> getConfiguredNetworks() {
    return ShellPermissionManager.executeWithShellPermission(
        () -> wifiManager.getConfiguredNetworks());
  }

  @Rpc(description = "Return the associated MLO Links for Wi-Fi 7 access points.")
  public List<MloLink> getAssociatedMloLinks() {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
      return ShellPermissionManager.executeWithShellPermission(
          () -> getConnectionInfo().getAssociatedMloLinks());
    } else {
      Log.w("getAssociatedMloLinks requires API level 34, but current is " + Build.VERSION.SDK_INT);
      return new ArrayList<>();
    }
  }

  @Rpc(description = "Return the supplicant state.")
  public SupplicantState wifiGetSupplicantState() {
    return getConnectionInfo().getSupplicantState();
  }

  /**
   * Gets the active WiFi connection data in JSON format.
   *
   * @return WiFi connection data in JSON format
   */
  @Rpc(description = "Get the information about the active Wi-Fi connection in JSON format.")
  public JSONObject wifiGetConnectionInfo() throws JSONException {
    return jsonSerializer.toJson(getConnectionInfo());
  }

  /**
   * Returns the WiFi connection standard.
   *
   * @return WiFi connection standard
   */
  @Rpc(description = "Get the WiFi connection standard, e.g. 802.11N, 802.11AC etc.")
  public Integer wifiGetConnectionStandard() {
    return getConnectionInfo().getWifiStandard();
  }

  /**
   * Returns the BSSID of the currently active access point.
   *
   * @return a String representing BSSID, an empty String if there is no active access point
   */
  @Rpc(description = "Returns the BSSID of the currently active access point.")
  public String wifiGetConnectionBssid() {
    return getConnectionInfo().getBSSID();
  }

  /**
   * Returns the SSID of the currently active access point.
   *
   * @return a String representing SSID, an empty String if there is no active access point
   */
  @Rpc(description = "Returns the SSID of the currently active access point.")
  public String wifiGetConnectionSsid() {
    return getConnectionInfo().getSSID();
  }

  /**
   * Returns the RSSI of the current active connection.
   *
   * @return Integer RSSI value of current Wi-Fi connection. It returns -127 when no connection.
   */
  @Rpc(description = "Returns the RSSI of the current active connection.")
  public Integer wifiGetConnectionRssi() {
    return getConnectionInfo().getRssi();
  }

  /**
   * Returns the frequency of the currently active access point.
   *
   * @return Integer frequency (MHz) value of current Wi-Fi connection. It returns -1 when no
   *     connection.
   */
  @Rpc(description = "Returns the frequency of the currently active access point.")
  public int wifiGetConnectionFrequency() {
    return getConnectionInfo().getFrequency();
  }

  /**
   * Returns the MAC address of the currently active access point.
   *
   * @return a String representing MAC address, an empty String if there is no active access point
   */
  @Rpc(description = "Returns the MAC address of the currently active access point.")
  public String wifiGetConnectionMacAddress() {
    return getConnectionInfo().getMacAddress();
  }

  /**
   * Clears all configured networks.
   *
   * <p>This will only work if all configured networks were added through WifiManagerSnippet.
   */
  @Rpc(
      description =
          "Clear all configured networks. This will only work if all configured "
              + "networks were added through WifiManagerSnippet.")
  public void wifiClearConfiguredNetworks() throws WifiManagerSnippetException {
    List<WifiConfiguration> unremovedConfigs = getConfiguredNetworks();
    List<WifiConfiguration> failedConfigs = new ArrayList<>();
    if (unremovedConfigs == null) {
      throw new WifiManagerSnippetException(
          "Failed to get a list of configured networks. Is WiFi disabled?");
    }
    for (WifiConfiguration config : unremovedConfigs) {
      if (!ShellPermissionManager.executeWithShellPermission(
          () -> wifiManager.removeNetwork(config.networkId))) {
        failedConfigs.add(config);
      }
    }

    // If removeNetwork is called on a network with both an open and OWE config, it will remove
    // both. The subsequent call on the same network will fail. The clear operation may succeed
    // even if failures appear in the log below.
    if (!failedConfigs.isEmpty()) {
      Log.e("Encountered error while removing networks: " + failedConfigs);
    }

    // Re-check configured configs list to ensure that it is cleared
    unremovedConfigs = getConfiguredNetworks();
    if (!unremovedConfigs.isEmpty()) {
      throw new WifiManagerSnippetException("Failed to remove networks: " + unremovedConfigs);
    }
  }

  /** Checks if device supports TDLS. */
  @Rpc(description = "Check if TDLS is supported.")
  public boolean wifiIsTdlsSupported() {
    return wifiManager.isTdlsSupported();
  }

  /** Checks if the device supports the specified WiFi standard. */
  @Rpc(description = "Check if the device supports the specified WiFi standard.")
  public boolean isWifiStandardSupported(int standard) {
    return wifiManager.isWifiStandardSupported(standard);
  }

  /**
   * Connects/Enables TDLS connection using peer MAC address. True to enable, False to disable
   *
   * @param remoteMacAddress Peer MAC address
   * @param enable {@code true} to setup a connection to the given peer MAC address network, {@code
   *     false} to tear down TDLS
   */
  @Rpc(description = "Set TDLS connection enabled/disabled with peer MAC address.")
  public void setTdlsEnabledWithMacAddress(String remoteMacAddress, boolean enable) {
    wifiManager.setTdlsEnabledWithMacAddress(remoteMacAddress, enable);
  }

  /** Get the usable channels. */
  @Rpc(description = "Get the usable channels for the specified band and mode.")
  public List<WifiAvailableChannel> getUsableChannels(int band, int mode) {
    return ShellPermissionManager.executeWithShellPermission(
        () -> wifiManager.getUsableChannels(band, mode));
  }

  @Override
  public void shutdown() {}
}
