package com.google.android.nearby.mobly.snippet.betocore

import android.content.Context
import com.google.android.gms.nearby.betocore.ffi.DiscoveryConfigV2Ffi
import com.google.android.gms.nearby.betocore.ffi.ServiceConfigV2Ffi
import com.google.android.mobly.snippet.event.SnippetEvent
import com.google.android.mobly.snippet.util.Log

/** BeToCore adapter for GMS Core API. */
class GmsBeToCoreAdapter(private val context: Context) : IBeToCoreAdapter {

  override fun registerService(config: ServiceConfigV2Ffi) {
    Log.d("GMS registerService called!")
    // TODO: Implement GMS registerService
  }

  override fun requestTemporaryPublicVisibility() {
    Log.d("GMS requestTemporaryPublicVisibility called!")
    // TODO: Implement GMS requestTemporaryPublicVisibility
  }

  override fun cancelTemporaryPublicVisibility() {
    Log.d("GMS cancelTemporaryPublicVisibility called!")
    // TODO: Implement GMS cancelTemporaryPublicVisibility
  }

  override fun onWakeupObserved(timeoutSec: Long): Boolean {
    Log.d("GMS onWakeupObserved called with timeout $timeoutSec!")
    // TODO: Implement GMS onWakeupObserved
    return false
  }

  override fun unregisterService() {
    Log.d("GMS unregisterService called!")
    // TODO: Implement GMS unregisterService
  }

  override fun startDiscovery(callbackEvent: SnippetEvent, discoveryConfig: DiscoveryConfigV2Ffi) {
    Log.d("GMS startDiscovery called!")
    // TODO: Implement GMS startDiscovery
  }

  override fun stopDiscovery() {
    Log.d("GMS stopDiscovery called!")
    // TODO: Implement GMS stopDiscovery
  }

  override fun getDiscoveredDeviceIds(): List<String> {
    // TODO: Implement GMS getDiscoveredDeviceIds
    return emptyList()
  }

  override suspend fun close() {}
}
