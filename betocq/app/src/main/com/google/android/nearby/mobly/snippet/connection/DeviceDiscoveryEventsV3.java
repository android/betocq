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
import com.google.android.gms.nearby.connection.DistanceInfo;
import com.google.android.gms.nearby.connection.v3.DeviceDiscoveryCallback;
import com.google.android.gms.nearby.connection.v3.dct.DctDevice;
import com.google.android.mobly.snippet.event.EventCache;
import com.google.android.mobly.snippet.event.SnippetEvent;
import com.google.common.android.base.AndroidTicker;
import com.google.common.base.Stopwatch;

/** A callback that reports Device discovery events to the test scripts side for V3. */
public class DeviceDiscoveryEventsV3 extends DeviceDiscoveryCallback<DctDevice> {
  private final String callbackId;
  private final Stopwatch discoveryStopwatch;

  public DeviceDiscoveryEventsV3(String callbackId) {
    super(DctDevice.class);
    this.callbackId = callbackId;
    this.discoveryStopwatch = Stopwatch.createUnstarted(AndroidTicker.systemTicker());
    this.discoveryStopwatch.start();
  }

  @Override
  public void onDeviceFound(@NonNull DctDevice device) {
    long discoveryTimeNs = discoveryStopwatch.elapsed().toNanos();
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onDeviceFound");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putByteArray("endpointInfo", device.getEndpointInfo());
    eventData.putLong("discoveryTimeNs", discoveryTimeNs);
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onDeviceLost(@NonNull DctDevice device) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onDeviceLost");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onDeviceDistanceChanged(
      @NonNull DctDevice device, @NonNull DistanceInfo distanceInfo) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onDeviceDistanceChanged");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    eventData.putInt("distance", distanceInfo.getDistance());
    EventCache.getInstance().postEvent(snippetEvent);
  }
}
