package io.github.ayush00git.xcurs

import android.os.Build
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * V2.4: pairing without a QR code.
 *
 * For a short while after xcurs starts on the laptop (its "pairing window"),
 * `POST /pair` answers with the token. We ask every laptop we found, in turn,
 * and keep the first one that says yes.
 */
object AutoPair {
    sealed interface Result {
        data class Paired(val pairing: Pairing) : Result
        /** Laptops answered, but none has its pairing window open. */
        data object Closed : Result
        /** No laptop could be reached at all. */
        data object Unreachable : Result
    }

    private val io = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    fun tryAll(laptops: List<Laptop>, onResult: (Result) -> Unit) {
        io.execute {
            var anyAnswered = false
            var result: Result? = null
            for (laptop in laptops) {
                when (val token = request(laptop)) {
                    null -> {}
                    CLOSED -> anyAnswered = true
                    else -> {
                        result = Result.Paired(Pairing(token, laptop))
                        break
                    }
                }
            }
            val final = result ?: if (anyAnswered) Result.Closed else Result.Unreachable
            main.post { onResult(final) }
        }
    }

    /** The token, [CLOSED] if the laptop said no, or null if it didn't answer. */
    private fun request(laptop: Laptop): String? {
        val conn = URL("http://${laptop.authority}/pair").openConnection() as HttpURLConnection
        return try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 2500
            conn.readTimeout = 2500
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            val body = JSONObject().put("name", deviceName()).toString()
            conn.outputStream.use { it.write(body.toByteArray()) }
            when (conn.responseCode) {
                200 -> parseToken(conn.inputStream.bufferedReader().use { it.readText() })
                403 -> CLOSED
                else -> null
            }
        } catch (_: Exception) {
            null
        } finally {
            conn.disconnect()
        }
    }

    private fun parseToken(json: String): String? =
        try {
            JSONObject(json).getString("token")
        } catch (_: Exception) {
            null
        }

    private fun deviceName(): String {
        val maker = Build.MANUFACTURER.replaceFirstChar { it.uppercase() }
        return if (Build.MODEL.startsWith(maker, ignoreCase = true)) Build.MODEL else "$maker ${Build.MODEL}"
    }

    private const val CLOSED = "\u0000closed"
}
