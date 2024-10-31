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

package com.google.android.nearby.mobly.snippet.connection.thirdparty;

import android.content.Context;
import android.content.Intent;
import androidx.test.platform.app.InstrumentationRegistry;
// TODO: import com.google.android. ... .Utils;
import com.google.android.mobly.snippet.rpc.Rpc;
import com.google.android.nearby.mobly.snippet.connection.ConnectionsClientSnippet;

/** PlaceHolder for 3p nearby snippet app instance. */
public class ConnectionsClientSnippet3p extends ConnectionsClientSnippet {

  private final Context context;

  public ConnectionsClientSnippet3p() {
    context = InstrumentationRegistry.getInstrumentation().getContext();
    // TODO: Utils.registerNetworkStateCallback(context);
  }

  @Override
  @Rpc(description = "Bring the snippet service to the foreground by starting an activity.")
  public void bringToFront() {
    Intent intent = new Intent(context, MainActivity.class);
    intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    context.startActivity(intent);
  }
}
