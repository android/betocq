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
import android.util.LongSparseArray;
import com.google.android.gms.nearby.connection.Payload;
import com.google.android.gms.nearby.connection.PayloadCallback;
import com.google.android.gms.nearby.connection.PayloadTransferUpdate;
import com.google.android.gms.nearby.connection.PayloadTransferUpdate.Status;
import com.google.android.mobly.snippet.event.EventCache;
import com.google.android.mobly.snippet.event.SnippetEvent;
import com.google.android.mobly.snippet.util.Log;
import com.google.common.android.base.AndroidTicker;
import com.google.common.base.Stopwatch;
import java.io.IOException;
import java.io.InputStream;
import java.util.Objects;

/** Reports Nearby Connections' payload events to the test scripts side. */
public class PayloadEvents extends PayloadCallback {
  private final Context context;
  private final String callbackId;
  private final Stopwatch transferStopwatch;
  private final LongSparseArray<Payload> incomingPayloadsById = new LongSparseArray<>();
  private final LongSparseArray<IncomingStreamData> incomingStreamDataByPayloadId =
      new LongSparseArray<>();

  PayloadEvents(Context context, String callbackId) {
    this.context = context;
    this.callbackId = callbackId;
    this.transferStopwatch = Stopwatch.createUnstarted(AndroidTicker.systemTicker());
  }

  private static class IncomingStreamData {
    private final InputStream inputStream;
    private long receivedBytes = 0;

    private IncomingStreamData(InputStream inputStream) {
      this.inputStream = inputStream;
    }
  }

  public void startTransferStopwatch() {
    if (!transferStopwatch.isRunning()) {
      transferStopwatch.start();
    }
  }

  private String getPayloadType(Payload payload) {
    return switch (payload.getType()) {
      case Payload.Type.BYTES -> "BYTES";
      case Payload.Type.FILE -> "FILE";
      case Payload.Type.STREAM -> "STREAM";
      default -> "UNKNOWN";
    };
  }

  @Override
  public void onPayloadReceived(String endpointId, Payload payload) {
    incomingPayloadsById.put(payload.getId(), payload);
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onPayloadReceived");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", endpointId);

    Log.d("PayloadReceived type:" + getPayloadType(payload) + " id:" + payload.getId());
    if (payload.getType() == Payload.Type.STREAM) {
      incomingStreamDataByPayloadId.put(
          payload.getId(), new IncomingStreamData(payload.asStream().asInputStream()));
    }

    Bundle payloadData = new Bundle();
    payloadData.putLong("id", payload.getId());
    payloadData.putString("type", getPayloadType(payload));
    eventData.putParcelable("payload", payloadData);

    EventCache.getInstance().postEvent(snippetEvent);
  }

  @Override
  public void onPayloadTransferUpdate(String endpointId, PayloadTransferUpdate update) {
    SnippetEvent snippetEvent = new SnippetEvent(callbackId, "onPayloadTransferUpdate");
    Bundle eventData = snippetEvent.getData();
    eventData.putString("endpointId", endpointId);
    long payloadId = update.getPayloadId();

    Payload incomingPayload = incomingPayloadsById.get(payloadId);
    if (incomingPayload != null) {
      IncomingStreamData incomingStreamData = incomingStreamDataByPayloadId.get(payloadId);
      if (incomingPayload.getType() == Payload.Type.STREAM && incomingStreamData == null) {
        // Most likely incoming different type payloads or outgoing payloads. Nothing to do.
        return;
      }

      if (update.getStatus() == Status.IN_PROGRESS) {
        if (incomingPayload.getType() == Payload.Type.STREAM) {
          try {
            long newBytes = update.getBytesTransferred() - incomingStreamData.receivedBytes;
            byte[] bytes = new byte[(int) newBytes];
            int bytesRead = incomingStreamData.inputStream.read(bytes);
            if (bytesRead != newBytes) {
              // TODO: Fix the stream consumption logic to ensure that we read the expected
              // number of bytes, either once we reach the end of the stream or by using a loop on a
              // consumer thread. For now, we just log the issue for debugging purposes.
              Log.d(
                  "PayloadTransferUpdate expected "
                      + newBytes
                      + " bytes from incoming stream but got "
                      + bytesRead
                      + " bytes!");
            }
            incomingStreamData.receivedBytes += newBytes;
          } catch (IOException e) {
            Log.d(
                "PayloadTransferUpdate failed to copy received bytes from stream payload id="
                    + payloadId);
          }
        }
        return;
      }

      // Terminal state: SUCCESS, FAILURE, or CANCELLED.
      try {
        // Remove the received file through URI to avoid access limitation due to
        // scoped storage enforcement on Android 11. File location is /sdcard/Download/.nearby/...
        // The read/write access to the payload URI already granted by
        // ClientProxy inside Nearby Connection.
        if (incomingPayload.asFile() != null) {
          context
              .getContentResolver()
              .delete(
                  Objects.requireNonNull(incomingPayload.asFile()).asUri(),
                  null /* where */,
                  null /* selectionArgs */);
        }

        if (incomingPayload.getType() == Payload.Type.STREAM && incomingStreamData != null) {
          try {
            incomingStreamData.inputStream.close();
          } catch (IOException e) {
            Log.e("Failed to close input stream for payload " + payloadId, e);
          } finally {
            incomingStreamDataByPayloadId.remove(payloadId);
          }
        }
      } finally {
        incomingPayloadsById.remove(payloadId);
        incomingPayload.close();
      }
    }

    if (transferStopwatch.isRunning()) {
      eventData.putLong("transferTimeNs", transferStopwatch.elapsed().toNanos());
    }

    Log.d("PayloadTransferUpdate ID:" + payloadId);
    Bundle updateData = new Bundle();
    updateData.putLong("bytesTransferred", update.getBytesTransferred());
    updateData.putLong("totalBytes", update.getTotalBytes());
    updateData.putLong("payloadId", update.getPayloadId());
    updateData.putInt("statusCode", update.getStatus());
    updateData.putBoolean("isSuccess", update.getStatus() == Status.SUCCESS);
    eventData.putParcelable("update", updateData);
    EventCache.getInstance().postEvent(snippetEvent);
  }
}
