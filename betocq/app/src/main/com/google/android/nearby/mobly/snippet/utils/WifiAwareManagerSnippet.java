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

import android.content.Context;
import android.content.pm.PackageManager;
import android.net.wifi.aware.WifiAwareManager;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.android.mobly.snippet.Snippet;
import com.google.android.mobly.snippet.rpc.Rpc;

/** Snippet class exposing Android APIs in WifiAwareManager. */
public class WifiAwareManagerSnippet implements Snippet {

  private static class WifiAwareManagerSnippetException extends Exception {
    private static final long serialVersionUID = 1;

    WifiAwareManagerSnippetException(String msg) {
      super(msg);
    }
  }

  private final Context context;
  private final boolean isAwareSupported;
  WifiAwareManager wifiAwareManager;

  /** Default Constructor */
  public WifiAwareManagerSnippet() throws Throwable {
    context = InstrumentationRegistry.getInstrumentation().getContext();
    isAwareSupported =
        context.getPackageManager().hasSystemFeature(PackageManager.FEATURE_WIFI_AWARE);
    if (isAwareSupported) {
      wifiAwareManager = (WifiAwareManager) context.getSystemService(Context.WIFI_AWARE_SERVICE);
    }
  }

  /** Checks if Aware is supported. */
  @Rpc(description = "check if Aware is supported.")
  public boolean wifiAwareIsSupported() {
    return isAwareSupported;
  }

  /** Checks if Aware is available. This could return false if WiFi or location is disabled. */
  @Rpc(description = "check if Aware is available.")
  public boolean wifiAwareIsAvailable() throws WifiAwareManagerSnippetException {
    if (!isAwareSupported) {
      throw new WifiAwareManagerSnippetException("WifiAware is not supported in this device");
    }
    return ShellPermissionManager.executeWithShellPermission(wifiAwareManager::isAvailable);
  }
}
