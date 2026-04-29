package com.google.android.nearby.mobly.snippet.betocore

import com.google.android.gms.nearby.betocore.ffi.DiscoveryConfigV2Ffi
import com.google.android.gms.nearby.betocore.ffi.ServiceConfigV2Ffi
import com.google.android.mobly.snippet.event.SnippetEvent
import com.google.android.mobly.snippet.util.Log

/** BeToCore adapter for Mainline Module API. */
class MainlineBeToCoreAdapter : IBeToCoreAdapter {

  override fun registerService(config: ServiceConfigV2Ffi) {
    Log.d("Mainline registerService called")
    // TODO: Implement Mainline registerService
  }

  override fun requestTemporaryPublicVisibility() {
    Log.d("Mainline requestTemporaryPublicVisibility called")
    // TODO: Implement Mainline requestTemporaryPublicVisibility
  }

  override fun cancelTemporaryPublicVisibility() {
    Log.d("Mainline cancelTemporaryPublicVisibility called")
    // TODO: Implement Mainline cancelTemporaryPublicVisibility
  }

  override fun onWakeupObserved(timeoutSec: Long): Boolean {
    Log.d("Mainline onWakeupObserved called with timeout $timeoutSec")
    // TODO: Implement Mainline onWakeupObserved
    return false
  }

  override fun unregisterService() {
    Log.d("Mainline unregisterService called")
    // TODO: Implement Mainline unregisterService
  }

  override fun startDiscovery(callbackEvent: SnippetEvent, discoveryConfig: DiscoveryConfigV2Ffi) {
    Log.d("Mainline startDiscovery called")
    // TODO: Implement Mainline startDiscovery
  }

  override fun stopDiscovery() {
    Log.d("Mainline stopDiscovery called")
    // TODO: Implement Mainline stopDiscovery
  }

  override fun getDiscoveredDeviceIds(): List<String> {
    // TODO: Implement Mainline getDiscoveredDeviceIds
    return emptyList()
  }

  override suspend fun close() {}
}
