package io.github.ayush00git.xcurs

import java.net.URI
import java.security.MessageDigest

/** Where the laptop's daemon listens. */
data class Laptop(val host: String, val port: Int) {
    /** IPv6 literals need brackets inside a URL. */
    val authority: String get() = if (':' in host) "[$host]:$port" else "$host:$port"
}

/** What the QR code gives us: the secret token, and where the laptop was. */
data class Pairing(val token: String, val laptop: Laptop)

/**
 * Pure logic, no Android imports, so it runs in plain JVM unit tests.
 */
object PairingCodec {
    const val DEFAULT_PORT = 8710
    private val TOKEN = Regex("""(?:^|&)t=([A-Za-z0-9_-]+)""")

    /** Parses the QR's URL, e.g. `http://192.168.1.20:8710/#t=AbC...`. */
    fun parse(text: String): Pairing? {
        val uri = try {
            URI(text.trim())
        } catch (_: Exception) {
            return null
        }
        if (uri.scheme != "http" && uri.scheme != "https") return null
        val host = uri.host?.removeSurrounding("[", "]") ?: return null
        val port = if (uri.port > 0) uri.port else DEFAULT_PORT
        val token = TOKEN.find(uri.rawFragment ?: return null)?.groupValues?.get(1) ?: return null
        return Pairing(token, Laptop(host, port))
    }

    /**
     * The fingerprint the laptop announces over mDNS (see xcurs/beacon.py):
     * sha256 of the token, first 16 hex chars. Matching it tells us which
     * laptop on the network is ours, without the token ever being broadcast.
     */
    fun pairingId(token: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(token.toByteArray())
            .joinToString("") { "%02x".format(it) }
            .take(16)

    /** The touchpad page. The token rides after '#', so it never reaches server logs. */
    fun pageUrl(laptop: Laptop, token: String): String = "http://${laptop.authority}/#t=$token"
}
