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
import com.google.android.gms.nearby.connection.DiscoveredEndpointInfo;
import com.google.android.gms.nearby.connection.EndpointDiscoveryCallback;
import com.google.android.mobly.snippet.event.EventCache;
import com.google.android.mobly.snippet.event.SnippetEvent;
import com.google.common.android.base.AndroidTicker;
import com.google.common.base.Stopwatch;

/** Reports Nearby Connections' endpoint discovery events to the test scripts side. */
public class EndpointDiscoveryEvents extends EndpointDiscoveryCallback {
  private final String callbackId;
  private final Stopwatch discoveryStopwatch;

  public EndpointDiscoveryEvents(String callbackId) {
    this.callbackId = callbackId;
    this.discoveryStopwatch = Stopwatch.createUnstarted(AndroidTicker.systemTicker());
    this.discoveryStopwatch.start();
  }

  @Override
  public void onEndpointFound(String endpointId, DiscoveredEndpointInfo discoveredEndpointInfo) {
    long discoveryTimeNs = discoveryStopwatch.elapsed(NANOSECONDS);
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onEndpointFound");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", endpointId);
    eventData.putLong("discoveryTimeNs", discoveryTimeNs);

    Bundle discoveredEndpointData = new Bundle();
    discoveredEndpointData.putString("endpointName", discoveredEndpointInfo.getEndpointName());
    discoveredEndpointData.putString("serviceId", discoveredEndpointInfo.getServiceId());
    eventData.putParcelable("discoveredEndpointInfo", discoveredEndpointData);

    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onEndpointLost(String endpointId) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onEndpointLost");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", endpointId);
    EventCache.getInstance().postEvent(snippetEvent);
  }
}
