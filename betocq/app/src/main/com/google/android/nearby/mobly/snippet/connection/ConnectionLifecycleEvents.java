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

import static java.util.concurrent.TimeUnit.NANOSECONDS;

import android.os.Bundle;
import com.google.android.gms.nearby.connection.BandwidthInfo;
import com.google.android.gms.nearby.connection.BandwidthInfo.Quality;
import com.google.android.gms.nearby.connection.ConnectionInfo;
import com.google.android.gms.nearby.connection.ConnectionLifecycleCallback;
import com.google.android.gms.nearby.connection.ConnectionResolution;
import com.google.android.mobly.snippet.event.EventCache;
import com.google.android.mobly.snippet.event.SnippetEvent;
import com.google.common.android.base.AndroidTicker;
import com.google.common.base.Stopwatch;

/** Reports Nearby Connections' lifecycle events to the test scripts side. */
public class ConnectionLifecycleEvents extends ConnectionLifecycleCallback {
  private final String callbackId;
  private final Stopwatch connectionStopwatch;

  public ConnectionLifecycleEvents(String callbackId) {
    this.callbackId = callbackId;
    this.connectionStopwatch = Stopwatch.createUnstarted(AndroidTicker.systemTicker());
    this.connectionStopwatch.start();
  }

  @Override
  public void onConnectionInitiated(String endpointId, ConnectionInfo connectionInfo) {
    long connectionTimeNs = connectionStopwatch.elapsed(NANOSECONDS);
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onConnectionInitiated");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", endpointId);
    eventData.putLong("connectionTimeNs", connectionTimeNs);

    Bundle connectionData = new Bundle();
    connectionData.putString("authenticationDigits", connectionInfo.getAuthenticationDigits());
    connectionData.putString("endpointName", connectionInfo.getEndpointName());
    connectionData.putBoolean("isIncomingConnection", connectionInfo.isIncomingConnection());
    eventData.putParcelable("connectionInfo", connectionData);

    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onConnectionResult(String endpointId, ConnectionResolution resolution) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onConnectionResult");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", endpointId);
    eventData.putInt("statusCode", resolution.getStatus().getStatusCode());
    eventData.putBoolean("isSuccess", resolution.getStatus().isSuccess());
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onDisconnected(String endpointId) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onDisconnected");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", endpointId);
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onBandwidthChanged(String endpointId, BandwidthInfo bandwidthInfo) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onBandwidthChanged");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", endpointId);
    eventData.putInt("upgradeStatus", bandwidthInfo.getUpgradeStatus());
    eventData.putInt("bwQuality", bandwidthInfo.getQuality());
    eventData.putBoolean("isHighBwQuality", bandwidthInfo.getQuality() == Quality.HIGH);
    eventData.putInt("medium", bandwidthInfo.getMedium());
    EventCache.getInstance().postEvent(snippetEvent);
  }
}
