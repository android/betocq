package com.google.android.nearby.mobly.snippet.betocore

import com.google.android.mobly.snippet.Snippet

/**
 * Snippet class for GMS BeToCore APIs. Use this snippet only if this is GMS specific test, and not
 * shareable with other surfaces. If you are testing a shared API, please use BeToCoreSnippet
 * instead. Also, all methods should be named starting with "gms" prefix to avoid name collision.
 */
class GmsBeToCoreSnippet : Snippet {
  // TODO: clean up example methods
  /**
   * Example methods
   *
   * @AsyncRpc(description = "Starts advertising using GMS.") fun gmsStartBroadcast() { }
   * @AsyncRpc(description = "Starts discovery using GMS.") fun gmsStartDiscovery() { }
   */
  override fun shutdown() {}
}
