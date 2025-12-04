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

import static java.nio.charset.StandardCharsets.UTF_8;

import android.content.Context;
import android.content.Intent;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.android.gms.nearby.Nearby;
import com.google.android.gms.nearby.connection.Payload;
// TODO: import com.google.android. ... .ConnectionsConnectionlessImpl;
import com.google.android.gms.tasks.OnSuccessListener;
import com.google.android.gms.tasks.Tasks;
// TODO: import com.google.android. ... .Utils;
import com.google.android.mobly.snippet.Snippet;
import com.google.android.mobly.snippet.event.EventCache;
import com.google.android.mobly.snippet.event.SnippetEvent;
import com.google.android.mobly.snippet.rpc.AsyncRpc;
import com.google.android.mobly.snippet.rpc.Rpc;
import com.google.android.mobly.snippet.util.Log;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.RandomAccessFile;
import java.util.Arrays;
import java.util.Objects;

/** Snippet class that exposes Nearby Connections APIs as RPC calls. */
public class ConnectionsClientSnippet implements Snippet {
  private static final String SENDER_FILE_PREFIX = "nearby_test_";

  private final Context context;
  private PayloadEvents payloadEvents;

  public ConnectionsClientSnippet() {
    context = InstrumentationRegistry.getInstrumentation().getContext();
    // TODO: Utils.registerNetworkStateCallback(context);
  }

  @Rpc(description = "Bring the snippet service to the foreground by starting an activity.")
  public void bringToFront() {
    Intent intent = new Intent(context, MainActivity.class);
    intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    context.startActivity(intent);
  }

  /** Called after request connection or start advertizing. */
  @Rpc(description = "Get Local Endpoint Id.")
  public String getLocalEndpointId() throws Exception {
    verifyApiConnection();
    return Tasks.await(Nearby.getConnectionsClient(context).getLocalEndpointId());
  }

  @AsyncRpc(description = "Start advertising.")
  public void startAdvertising(
      String callbackId,
      String advertisingName,
      String advertisingServiceId,
      int advertisingMedium,
      int upgradeMedium)
      throws Exception {
    verifyApiConnection();
    Tasks.await(
        Nearby.getConnectionsClient(context)
            .startAdvertising(
                advertisingName,
                advertisingServiceId,
                new ConnectionLifecycleEvents(callbackId),
                MediumSettingsFactory.getAdvertisingOptions(advertisingMedium, upgradeMedium))
            .addOnSuccessListener(
                new OnSuccessListener<Void>() {
                  @Override
                  public void onSuccess(Void unusedResult) {
                    EventCache.getInstance().postEvent(new SnippetEvent(callbackId, "onSuccess"));
                  }
                }));
  }

  @Rpc(description = "Stop advertising.")
  public void stopAdvertising() throws Exception {
    verifyApiConnection();
    Nearby.getConnectionsClient(context).stopAdvertising();
  }

  @AsyncRpc(description = "Start discovery.")
  public void startDiscovery(String callbackId, String advertisingServiceId, int discoveryMedium)
      throws Exception {
    verifyApiConnection();
    Tasks.await(
        Nearby.getConnectionsClient(context)
            .startDiscovery(
                advertisingServiceId,
                new EndpointDiscoveryEvents(callbackId),
                MediumSettingsFactory.getDiscoveryMediumOptions(discoveryMedium)));
  }

  @Rpc(description = "Stop discovery.")
  public void stopDiscovery() throws Exception {
    verifyApiConnection();
    Nearby.getConnectionsClient(context).stopDiscovery();
  }

  @AsyncRpc(description = "Request connection.")
  public void requestConnection(
      String callbackId,
      String connectionName,
      String connectionEndpointId,
      int connectionMedium,
      int upgradeMedium,
      int mediumUpgradeType,
      int keepAliveTimeoutMillis,
      int keepAliveTimeoutIntervalMillis)
      throws Exception {
    verifyApiConnection();
    Tasks.await(
        Nearby.getConnectionsClient(context)
            .requestConnection(
                connectionName.getBytes(UTF_8),
                connectionEndpointId,
                new ConnectionLifecycleEvents(callbackId),
                MediumSettingsFactory.getConnectionMediumOptions(
                    connectionMedium, upgradeMedium, mediumUpgradeType, keepAliveTimeoutMillis,
                    keepAliveTimeoutIntervalMillis)));
  }

  @AsyncRpc(description = "Accept connection.")
  public void acceptConnection(String callbackId, String endpointId) throws Exception {
    verifyApiConnection();
    payloadEvents = new PayloadEvents(context, callbackId);
    Tasks.await(Nearby.getConnectionsClient(context).acceptConnection(endpointId, payloadEvents));
  }

  @Rpc(description = "Disconnect from endpoint.")
  public void disconnectFromEndpoint(String endpointId) throws Exception {
    verifyApiConnection();
    Nearby.getConnectionsClient(context).disconnectFromEndpoint(endpointId);
  }

  @Rpc(description = "Send a single payload.")
  public long sendPayload(String endpointId, String name, int sizeInKb) throws Exception {
    return sendPayloadWithType(endpointId, name, sizeInKb, Payload.Type.FILE);
  }

  @Rpc(description = "Send a single payload with specified type.")
  public long sendPayloadWithType(
      String endpointId, String name, int sizeInKb, @Payload.Type int type) throws Exception {
    return sendMultiplePayloadWithType(endpointId, name, sizeInKb, Payload.Type.FILE, 1);
  }

  @Rpc(description = "Send multiple payloads with specified type and return the last payload id.")
  public long sendMultiplePayloadWithType(
      String endpointId, String name, int sizeInKb, @Payload.Type int type, int numFiles)
      throws Exception {
    if (payloadEvents == null) {
      throw new Exception(
          "Ignore the call to sendPayloadWithType() type:'"
              + type
              + "', the connection is not yet accept.");
    }

    Payload[] payload = new Payload[numFiles];
    for (int i = 0; i < numFiles; i++) {
      payload[i] = createPayload(name + i, sizeInKb, type);
    }
    verifyApiConnection();
    payloadEvents.startTransferStopwatch();
    for (int i = 0; i < numFiles; i++) {
      Tasks.await(
          Nearby.getConnectionsClient(context).sendPayload(Arrays.asList(endpointId), payload[i]));
    }
    return payload[numFiles - 1].getId();
  }

  @Rpc(
      description =
          "Disconnects from, and removes all traces of, all connected and/or discovered endpoints.")
  public void stopAllEndpoints() {
    Nearby.getConnectionsClient(context).stopAllEndpoints();
  }

  private Payload createPayload(String name, int sizeInKb, @Payload.Type int type)
      throws IOException {
    String payloadFileName = SENDER_FILE_PREFIX + name;
    File externalFilesDirOfThisApp = context.getExternalFilesDir(null);
    File payloadFile = new File(externalFilesDirOfThisApp, payloadFileName);
    RandomAccessFile randomAccessFile = null;
    InputStream inputStream = null;
    Payload payload;
    try {
      if (payloadFile.exists()) {
        payloadFile.delete();
      }
      randomAccessFile = new RandomAccessFile(payloadFile, "rw");
      randomAccessFile.setLength(1024L * sizeInKb);
      if (type == Payload.Type.STREAM) {
        inputStream = new FileInputStream(payloadFile);
      }
    } catch (SecurityException exception) {
      throw new IOException(
          "Fail to create payload file '"
              + payloadFileName
              + "' at path '"
              + payloadFile.getAbsolutePath()
              + "', encounter exception",
          exception);
    } finally {
      if (randomAccessFile != null) {
        randomAccessFile.close();
      }
    }

    switch (type) {
      case Payload.Type.STREAM:
        payload = Payload.fromStream(inputStream);
        break;
        // Payload.Type.BYTES is unsupported type, but keep other types same as Payload.Type.FILE
      case Payload.Type.FILE:
      default:
        payload = Payload.fromFile(payloadFile);
    }
    return payload;
  }

  @Rpc(description = "Clean up transfer files.")
  public void transferFilesCleanup() {
    // Remove sender side files.
    File externalFilesDirOfThisApp = context.getExternalFilesDir(null);
    for (File file : Objects.requireNonNull(externalFilesDirOfThisApp.listFiles())) {
      if (file.getName().startsWith(SENDER_FILE_PREFIX)) {
        if (file.delete()) {
          Log.d("Deleted file " + file.getAbsolutePath());
        } else {
          throw new RuntimeException("Fail to delete file " + file.getAbsolutePath());
        }
      }
    }
  }

  /**
   * Checks whether or not the Connections API client is connected, and throws an exception if
   * unconnected.
   */
  void verifyApiConnection() throws Exception {
    // TODO: Utils.verifyGoogleApiConnection(
        // (ConnectionsConnectionlessImpl) Nearby.getConnectionsClient(context));
  }
}
