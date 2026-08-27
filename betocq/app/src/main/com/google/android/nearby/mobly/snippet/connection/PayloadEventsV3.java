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

import android.content.Context;
import android.os.Bundle;
import android.util.Pair;
import com.google.android.gms.nearby.connection.Device;
import com.google.android.gms.nearby.connection.Payload;
import com.google.android.gms.nearby.connection.PayloadTransferUpdate;
import com.google.android.gms.nearby.connection.PayloadTransferUpdate.Status;
import com.google.android.gms.nearby.connection.v2.PayloadCallback;
import com.google.android.gms.nearby.connection.v3.dct.DctDevice;
import com.google.android.gms.nearby.connection.v3.dct.DctPayload;
import com.google.android.gms.nearby.connection.v3.dct.DctPayload.DctPayloadType;
import com.google.android.mobly.snippet.event.EventCache;
import com.google.android.mobly.snippet.event.SnippetEvent;
import com.google.android.mobly.snippet.util.Log;
import com.google.common.android.base.AndroidTicker;
import com.google.common.base.Stopwatch;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** A callback that reports payload events to the test scripts side for V3. */
public class PayloadEventsV3 extends PayloadCallback<Device> {

  private final Context context;
  private final String callbackId;
  private final Stopwatch transferStopwatch;
  private final ConnectionsClientV3Snippet connectionsClientSnippet;
  private Payload receivedPayload;
  private final ExecutorService executor = Executors.newSingleThreadExecutor();

  PayloadEventsV3(Context context, String callbackId, ConnectionsClientV3Snippet snippet) {
    this.context = context;
    this.callbackId = callbackId;
    this.transferStopwatch = Stopwatch.createUnstarted(AndroidTicker.systemTicker());
    this.connectionsClientSnippet = snippet;
  }

  public void startTransferStopwatch() {
    if (!transferStopwatch.isRunning()) {
      transferStopwatch.start();
    }
  }

  @Override
  public void onPayloadReceived(Device device, Payload payload) {
    if (payload instanceof DctPayload v3Payload && v3Payload.isRequest()) {
      executor.execute(
          () -> {
            try {
              connectionsClientSnippet.sendResponsePayload(
                  (DctDevice) device, v3Payload.asRequest().getId(), this);
            } catch (Exception e) {
              Log.e("Failed to send response payload: " + e);
            }
          });
    } else {
      receivedPayload = payload;
    }
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onPayloadReceived");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());

    Log.d("PayloadReceived type:" + getPayloadType(payload) + " id:" + payload.getId());

    Bundle payloadData = new Bundle();
    payloadData.putLong("id", payload.getId());
    payloadData.putString("type", getPayloadType(payload));
    eventData.putParcelable("payload", payloadData);
    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onPayloadTransferUpdate(Device device, PayloadTransferUpdate update) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onPayloadTransferUpdate");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", device.getEndpointId());
    long payloadId = update.getPayloadId();

    int status = update.getStatus();
    if (status == Status.IN_PROGRESS) {
      return;
    }

    if (status == Status.SUCCESS) {
      if (transferStopwatch.isRunning()) {
        eventData.putLong("transferTimeNs", transferStopwatch.elapsed().toNanos());
      }
    }
    // Remove the received file through URI to avoid access limitation due to
    // scoped storage enforcement on Android 11. File location is /sdcard/Download/.nearby/...
    // The read/write access to the payload URI already granted by
    // ClientProxy inside Nearby Connection.
    if (receivedPayload != null) {
      if (receivedPayload instanceof DctPayload v3Payload
          && v3Payload.getDctPayloadType() == DctPayloadType.FILES_RESPONSE) {
        DctPayload.FilesResponse filesResponse = (DctPayload.FilesResponse) v3Payload.asResponse();
        if (filesResponse != null) {
          for (Pair<byte[], Payload.File> filePair : filesResponse.getFiles()) {
            Payload.File file = filePair.second;
            if (file != null && file.asUri() != null) {
              try {
                context.getContentResolver().delete(file.asUri(), null, null);
              } catch (RuntimeException e) {
                Log.e("Failed to delete received file: " + file.asUri(), e);
              }
            }
          }
        }
      } else if (receivedPayload.asFile() != null) {
        context
            .getContentResolver()
            .delete(
                Objects.requireNonNull(receivedPayload.asFile()).asUri(),
                null /* where */,
                null /* selectionArgs */);
      }
    }

    Log.d("PayloadTransferUpdate ID:" + payloadId);
    Bundle updateData = new Bundle();
    updateData.putLong("bytesTransferred", update.getBytesTransferred());
    updateData.putLong("totalBytes", update.getTotalBytes());
    updateData.putLong("payloadId", update.getPayloadId());
    updateData.putInt("statusCode", update.getStatus());
    updateData.putBoolean("isSuccess", status == Status.SUCCESS);
    eventData.putParcelable("update", updateData);
    EventCache.getInstance().postEvent(snippetEvent);
  }

  private String getPayloadType(Payload payload) {
    if (payload instanceof DctPayload v3Payload) {
      return switch (v3Payload.getDctPayloadType()) {
        case DctPayloadType.REQUEST -> "REQUEST";
        case DctPayloadType.BYTES_RESPONSE -> "BYTES_RESPONSE";
        case DctPayloadType.FILES_RESPONSE -> "FILES_RESPONSE";
        default -> "UNKNOWN";
      };
    } else {
      return switch (payload.getType()) {
        case Payload.Type.BYTES -> "BYTES";
        case Payload.Type.FILE -> "FILE";
        case Payload.Type.STREAM -> "STREAM";
        default -> "UNKNOWN";
      };
    }
  }
}
