package com.google.android.nearby.mobly.snippet.betocore

import com.google.android.gms.nearby.betocore.ffi.DiscoveryConfigV2Ffi
import com.google.android.gms.nearby.betocore.ffi.ServiceConfigV2Ffi
import com.google.android.mobly.snippet.event.SnippetEvent

/** Defines a unified contract for all BeToCore operations. */
interface IBeToCoreAdapter {
  fun registerService(config: ServiceConfigV2Ffi)

  fun requestTemporaryPublicVisibility()

  fun cancelTemporaryPublicVisibility()

  fun onWakeupObserved(timeoutSec: Long): Boolean

  fun unregisterService()

  fun startDiscovery(callbackEvent: SnippetEvent, discoveryConfig: DiscoveryConfigV2Ffi)

  fun stopDiscovery()

  fun getDiscoveredDeviceIds(): List<String>

  /** Clean up resources on close. */
  suspend fun close()
}
