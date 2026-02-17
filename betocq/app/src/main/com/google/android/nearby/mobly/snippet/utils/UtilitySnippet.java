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

import android.app.UiAutomation;
import android.os.RemoteException;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.android.mobly.snippet.Snippet;
import com.google.android.mobly.snippet.event.EventCache;
import com.google.android.mobly.snippet.rpc.Rpc;
import com.google.android.mobly.snippet.rpc.RpcOptional;
import com.google.android.mobly.snippet.util.Log;
import java.lang.reflect.Method;

/** Snippet class for exposing utility RPCs. */
public class UtilitySnippet implements Snippet {

  private UiAutomation uia = null;

  public UtilitySnippet() {}

  /** Acquires the UiAutomation instance. */
  @Rpc(description = "Acquires the UiAutomation instance.")
  public void acquireUiAutomation() {
    // Reuse an UiAutomation instance if there is an existing one; otherwise, create one.
    // The UiAutomation instance is maintained by the Instrumentation.
    if (uia == null) {
      uia = InstrumentationRegistry.getInstrumentation().getUiAutomation();
      Log.i("UiAutomation instance acquired: " + uia);
    }
  }

  /**
   * Releases the UiAutomation instance. Releasing UiAutomation is generally not recommended as it
   * is managed by Instrumentation, but this method is provided for corner cases. Once released, it
   * might be taken over by others. Typically, the UiAutomation will be released automatically when
   * the test is done. This method is added in case it needs to be released in a corner case, like
   * if the test needs to acquire the UiAutomation instance again in a different context.
   */
  @Rpc(description = "Releases the UiAutomation instance.")
  public void releaseUiAutomation() {
    if (uia == null) {
      throw new IllegalStateException("UiAutomation instance is not acquired yet.");
    }
    // Release the UiAutomation instance if there is an existing one.
    try {
      destroyUiaInstance();
    } catch (IllegalStateException e) {
      Log.i(
          "UiAutomation may be released already. Failed to release UiAutomation instance: "
              + e.getMessage());
    }
    uia = null;
  }

  /** Drops the shell permission. This is no-op if shell permission identity is not adopted. */
  @Rpc(
      description =
          "Drops the shell permission. This is no-op if shell"
              + " permission identity is not adopted.")
  public void dropShellPermission() {
    ShellPermissionManager.dropShellPermission();
  }

  private void destroyUiaInstance() {
    if (uia == null) {
      return;
    }
    Log.i("Destroy UiAutomation instance");
    try {
      Class<?> cls = uia.getClass();
      Method destroyMethod = cls.getDeclaredMethod("destroy");
      destroyMethod.invoke(uia);
      uia = null;
    } catch (ReflectiveOperationException e) {
      Log.e("Failed to cleanup UI Automation", e);
    }
  }

  /**
   * Adopts shell permission. If shell permissions are already adopted, subsequent calls will not
   * overwrite the existing adopted permissions.
   *
   * @param permissions The permissions to grant (if null all permissions will be granted).
   */
  @Rpc(
      description =
          "Adopts shell permission. If shell permissions are already adopted, subsequent calls will"
              + " not overwrite the existing adopted permissions.")
  public void adoptShellPermission(@RpcOptional String[] permissions) throws RemoteException {
    if (permissions == null) {
      ShellPermissionManager.adoptShellPermission();
    } else {
      ShellPermissionManager.adoptShellPermission(permissions);
    }
  }

  /** Clear the event cache. */
  @Rpc(description = "Clear the event cache.")
  public void clearEventCache() {
    EventCache.getInstance().clearAll();
  }

  @Override
  public void shutdown() {}
}
