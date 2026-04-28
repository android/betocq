package com.google.android.nearby.mobly.snippet.betocore

import androidx.test.platform.app.InstrumentationRegistry
import com.google.android.mobly.snippet.Snippet
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

  override fun shutdown() {
    runBlocking { adapter?.close() }
  }
}
