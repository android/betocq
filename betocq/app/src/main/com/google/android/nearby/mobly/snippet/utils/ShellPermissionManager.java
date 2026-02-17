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
import android.os.Build;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.android.mobly.snippet.util.Log;
import java.util.Arrays;
import java.util.concurrent.Callable;

/** Utility class for managing shell permissions for Mobly tests. */
public class ShellPermissionManager {
  private ShellPermissionManager() {}

  private static final ThreadLocal<Integer> adoptionCount =
      new ThreadLocal<Integer>() {
        @Override
        protected Integer initialValue() {
          return 0;
        }
      };

  /**
   * Adopts the specified shell permissions.
   *
   * @param permissions The permissions to grant (if empty all permissions will be granted).
   */
  public static void adoptShellPermission(String... permissions) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
      Log.w(
          "adoptShellPermissionIdentity requires API level 28, but the current SDK version is "
              + Build.VERSION.SDK_INT
              + ". Shell permissions will not be adopted.");
      return;
    }

    if (adoptionCount.get() == 0) {
      // Reuse an UiAutomation instance if there is an existing one; otherwise, get one.
      UiAutomation uia = InstrumentationRegistry.getInstrumentation().getUiAutomation();
      if (permissions.length == 0) {
        uia.adoptShellPermissionIdentity();
        Log.d("Adopting shell identity of the shell UID for all permissions successfully.");
      } else {
        uia.adoptShellPermissionIdentity(permissions);
        Log.d(
            "Adopting shell identity of the shell UID for permissions successfully: "
                + Arrays.toString(permissions));
      }
      Log.d("UiAutomation instance from ShellPermissionManager: " + uia);
    } else {
      Log.d(
          "Shell permissions already adopted, skipping adoptShellPermissionIdentity."
              + " Nested call requested permissions: "
              + Arrays.toString(permissions));
    }
    adoptionCount.set(adoptionCount.get() + 1);
  }

  /** Drop the shell permissions adopted */
  public static void dropShellPermission() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
      Log.i(
          "dropShellPermissionIdentity requires API level 28, but the current SDK version is "
              + Build.VERSION.SDK_INT
              + ". No shell permissions to drop.");
      return;
    }

    if (adoptionCount.get() <= 0) {
      Log.e("No shell permissions adopted, cannot drop.");
      return;
    }

    adoptionCount.set(adoptionCount.get() - 1);
    if (adoptionCount.get() == 0) {
      UiAutomation uia = InstrumentationRegistry.getInstrumentation().getUiAutomation();
      uia.dropShellPermissionIdentity();
      Log.d("UiAutomation instance from ShellPermissionManager after dropping: " + uia);
    } else {
      Log.d("Still in nested shell permission adoption, not dropping permissions yet.");
    }
  }

  /**
   * Executes a method with a non-void return type with permission escalation.
   *
   * <p>Adopts the specified shell permissions, executes the {@link Callable} passed to it, then
   * drops the permissions and returns the invocation result.
   *
   * <p>Sample usage: {@code boolean ret = executeWithShellPermission( () -> { return
   * doSomething();});}
   *
   * @param callable the {@link Callable} to execute
   * @param permissions the permissions to grant (if empty all permissions will be granted)
   * @return the callable execution result
   */
  public static <T> T executeWithShellPermission(Callable<T> callable, String... permissions) {
    try {
      adoptShellPermission(permissions);
      return callable.call();
    } catch (Exception e) {
      throw new RuntimeException("executeWithShellPermission failed", e);
    } finally {
      dropShellPermission();
    }
  }

  /**
   * Executes a method with a void return type with permission escalation.
   *
   * <p>Adopts the specified shell permissions, executes the {@link Runnable} passed to it, then
   * drops the permissions.
   *
   * <p>Sample usage: {@code executeWithShellPermission(() -> { doSomething(); });}
   *
   * @param runnable the {@link Runnable} to execute
   * @param permissions the permissions to grant (if empty all permissions will be granted)
   */
  public static void executeWithShellPermission(Runnable runnable, String... permissions) {
    try {
      adoptShellPermission(permissions);
      runnable.run();
    } catch (RuntimeException e) {
      throw new RuntimeException("executeWithShellPermission failed", e);
    } finally {
      dropShellPermission();
    }
  }
}
