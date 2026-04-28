package com.google.android.nearby.mobly.snippet.betocore


/** Defines a unified contract for all BeToCore operations. */
interface IBeToCoreAdapter {
  /** Clean up resources on close. */
  suspend fun close()
}
