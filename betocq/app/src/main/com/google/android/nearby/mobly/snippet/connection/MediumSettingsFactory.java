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

package com.google.android.nearby.mobly.snippet.connection;

import static com.google.android.gms.nearby.connection.Medium.BLE;
import static com.google.android.gms.nearby.connection.Medium.BLE_L2CAP;
import static com.google.android.gms.nearby.connection.Medium.BLUETOOTH;
import static com.google.android.gms.nearby.connection.Medium.WEB_RTC;
import static com.google.android.gms.nearby.connection.Medium.WIFI_AWARE;
import static com.google.android.gms.nearby.connection.Medium.WIFI_DIRECT;
import static com.google.android.gms.nearby.connection.Medium.WIFI_HOTSPOT;
import static com.google.android.gms.nearby.connection.Medium.WIFI_LAN;

import com.google.android.gms.nearby.connection.AdvertisingOptions;
import com.google.android.gms.nearby.connection.ConnectionOptions;
import com.google.android.gms.nearby.connection.ConnectionType;
import com.google.android.gms.nearby.connection.DiscoveryOptions;
import com.google.android.gms.nearby.connection.Strategy;
import java.util.stream.IntStream;

/** A factory to create advertising/discovery/connection medium options for Nearby connections. */
public final class MediumSettingsFactory {
  private static final int AUTO = 0;

  // LINT.IfChange
  private static final int MEDIUM_BT_ONLY = 1;
  private static final int MEDIUM_BLE_ONLY = 2;
  private static final int MEDIUM_WIFILAN_ONLY = 3;
  private static final int MEDIUM_WIFIAWARE_ONLY = 4;
  private static final int MEDIUM_UPGRADE_TO_WEBRTC = 5;
  private static final int MEDIUM_UPGRADE_TO_WIFIHOTSPOT = 6;
  private static final int MEDIUM_UPGRADE_TO_WIFIDIRECT = 7;
  private static final int MEDIUM_BLE_L2CAP_ONLY = 8;
  private static final int MEDIUM_UPGRADE_TO_ALL_WIFI = 9;
  // LINT.ThenChange(//depot/google3/wireless/android/platform/testing/bettertogether/betocq/nc_constants.py)

  private static final int MEDIUM_UPGRADE_TYPE_DISRUPTIVE = 1;
  private static final int MEDIUM_UPGRADE_TYPE_NON_DISRUPTIVE = 2;

  private static final Strategy STRATEGY = Strategy.P2P_POINT_TO_POINT;

  public static AdvertisingOptions getAdvertisingOptions(int advertisingMedium, int upgradeMedium) {
    boolean autoUpgradeBandwidth = false;
    boolean enforceTopologyConstraints = true;
    boolean lowPower = false;
    IntStream advertisingMediums = IntStream.empty();
    IntStream upgradeMediums = IntStream.empty();

    AdvertisingOptions.Builder builder = new AdvertisingOptions.Builder().setStrategy(STRATEGY);

    advertisingMediums =
        switch (advertisingMedium) {
          case AUTO -> null;
          case MEDIUM_BT_ONLY -> IntStream.of(BLUETOOTH);
          case MEDIUM_BLE_ONLY, MEDIUM_BLE_L2CAP_ONLY -> IntStream.of(BLE);
          case MEDIUM_WIFILAN_ONLY -> IntStream.of(WIFI_LAN);
          case MEDIUM_WIFIAWARE_ONLY -> IntStream.of(BLE, WIFI_AWARE);
          case MEDIUM_UPGRADE_TO_WEBRTC -> IntStream.of(BLE, WEB_RTC);
          case MEDIUM_UPGRADE_TO_WIFIHOTSPOT -> IntStream.of(BLE, WIFI_HOTSPOT);
          case MEDIUM_UPGRADE_TO_WIFIDIRECT -> IntStream.of(BLE, WIFI_DIRECT);
          case MEDIUM_UPGRADE_TO_ALL_WIFI ->
              IntStream.of(BLE, WIFI_DIRECT, WIFI_HOTSPOT, WIFI_LAN, WIFI_AWARE);
          default ->
              throw new IllegalArgumentException(
                  String.format("Unsupported advertising medium: %d", advertisingMedium));
        };

    switch (upgradeMedium) {
      case AUTO -> {
        autoUpgradeBandwidth = true;
        upgradeMediums = null;
      }
      case MEDIUM_BT_ONLY -> upgradeMediums = IntStream.of(BLUETOOTH);
      case MEDIUM_BLE_ONLY, MEDIUM_BLE_L2CAP_ONLY -> {
        lowPower = true;
        upgradeMediums = IntStream.of(BLE);
      }
      case MEDIUM_WIFILAN_ONLY -> {
        autoUpgradeBandwidth = true;
        upgradeMediums = IntStream.of(WIFI_LAN);
      }
      case MEDIUM_WIFIAWARE_ONLY -> {
        autoUpgradeBandwidth = true;
        upgradeMediums = IntStream.of(WIFI_AWARE, BLE_L2CAP, BLUETOOTH, BLE);
      }
      case MEDIUM_UPGRADE_TO_WEBRTC -> {
        autoUpgradeBandwidth = true;
        upgradeMediums = IntStream.of(WEB_RTC, BLE_L2CAP, BLUETOOTH, BLE);
      }
      case MEDIUM_UPGRADE_TO_WIFIHOTSPOT -> {
        autoUpgradeBandwidth = true;
        upgradeMediums = IntStream.of(WIFI_HOTSPOT, BLE_L2CAP, BLUETOOTH, BLE);
      }
      case MEDIUM_UPGRADE_TO_WIFIDIRECT -> {
        autoUpgradeBandwidth = true;
        upgradeMediums = IntStream.of(WIFI_DIRECT, BLE_L2CAP, BLUETOOTH, BLE);
      }
      case MEDIUM_UPGRADE_TO_ALL_WIFI -> {
        autoUpgradeBandwidth = true;
        upgradeMediums = IntStream.of(WIFI_DIRECT, WIFI_AWARE, WIFI_HOTSPOT, WIFI_LAN);
      }
      default ->
          throw new IllegalArgumentException(
              String.format("Unsupported upgrade medium: %d", upgradeMedium));
    }

    builder
        .setAutoUpgradeBandwidth(autoUpgradeBandwidth)
        .setEnforceTopologyConstraints(enforceTopologyConstraints)
        .setLowPower(lowPower);

    if (advertisingMediums != null) {
      builder.setAdvertisingMediums(advertisingMediums.toArray());
    }

    if (upgradeMediums != null) {
      builder.setUpgradeMediums(upgradeMediums.toArray());
    }

    return builder.build();
  }

  public static DiscoveryOptions getDiscoveryMediumOptions(int discoveryMedium) {
    boolean forwardUnrecognizedBluetoothDevices = false;
    boolean lowPower = false;
    IntStream discoveryMediums = IntStream.empty();

    DiscoveryOptions.Builder builder = new DiscoveryOptions.Builder().setStrategy(STRATEGY);

    switch (discoveryMedium) {
      case AUTO -> {}
      case MEDIUM_BT_ONLY -> discoveryMediums = IntStream.of(BLUETOOTH);
      case MEDIUM_BLE_ONLY, MEDIUM_BLE_L2CAP_ONLY -> discoveryMediums = IntStream.of(BLE);
      case MEDIUM_WIFILAN_ONLY -> discoveryMediums = IntStream.of(WIFI_LAN);
      case MEDIUM_WIFIAWARE_ONLY -> discoveryMediums = IntStream.of(BLE, WIFI_AWARE);
      case MEDIUM_UPGRADE_TO_WEBRTC, MEDIUM_UPGRADE_TO_WIFIHOTSPOT, MEDIUM_UPGRADE_TO_WIFIDIRECT ->
          discoveryMediums = IntStream.of(BLE);
      case MEDIUM_UPGRADE_TO_ALL_WIFI -> discoveryMediums = IntStream.of(BLE, WIFI_LAN, WIFI_AWARE);
      default -> {
        return builder.build();
      }
    }

    builder
        .setForwardUnrecognizedBluetoothDevices(forwardUnrecognizedBluetoothDevices)
        .setLowPower(lowPower);

    if (discoveryMedium != AUTO) {
      builder.setDiscoveryMediums(discoveryMediums.toArray());
    }

    return builder.build();
  }

  public static ConnectionOptions getConnectionMediumOptions(
      int connectionMedium,
      int upgradeMedium,
      int mediumUpgradeType,
      int keepAliveTimeoutMillis,
      int keepAliveIntervalMillis) {
    IntStream connectionMediums = IntStream.empty();
    IntStream upgradeMediums = IntStream.empty();

    ConnectionOptions.Builder builder = new ConnectionOptions.Builder().setStrategy(STRATEGY);

    if (mediumUpgradeType == MEDIUM_UPGRADE_TYPE_DISRUPTIVE) {
      builder.setConnectionType(ConnectionType.DISRUPTIVE);
    } else if (mediumUpgradeType == MEDIUM_UPGRADE_TYPE_NON_DISRUPTIVE) {
      builder.setConnectionType(ConnectionType.NON_DISRUPTIVE);
    }

    if (keepAliveTimeoutMillis != 0) {
      builder.setKeepAliveTimeoutMillis(keepAliveTimeoutMillis);
    }

    if (keepAliveIntervalMillis != 0) {
      builder.setKeepAliveIntervalMillis(keepAliveIntervalMillis);
    }

    connectionMediums =
        switch (connectionMedium) {
          case AUTO -> null;
          case MEDIUM_BT_ONLY -> IntStream.of(BLUETOOTH);
          case MEDIUM_BLE_ONLY -> IntStream.of(BLE);
          case MEDIUM_BLE_L2CAP_ONLY -> IntStream.of(BLE_L2CAP);
          case MEDIUM_WIFILAN_ONLY -> IntStream.of(WIFI_LAN);
          case MEDIUM_WIFIAWARE_ONLY -> IntStream.of(BLUETOOTH, BLE, BLE_L2CAP, WIFI_AWARE);
          case MEDIUM_UPGRADE_TO_WEBRTC -> IntStream.of(BLUETOOTH, BLE, BLE_L2CAP, WEB_RTC);
          case MEDIUM_UPGRADE_TO_WIFIHOTSPOT ->
              IntStream.of(BLUETOOTH, BLE, BLE_L2CAP, WIFI_HOTSPOT);
          case MEDIUM_UPGRADE_TO_WIFIDIRECT -> IntStream.of(BLUETOOTH, BLE, BLE_L2CAP, WIFI_DIRECT);
          case MEDIUM_UPGRADE_TO_ALL_WIFI ->
              IntStream.of(BLUETOOTH, BLE, BLE_L2CAP, WIFI_DIRECT, WIFI_HOTSPOT, WIFI_AWARE);
          default ->
              throw new IllegalArgumentException(
                  String.format("Unsupported connection medium: %d", upgradeMedium));
        };

    if (connectionMediums != null) {
      builder.setConnectionMediums(connectionMediums.toArray());
    }

    upgradeMediums =
        switch (upgradeMedium) {
          case AUTO -> null;
          case MEDIUM_BT_ONLY -> IntStream.of(BLUETOOTH, BLE);
          case MEDIUM_BLE_ONLY, MEDIUM_BLE_L2CAP_ONLY -> IntStream.of(BLE_L2CAP);
          case MEDIUM_WIFILAN_ONLY -> IntStream.of(WIFI_LAN);
          case MEDIUM_WIFIAWARE_ONLY -> IntStream.of(WIFI_AWARE, BLE_L2CAP, BLUETOOTH, BLE);
          case MEDIUM_UPGRADE_TO_WEBRTC -> IntStream.of(WEB_RTC, BLE_L2CAP, BLUETOOTH, BLE);
          case MEDIUM_UPGRADE_TO_WIFIHOTSPOT ->
              IntStream.of(WIFI_HOTSPOT, BLE_L2CAP, BLUETOOTH, BLE);
          case MEDIUM_UPGRADE_TO_WIFIDIRECT -> IntStream.of(WIFI_DIRECT, BLE_L2CAP, BLUETOOTH, BLE);
          case MEDIUM_UPGRADE_TO_ALL_WIFI -> IntStream.of(WIFI_DIRECT, WIFI_HOTSPOT, WIFI_LAN);
          default ->
              throw new IllegalArgumentException(
                  String.format("Unsupported connection medium: %d", upgradeMedium));
        };

    if (upgradeMediums != null) {
      builder.setUpgradeMediums(upgradeMediums.toArray());
    }

    return builder.build();
  }

  private MediumSettingsFactory() {}
}
