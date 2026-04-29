package com.google.android.nearby.mobly.snippet.betocore

import android.annotation.SuppressLint
import android.content.Context
import com.google.android.gms.nearby.betocore.NearbyCore
import com.google.android.gms.nearby.betocore.ffi.D2dClientV2
import com.google.android.gms.nearby.betocore.ffi.DiscoveredDeviceHandlerV2
import com.google.android.gms.nearby.betocore.ffi.DiscoveryConfigV2Ffi
import com.google.android.gms.nearby.betocore.ffi.RegisteredServiceV2
import com.google.android.gms.nearby.betocore.ffi.ServiceConfigV2Ffi
import com.google.android.mobly.snippet.event.EventCache
import com.google.android.mobly.snippet.event.SnippetEvent
import com.google.android.mobly.snippet.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

/** BeToCore adapter for Oxide Library. */
class OxideBeToCoreAdapter(context: Context) : IBeToCoreAdapter {
  @SuppressLint("GlobalCoroutineDispatchers") private val scope = CoroutineScope(Dispatchers.IO)
  private val d2dClientV2: D2dClientV2 by lazy { NearbyCore.createD2dClientV2(context) }

  private var registeredServiceV2: RegisteredServiceV2? = null
  private var discoveryHandlerV2: DiscoveredDeviceHandlerV2? = null
  private val discoveredDeviceIds = mutableListOf<String>()

  override fun registerService(config: ServiceConfigV2Ffi) {
    Log.d("Oxide registerService called with ${config.serviceId}")
    runBlocking {
      registeredServiceV2 = d2dClientV2.registerService(config)
      Log.d("Oxide registerService finished")
    }
  }

  override fun requestTemporaryPublicVisibility() {
    Log.d("Oxide requestTemporaryPublicVisibility called!")
    scope.launch {
      try {
        val receiver = registeredServiceV2?.requestTemporaryPublicVisibility()
        Log.d("Oxide requestTemporaryPublicVisibility finished. Waiting for expiration...")
        receiver?.waitForExpiration()
        Log.d("Oxide visibility expired")
      } catch (e: Exception) {
        Log.e("Oxide requestTemporaryPublicVisibility failed: ${e.message}")
      }
    }
  }

  override fun cancelTemporaryPublicVisibility() {
    Log.d("Oxide cancelTemporaryPublicVisibility called!")
    runBlocking {
      try {
        registeredServiceV2?.cancelTemporaryPublicVisibility()
        Log.d("Oxide cancelTemporaryPublicVisibility finished")
      } catch (e: Exception) {
        Log.e("Oxide cancelTemporaryPublicVisibility failed: ${e.message}")
      }
    }
  }

  override fun onWakeupObserved(timeoutSec: Long): Boolean {
    Log.d("Oxide onWakeupObserved called with timeout $timeoutSec seconds!")
    return runBlocking {
      kotlinx.coroutines.withTimeoutOrNull(timeoutSec * 1000L) {
        registeredServiceV2?.onWakeupObserved() ?: false
      } ?: false
    }
  }

  override fun unregisterService() {
    Log.d("Oxide unregisterService called!")
    runBlocking { registeredServiceV2?.unregister() }
    registeredServiceV2 = null
  }

  override fun startDiscovery(callbackEvent: SnippetEvent, discoveryConfig: DiscoveryConfigV2Ffi) {
    Log.d("Oxide startDiscovery called with ${discoveryConfig.serviceId}")
    scope.launch {
      discoveredDeviceIds.clear()
      val handler = d2dClientV2.startDiscovery(discoveryConfig)
      discoveryHandlerV2 = handler

      Log.d("Oxide startDiscovery handler received")
      try {
        while (true) {
          val devices = handler.waitForDiscoveredDevicesUpdate() ?: break
          Log.d("Oxide discovered devices update: ${devices.size}")
          for (device in devices) {
            val id = device.deviceInfo().id.toString()
            if (!discoveredDeviceIds.contains(id)) {
              discoveredDeviceIds.add(id)
              EventCache.getInstance().postEvent(callbackEvent)
            }
          }
        }
      } catch (e: Exception) {
        Log.e("Oxide discovery handler error: ${e.message}")
      }
    }
  }

  override fun stopDiscovery() {
    Log.d("Oxide stopDiscovery called!")
    runBlocking { discoveryHandlerV2?.stop() }
    discoveryHandlerV2 = null
  }

  override fun getDiscoveredDeviceIds() = discoveredDeviceIds.toList()

  private fun String.hexToByteArray(): ByteArray {
    return chunked(2).map { it.toInt(16).toByte() }.toByteArray()
  }

  override suspend fun close() {
    Log.d("Oxide close called!")
    registeredServiceV2?.unregister()
    registeredServiceV2 = null
    discoveryHandlerV2?.stop()
    discoveryHandlerV2 = null
    scope.cancel("OxideBeToCoreAdapter is being closed")
  }
}
