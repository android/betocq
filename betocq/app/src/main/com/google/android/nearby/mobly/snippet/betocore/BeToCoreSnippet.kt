package com.google.android.nearby.mobly.snippet.betocore

import androidx.test.platform.app.InstrumentationRegistry
import com.google.android.gms.nearby.betocore.ffi.AttestationProfileFfi
import com.google.android.gms.nearby.betocore.ffi.AuthenticationPolicyFfi
import com.google.android.gms.nearby.betocore.ffi.DiscoveryConfigV2Ffi
import com.google.android.gms.nearby.betocore.ffi.PinComparisonFfi
import com.google.android.gms.nearby.betocore.ffi.ServiceConfigV2Ffi
import com.google.android.gms.nearby.betocore.ffi.ServiceIdV2Ffi
import com.google.android.gms.nearby.betocore.ffi.VisibilityScopeV2Ffi
import com.google.android.mobly.snippet.Snippet
import com.google.android.mobly.snippet.event.SnippetEvent
import com.google.android.mobly.snippet.rpc.AsyncRpc
import com.google.android.mobly.snippet.rpc.Rpc
import kotlinx.coroutines.runBlocking

/** Snippet class for BeToCore APIs. */
class BeToCoreSnippet : Snippet {
  private val context = InstrumentationRegistry.getInstrumentation().targetContext
  private var adapter: IBeToCoreAdapter? = null

  private fun getAdapter(): IBeToCoreAdapter {
    return checkNotNull(adapter) { "setBeToCoreApiSurface must be called first." }
  }

  @Rpc(description = "Sets the BeToCore API surface to use (e.g., GMS, MAINLINE, OXIDE).")
  fun setBeToCoreApiSurface(surface: String) {
    adapter = BeToCoreAdapterFactory.createAdapter(surface, context)
  }

  // TODO: update the interface to support testing other configs.
  @Rpc(description = "Registers a service.")
  fun registerService(serviceId: String) {
    val serviceIdFfi =
      ServiceIdV2Ffi(serviceId.chunked(2).map { it.toInt(16).toByte() }.toByteArray())
    val config =
      ServiceConfigV2Ffi(
        serviceId = serviceIdFfi,
        visibilityScope = VisibilityScopeV2Ffi.EVERYONE,
        authorizationPolicy =
          AuthenticationPolicyFfi(AttestationProfileFfi.NONE, PinComparisonFfi.NotAllowed),
        useUnsolicitedBroadcast = true,
        serviceSpecificInfo = null,
      )
    getAdapter().registerService(config)
  }

  @Rpc(description = "Requests temporary public visibility for service.")
  fun requestTemporaryPublicVisibility() {
    getAdapter().requestTemporaryPublicVisibility()
  }

  @Rpc(description = "Cancels temporary public visibility for service.")
  fun cancelTemporaryPublicVisibility() {
    getAdapter().cancelTemporaryPublicVisibility()
  }

  @Rpc(description = "Waits until wakeup is observed for service.")
  fun onWakeupObserved(timeoutSec: Long): Boolean {
    return getAdapter().onWakeupObserved(timeoutSec)
  }

  @Rpc(description = "Unregisters the service.")
  fun unregisterService() {
    getAdapter().unregisterService()
  }

  @AsyncRpc(description = "Starts discovery for the service.")
  fun startDiscovery(callbackId: String, serviceId: String) {
    val serviceIdFfi =
      ServiceIdV2Ffi(serviceId.chunked(2).map { it.toInt(16).toByte() }.toByteArray())
    val config = DiscoveryConfigV2Ffi(serviceIdFfi, VisibilityScopeV2Ffi.EVERYONE)
    getAdapter().startDiscovery(SnippetEvent(callbackId, "onDeviceDiscovered"), config)
  }

  @Rpc(description = "Stops the discovery.")
  fun stopDiscovery() {
    getAdapter().stopDiscovery()
  }

  @Rpc(description = "Gets the discovery results.")
  fun getDiscoveredDeviceIds(): List<String> {
    return getAdapter().getDiscoveredDeviceIds()
  }

  override fun shutdown() {
    runBlocking { adapter?.close() }
  }
}
