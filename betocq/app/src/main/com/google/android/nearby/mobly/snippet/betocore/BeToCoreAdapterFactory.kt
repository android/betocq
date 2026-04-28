package com.google.android.nearby.mobly.snippet.betocore

import android.content.Context

/** Factory to create BeToCore adapters. */
object BeToCoreAdapterFactory {
  private const val GMS = "GMS"
  private const val MAINLINE = "MAINLINE"
  private const val OXIDE = "OXIDE"

  fun createAdapter(surface: String, context: Context): IBeToCoreAdapter {
    return when (surface) {
      GMS -> GmsBeToCoreAdapter(context)
      MAINLINE -> MainlineBeToCoreAdapter()
      OXIDE -> OxideBeToCoreAdapter(context)
      else -> throw IllegalArgumentException("Unknown BeToCore surface: $surface")
    }
  }
}
