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

import android.os.Bundle;
import androidx.annotation.NonNull;
import com.google.android.gms.nearby.connection.BandwidthInfo;
import com.google.android.gms.nearby.connection.BandwidthInfo.Quality;
import com.google.android.gms.nearby.connection.Device;
import com.google.android.gms.nearby.connection.InternetConnectionResult;
import com.google.android.gms.nearby.connection.v3.ConnectionInfo;
import com.google.android.gms.nearby.connection.v3.ConnectionLifecycleCallback;
import com.google.android.gms.nearby.connection.v3.ConnectionResult;
import com.google.android.gms.nearby.connection.v3.DisconnectReason;
import com.google.android.mobly.snippet.event.EventCache;
import com.google.android.mobly.snippet.event.SnippetEvent;
import com.google.common.android.base.AndroidTicker;
import com.google.common.base.Stopwatch;

/** Reports Nearby Connections' lifecycle events to the test scripts side for V3. */
public class ConnectionLifecycleEventsV3 extends ConnectionLifecycleCallback<Device> {
  private long connectionTimeNs;
  private final String callbackId;
  private final Stopwatch connectionStopwatch;
  private ConnectionResult connectionResult;

  public ConnectionLifecycleEventsV3(String callbackId) {
    super(Device.class);
    this.callbackId = callbackId;
    this.connectionStopwatch = Stopwatch.createUnstarted(AndroidTicker.systemTicker());
    this.connectionStopwatch.start();
  }

  /** Returns the connection result. */
  public ConnectionResult getConnectionResult() {
    return connectionResult;
  }

  @Override
  public void onConnectionInitiated(
      @NonNull Device device, @NonNull ConnectionInfo connectionInfo) {
    connectionTimeNs = connectionStopwatch.elapsed().toNanos();
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onConnectionInitiated");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putLong("connectionTimeNs", connectionTimeNs);

    Bundle connectionData = new Bundle();
    connectionData.putString("endpointId", device.getEndpointId());
    connectionData.putBoolean(
        "isIncomingConnection",
        connectionInfo.getConnectionDirection().equals(ConnectionInfo.Direction.INCOMING));
    eventData.putParcelable("connectionInfo", connectionData);

    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onConnectionResult(@NonNull Device device, @NonNull ConnectionResult result) {
    this.connectionResult = result;
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onConnectionResult");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putInt("statusCode", result.getStatus().getStatusCode());
    eventData.putBoolean("isSuccess", result.getStatus().isSuccess());
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onDisconnected(@NonNull Device device, @DisconnectReason int reason) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onDisconnected");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putInt("disconnectReason", reason);
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onBandwidthChanged(@NonNull Device device, @NonNull BandwidthInfo bandwidthInfo) {
    long upgradeTimeNs = connectionStopwatch.elapsed().toNanos() - connectionTimeNs;
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onBandwidthChanged");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putInt("upgradeStatus", bandwidthInfo.getUpgradeStatus());
    eventData.putInt("bwQuality", bandwidthInfo.getQuality());
    eventData.putBoolean("isHighBwQuality", bandwidthInfo.getQuality() == Quality.HIGH);
    eventData.putInt("medium", bandwidthInfo.getMedium());
    eventData.putLong("upgradeTimeNs", upgradeTimeNs);
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onInternetConnectionChanged(
      @NonNull Device device, @NonNull InternetConnectionResult result) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onInternetConnectionChanged");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putInt("statusCode", result.getStatus());
    eventData.putBoolean(
        "isSuccess", result.getStatus() == InternetConnectionResult.Status.AP_CONNECTION_SUCCESS);
    EventCache.getInstance().postEvent(snippetEvent);
  }
}
