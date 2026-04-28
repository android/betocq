package com.google.android.nearby.mobly.snippet.betocore

import android.content.Context

/** BeToCore adapter for GMS Core API. */
class GmsBeToCoreAdapter(private val context: Context) : IBeToCoreAdapter {
  override suspend fun close() {}
}
