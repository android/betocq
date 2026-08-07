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
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;
import android.util.Log;
import androidx.annotation.IntDef;
import androidx.annotation.Nullable;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.android.gms.common.api.ApiException;
import com.google.android.gms.nearby.Nearby;
import com.google.android.gms.nearby.connection.ConnectionsStatusCodes;
import com.google.android.gms.nearby.connection.Payload;
import com.google.android.gms.nearby.connection.v3.ClientOptions;
import com.google.android.gms.nearby.connection.v3.ConnectionResult;
import com.google.android.gms.nearby.connection.v3.ConnectionsClient;
import com.google.android.gms.nearby.connection.v3.DisconnectReason;
import com.google.android.gms.nearby.connection.v3.dct.DctDevice;
import com.google.android.gms.nearby.connection.v3.dct.DctDeviceDataElement;
import com.google.android.gms.nearby.connection.v3.dct.DctPayload;
import com.google.android.gms.nearby.connection.v3.dct.DctPayload.FileWithMetaData;
import com.google.android.gms.nearby.internal.connection.v3.ConnectionsConnectionlessImpl;
import com.google.android.gms.tasks.OnSuccessListener;
import com.google.android.gms.tasks.Tasks;
// TODO: import com.google.android. ... .Utils;
import com.google.android.mobly.snippet.Snippet;
import com.google.android.mobly.snippet.event.EventCache;
import com.google.android.mobly.snippet.event.SnippetEvent;
import com.google.android.mobly.snippet.rpc.AsyncRpc;
import com.google.android.mobly.snippet.rpc.Rpc;
import com.google.common.collect.ImmutableList;
import com.google.errorprone.annotations.CanIgnoreReturnValue;
import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Random;
import java.util.concurrent.atomic.AtomicInteger;

/** Snippet class that exposes Nearby Connections V3 APIs as RPC calls. */
public class ConnectionsClientV3Snippet implements Snippet {
  private static final String TAG = "ConnectionsClientV3Snippet";
  private static final String SENDER_FILE_PREFIX = "nearby_v3_test_";
  private static final String LOCAL_ENDPOINT_ID = "Nearby V3 Device";
  private static final String SERVICE_ID = "U14GxFKi";
  private static final int BYTES_PER_KB = 1024;
  private static final String CONTENT_TYPE = "application/vnd.os-migration.communications+proto";
  private static final String FILE_CONTENT_TYPE = "application/octet-stream";
  private static final int NUM_RETRIES = 3;

  private final Object responseParamsLock = new Object();
  private int responseSize = 0;
  private int responsePayloadType = 0;
  private int payloadPartType = 0;
  private int payloadPartNumber = 0;
  private final AtomicInteger supportedServices = new AtomicInteger(0);

  private final Context context;
  private volatile PayloadEventsV3 payloadEvents;
  private final List<ParcelFileDescriptor> openFileDescriptors =
      Collections.synchronizedList(new ArrayList<>());

  public ConnectionsClientV3Snippet() {
    context = InstrumentationRegistry.getInstrumentation().getContext();
    // TODO: Utils.registerNetworkStateCallback(context);
  }

  /** The part type. */
  @Retention(RetentionPolicy.SOURCE)
  @IntDef({
    PartType.SINGLE_PART,
    PartType.MULTI_PART,
  })
  public @interface PartType {
    int SINGLE_PART = 1;
    int MULTI_PART = 2;
  }

  @Override
  public void shutdown() {
    cleanupFilesV3();
  }

  @Rpc(description = "Cleanup opened file descriptors.")
  public void cleanupFilesV3() {
    synchronized (openFileDescriptors) {
      for (ParcelFileDescriptor pfd : openFileDescriptors) {
        try {
          if (pfd != null) {
            pfd.close();
          }
        } catch (IOException e) {
          Log.e(TAG, "Failed to close PFD", e);
        }
      }
      openFileDescriptors.clear();
    }
  }

  @Rpc(description = "Bring the snippet service to the foreground by starting an activity for V3.")
  public void bringToFrontV3() {
    Intent intent = new Intent(context, MainActivity.class);
    intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    context.startActivity(intent);
  }

  @AsyncRpc(description = "Start advertising for V3.")
  public void startAdvertisingV3(
      String callbackId,
      String password,
      int advertisingMedium,
      int upgradeMedium,
      int supportedServices)
      throws Exception {
    verifyApiConnection();
    retry(
        () ->
            Tasks.await(
                getConnectionsClient()
                    .startAdvertising(
                        LOCAL_ENDPOINT_ID.getBytes(UTF_8),
                        new ConnectionsAdvertisingEventsV3(callbackId),
                        MediumSettingsFactoryV3.getAdvertisingOptions(
                            password, advertisingMedium, upgradeMedium, supportedServices))
                    .addOnSuccessListener(
                        new OnSuccessListener<Void>() {
                          @Override
                          public void onSuccess(Void unusedResult) {
                            EventCache.getInstance()
                                .postEvent(new SnippetEvent(callbackId, "onSuccess"));
                          }
                        })));
    this.supportedServices.set(supportedServices);
  }

  @Rpc(description = "Stop advertising for V3.")
  public void stopAdvertisingV3() throws Exception {
    verifyApiConnection();
    getConnectionsClient().stopAdvertising();
  }

  @AsyncRpc(description = "Start discovery for V3.")
  public void startDiscoveryV3(String callbackId, int discoveryMedium, int supportedServices)
      throws Exception {
    verifyApiConnection();
    retry(
        () ->
            Tasks.await(
                getConnectionsClient()
                    .startDiscovery(
                        new DeviceDiscoveryEventsV3(callbackId),
                        MediumSettingsFactoryV3.getDiscoveryMediumOptions(
                            discoveryMedium, supportedServices))));
    this.supportedServices.set(supportedServices);
  }

  @Rpc(description = "Stop discovery for V3.")
  public void stopDiscoveryV3() throws Exception {
    verifyApiConnection();
    getConnectionsClient().stopDiscovery();
  }

  @AsyncRpc(description = "Request connection for V3.")
  public void requestConnectionV3(
      String callbackId,
      byte[] endpointInfo,
      String endpointId,
      String password,
      int connectionMedium,
      int upgradeMedium,
      int mediumUpgradeType)
      throws Exception {
    verifyApiConnection();
    DctDevice device = createDevice(endpointId, endpointInfo);
    ConnectionLifecycleEventsV3 lifecycleEvents = new ConnectionLifecycleEventsV3(callbackId);
    retryRequestConnection(
        () ->
            Tasks.await(
                getConnectionsClient()
                    .requestConnection(
                        endpointId.getBytes(UTF_8),
                        device,
                        lifecycleEvents,
                        MediumSettingsFactoryV3.getConnectionMediumOptions(
                            password, connectionMedium, upgradeMedium, mediumUpgradeType))),
        lifecycleEvents);
  }

  @AsyncRpc(description = "Accept connection for V3.")
  public void acceptConnectionV3(String callbackId, String endpointId, byte[] endpointInfo)
      throws Exception {
    verifyApiConnection();
    payloadEvents = new PayloadEventsV3(context, callbackId, this);
    DctDevice device = createDevice(endpointId, endpointInfo);
    retry(() -> Tasks.await(getConnectionsClient().acceptConnection(device, payloadEvents)));
  }

  @Rpc(description = "Disconnect from device for V3.")
  public void disconnectFromDeviceV3(String endpointId, byte[] endpointInfo) throws Exception {
    verifyApiConnection();
    DctDevice device = createDevice(endpointId, endpointInfo);
    getConnectionsClient().disconnectFromDevice(device, DisconnectReason.SUCCESS);
  }

  @Rpc(description = "Set response params for V3.")
  public void setResponseParamsV3(
      int sizeInKb,
      @DctPayload.DctPayloadType int payloadType,
      @PartType int partType,
      int partNumber) {
    synchronized (responseParamsLock) {
      responseSize = sizeInKb * BYTES_PER_KB;
      responsePayloadType = payloadType;
      payloadPartType = partType;
      payloadPartNumber = partNumber;
    }
  }

  @Rpc(description = "Send request payload for V3.")
  public void sendRequestPayloadV3(String endpointId, byte[] endpointInfo, int sizeInKb)
      throws Exception {
    DctDevice device = createDevice(endpointId, endpointInfo);
    DctPayload payload = createRequest(sizeInKb);
    sendPayloadInternal(device, payload);
  }

  void sendResponsePayload(DctDevice device, long requestId, PayloadEventsV3 payloadEvents)
      throws Exception {
    int size;
    int type;
    int pType;
    int pNumber;

    synchronized (responseParamsLock) {
      size = responseSize;
      type = responsePayloadType;
      pType = payloadPartType;
      pNumber = payloadPartNumber;
    }

    DctPayload payload =
        switch (type) {
          case DctPayload.DctPayloadType.BYTES_RESPONSE ->
              createBytesResponse(requestId, size, pType, pNumber);
          case DctPayload.DctPayloadType.FILES_RESPONSE ->
              createFilesResponse(requestId, size, pType, pNumber);
          default -> throw new IllegalArgumentException("Unsupported payload type: " + type);
        };
    payloadEvents.startTransferStopwatch();
    sendPayloadInternal(device, payload);
  }

  private void sendPayloadInternal(DctDevice device, DctPayload payload) throws Exception {
    verifyApiConnection();
    retry(() -> Tasks.await(getConnectionsClient().sendPayload(device, payload)));
  }

  @Rpc(description = "Send a single payload for V3.")
  public long sendPayloadV3(String endpointId, byte[] endpointInfo, String name, int sizeInKb)
      throws Exception {
    return sendPayloadWithTypeV3(endpointId, endpointInfo, name, sizeInKb, Payload.Type.BYTES);
  }

  @Rpc(description = "Send a single payload with specified type for V3.")
  public long sendPayloadWithTypeV3(
      String endpointId, byte[] endpointInfo, String name, int sizeInKb, @Payload.Type int type)
      throws Exception {
    return sendMultiplePayloadWithTypeV3(endpointId, endpointInfo, name, sizeInKb, type, 1);
  }

  @Rpc(
      description =
          "Send multiple payloads with specified type and return the last payload id for V3.")
  public long sendMultiplePayloadWithTypeV3(
      String endpointId,
      byte[] endpointInfo,
      String name,
      int sizeInKb,
      @Payload.Type int type,
      int numFiles)
      throws Exception {
    if (payloadEvents == null) {
      throw new Exception(
          "Ignore the call to sendPayloadWithType() type:'"
              + type
              + "', the connection is not yet accepted.");
    }
    DctDevice device = createDevice(endpointId, endpointInfo);
    Payload[] payload = new Payload[numFiles];
    for (int i = 0; i < numFiles; i++) {
      payload[i] = createPayload(sizeInKb, type);
    }
    verifyApiConnection();
    payloadEvents.startTransferStopwatch();
    for (int i = 0; i < numFiles; i++) {
      Payload p = payload[i];
      retry(() -> Tasks.await(getConnectionsClient().sendPayload(device, p)));
    }
    return payload[numFiles - 1].getId();
  }

  @Rpc(
      description =
          "Disconnects from, and removes all traces of, all connected and/or discovered devices for"
              + " V3.")
  public void stopAllEndpointsV3() {
    getConnectionsClient().stopAllDevices();
  }

  private Payload createPayload(int sizeInKb, @Payload.Type int type) throws IOException {
    if (type != Payload.Type.BYTES) {
      throw new UnsupportedOperationException("Unsupported payload type: " + type);
    }
    return Payload.fromBytes(generateRandomBytes(sizeInKb * BYTES_PER_KB));
  }

  private DctPayload createRequest(int sizeInKb) {
    int size = sizeInKb * BYTES_PER_KB;
    Uri uri = Uri.parse(String.format(Locale.US, "/data?size=%d", size));
    return DctPayload.fromRequest(uri, CONTENT_TYPE, generateRandomBytes(size));
  }

  private DctPayload createBytesResponse(
      long requestId, int byteArraySize, @PartType int partType, int partNumber) {
    List<byte[]> bytesList = new ArrayList<>();
    int generatePartNumber = partType == PartType.SINGLE_PART ? 1 : partNumber;
    for (int i = 0; i < generatePartNumber; i++) {
      bytesList.add(generateRandomBytes(byteArraySize));
    }
    return DctPayload.fromBytesResponse(
        requestId, bytesList, CONTENT_TYPE, /* isLast= */ true, partType == PartType.MULTI_PART);
  }

  private byte[] generateRandomBytes(int size) {
    byte[] bytes = new byte[size];
    new Random().nextBytes(bytes);

    return bytes;
  }

  @Rpc(description = "Clean up transfer files for V3.")
  public void transferFilesCleanupV3() {
    cleanupFilesV3();
    // Remove sender side files.
    File externalFilesDirOfThisApp = context.getExternalFilesDir(null);
    if (externalFilesDirOfThisApp == null) {
      Log.w(TAG, "External files directory is null, skipping cleanup.");
      return;
    }
    File[] files = externalFilesDirOfThisApp.listFiles();
    if (files == null) {
      Log.w(TAG, "List of files is null, skipping cleanup.");
      return;
    }
    for (File file : files) {
      if (file.getName().startsWith(SENDER_FILE_PREFIX)) {
        if (file.delete()) {
          Log.d(TAG, "Deleted file " + file.getAbsolutePath());
        } else {
          throw new RuntimeException("Fail to delete file " + file.getAbsolutePath());
        }
      }
    }
  }

  private File createFilePayload(long size) throws IOException {
    String payloadFileName = SENDER_FILE_PREFIX + SystemClock.elapsedRealtime();
    File externalFilesDirOfThisApp = context.getExternalFilesDir(null);
    File payloadFile = new File(externalFilesDirOfThisApp, payloadFileName);
    if (payloadFile.exists()) {
      payloadFile.delete();
    }
    try (RandomAccessFile randomAccessFile = new RandomAccessFile(payloadFile, "rw")) {
      randomAccessFile.setLength(size);
    } catch (SecurityException exception) {
      throw new IOException(
          String.format(
              "Failed to create payload file '%s' at path '%s'",
              payloadFileName, payloadFile.getAbsolutePath()),
          exception);
    }
    return payloadFile;
  }

  private DctPayload createFilesResponse(
      long requestId, long size, @PartType int partType, int partNumber) throws IOException {
    List<File> fileList = new ArrayList<>();
    int generatePartNumber = partType == PartType.SINGLE_PART ? 1 : partNumber;
    for (int i = 0; i < generatePartNumber; i++) {
      fileList.add(createFilePayload(size));
    }
    List<FileWithMetaData> pfdList = new ArrayList<>();
    byte[] metaData = {0x1, 0x2, 0x3, 0x4, 0x5, 0x6};
    for (int i = 0; i < fileList.size(); i++) {
      ParcelFileDescriptor pfd =
          ParcelFileDescriptor.open(fileList.get(i), ParcelFileDescriptor.MODE_READ_WRITE);
      synchronized (openFileDescriptors) {
        openFileDescriptors.add(pfd);
      }
      pfdList.add(new FileWithMetaData(Uri.fromFile(fileList.get(i)), pfd, metaData, size));
      Log.d(TAG, "file" + i + " size: " + pfdList.get(i).getContent().getStatSize());
    }

    return DctPayload.fromFilesResponse(
        requestId, pfdList, FILE_CONTENT_TYPE, /* isLast= */ true, partType == PartType.MULTI_PART);
  }

  /**
   * Checks whether or not the Connections API client is connected, and throws an exception if
   * unconnected.
   */
  void verifyApiConnection() throws Exception {
    // TODO: Utils.verifyGoogleApiConnection((ConnectionsConnectionlessImpl) getConnectionsClient());
  }

  protected ConnectionsClient getConnectionsClient() {
    return Nearby.getConnectionsClient(
        context, new ClientOptions.Builder().setServiceId(SERVICE_ID).build());
  }

  private DctDevice createDevice(String endpointId, byte[] endpointInfo) {
    return new DctDevice.Builder()
        .setEndpointId(endpointId)
        .setEndpointInfo(endpointInfo)
        .setDctDeviceDataElements(
            ImmutableList.of(
                new DctDeviceDataElement(
                    DctDeviceDataElement.Type.SUPPORTED_SERVICES,
                    1,
                    new byte[] {(byte) this.supportedServices.get()})))
        .build();
  }

  @CanIgnoreReturnValue
  @SuppressWarnings("PatternMatchingInstanceof")
  private <T> T retry(NearbyCallable<T> callable) throws Exception {
    Exception toThrow = null;
    for (int i = 0; i < NUM_RETRIES; i++) {
      try {
        return callable.call();
      } catch (Exception e) {
        ApiException apiException = extractApiException(e);
        if (apiExceptionRetryable(apiException)) {
          Log.w(TAG, "Failed to call Nearby API on attempt " + (i + 1) + ", retrying", e);
          toThrow = e;
          SystemClock.sleep(1000);
        } else {
          if (apiException != null) {
            throw new Exception(
                String.format(
                    "Nearby API call failed with status: %s (%d) %s",
                    ConnectionsStatusCodes.getStatusCodeString(apiException.getStatusCode()),
                    apiException.getStatusCode(),
                    apiException.getStatus().getStatusMessage()),
                e);
          }
          throw e;
        }
      }
    }
    throw toThrow;
  }

  @Nullable
  private ApiException extractApiException(Exception e) {
    if (e instanceof ApiException apiException) {
      return apiException;
    }

    if (e.getCause() instanceof ApiException) {
      return (ApiException) e.getCause();
    }

    return null;
  }

  private boolean apiExceptionRetryable(ApiException e) {
    if (e == null) {
      return false;
    }

    int statusCode = e.getStatusCode();
    return switch (statusCode) {
      case ConnectionsStatusCodes.INTERNAL_ERROR,
          ConnectionsStatusCodes.CONNECTION_SUSPENDED_DURING_CALL,
          ConnectionsStatusCodes.NETWORK_ERROR ->
          true;
      default -> false;
    };
  }

  private String getConnectionResultErrorMessage(ConnectionResult result) {
    if (result == null) {
      return "MISSING";
    }

    return String.format(
        "ConnectionResult: [%d] %s",
        result.getStatus().getStatusCode(), result.getStatus().getStatusString());
  }

  @CanIgnoreReturnValue
  private <T> T retryRequestConnection(
      NearbyCallable<T> callable, @Nullable ConnectionLifecycleEventsV3 lifecycleEvents)
      throws Exception {
    try {
      return retry(callable);
    } catch (Exception e) {
      throw new Exception(
          String.format(
              "RequestConnection failed with ConnectionResult status:\n %s \n And exception: %s",
              getConnectionResultErrorMessage(lifecycleEvents.getConnectionResult()),
              e.getMessage()),
          e);
    }
  }

  /** Functional interface for boxing up lambdas of Nearby API calls that we want to retry. */
  @FunctionalInterface
  private interface NearbyCallable<T> {
    T call() throws Exception;
  }
}
