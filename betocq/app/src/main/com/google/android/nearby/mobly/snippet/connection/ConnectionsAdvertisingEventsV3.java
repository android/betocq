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
import androidx.annotation.Nullable;
import com.google.android.gms.nearby.connection.BandwidthInfo;
import com.google.android.gms.nearby.connection.BandwidthInfo.Quality;
import com.google.android.gms.nearby.connection.InternetConnectionResult;
import com.google.android.gms.nearby.connection.v3.AdvertisingCallback;
import com.google.android.gms.nearby.connection.v3.ConnectionInfo;
import com.google.android.gms.nearby.connection.v3.ConnectionResult;
import com.google.android.gms.nearby.connection.v3.DisconnectReason;
import com.google.android.gms.nearby.connection.v3.dct.DctDevice;
import com.google.android.mobly.snippet.event.EventCache;
import com.google.android.mobly.snippet.event.SnippetEvent;
import com.google.common.android.base.AndroidTicker;
import com.google.common.base.Stopwatch;

/** Reports Nearby Connections' advertising events to the test scripts side for V3. */
public class ConnectionsAdvertisingEventsV3 extends AdvertisingCallback<DctDevice> {
  private final String callbackId;
  private final Stopwatch connectionStopwatch;

  public ConnectionsAdvertisingEventsV3(String callbackId) {
    super(DctDevice.class);
    this.callbackId = callbackId;
    this.connectionStopwatch = Stopwatch.createUnstarted(AndroidTicker.systemTicker());
    this.connectionStopwatch.start();
  }

  @Override
  public void onConnectionInitiated(
      @NonNull DctDevice device, @NonNull ConnectionInfo connectionInfo) {
    long connectionTimeNs = connectionStopwatch.elapsed().toNanos();
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onConnectionInitiated");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putLong("connectionTimeNs", connectionTimeNs);

    Bundle connectionData = new Bundle();
    connectionData.putBoolean(
        "isIncomingConnection",
        connectionInfo.getConnectionDirection().equals(ConnectionInfo.Direction.INCOMING));
    eventData.putParcelable("connectionInfo", connectionData);

    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onConnectionResult(@NonNull DctDevice device, @NonNull ConnectionResult result) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onConnectionResult");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putInt("statusCode", result.getStatus().getStatusCode());
    eventData.putBoolean("isSuccess", result.getStatus().isSuccess());
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onDisconnected(@NonNull DctDevice device, @DisconnectReason int reason) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onDisconnected");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putInt("disconnectReason", reason);
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onBandwidthChanged(@NonNull DctDevice device, @NonNull BandwidthInfo bandwidthInfo) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onBandwidthChanged");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putInt("bwQuality", bandwidthInfo.getQuality());
    eventData.putBoolean("isHighBwQuality", bandwidthInfo.getQuality() == Quality.HIGH);
    eventData.putInt("medium", bandwidthInfo.getMedium());
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onInternetConnectionChanged(
      @NonNull DctDevice device, @NonNull InternetConnectionResult result) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onInternetConnectionChanged");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putInt("statusCode", result.getStatus());
    eventData.putBoolean(
        "isSuccess", result.getStatus() == InternetConnectionResult.Status.AP_CONNECTION_SUCCESS);
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onEndpointIdRotated(@Nullable String oldEndpointId, @NonNull String newEndpointId) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onEndpointIdRotated");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("oldEndpointId", oldEndpointId);
    eventData.putString("newEndpointId", newEndpointId);
    EventCache.getInstance().postEvent(snippetEvent);
  }
}
