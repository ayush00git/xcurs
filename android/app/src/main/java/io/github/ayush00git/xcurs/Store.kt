package io.github.ayush00git.xcurs

import android.content.Context
import androidx.core.content.edit

/** The little the app remembers: the pairing, and the last address that worked. */
class Store(context: Context) {
    private val prefs = context.getSharedPreferences("xcurs", Context.MODE_PRIVATE)

    var token: String?
        get() = prefs.getString("token", null)
        set(value) = prefs.edit { putString("token", value) }

    var lastLaptop: Laptop?
        get() {
            val host = prefs.getString("host", null) ?: return null
            return Laptop(host, prefs.getInt("port", PairingCodec.DEFAULT_PORT))
        }
        set(value) = prefs.edit {
            if (value == null) {
                remove("host")
                remove("port")
            } else {
                putString("host", value.host)
                putInt("port", value.port)
            }
        }

    fun save(pairing: Pairing) {
        token = pairing.token
        lastLaptop = pairing.laptop
    }

    /** Forget the laptop. */
    fun forget() = prefs.edit {
        remove("token")
        remove("host")
        remove("port")
    }
}
