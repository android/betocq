package com.google.android.nearby.mobly.snippet.betocore

import android.annotation.SuppressLint
import android.content.Context
import com.google.android.gms.nearby.betocore.NearbyCore
import com.google.android.gms.nearby.betocore.ffi.BetoCoreClient
import com.google.android.gms.nearby.betocore.ffi.BroadcastHandle
import com.google.android.gms.nearby.betocore.ffi.DiscoveryHandle
import com.google.android.mobly.snippet.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancel

/** BeToCore adapter for Oxide Library. */
class OxideBeToCoreAdapter(context: Context) : IBeToCoreAdapter {
  @SuppressLint("GlobalCoroutineDispatchers") private val scope = CoroutineScope(Dispatchers.IO)
  private val betoCoreClient: BetoCoreClient = NearbyCore.createBetoCoreClient(context)
  private var broadcastHandle: BroadcastHandle? = null
  private var discoveryHandle: DiscoveryHandle? = null
  private val discoveredTxPowers = mutableListOf<String>()

  override suspend fun close() {
    Log.d("Oxide close called!")
    broadcastHandle?.stop()
    broadcastHandle?.close()
    broadcastHandle = null
    discoveryHandle?.stop()
    discoveryHandle?.close()
    discoveryHandle = null
    scope.cancel("OxideBeToCoreAdapter is being closed")
  }
}
