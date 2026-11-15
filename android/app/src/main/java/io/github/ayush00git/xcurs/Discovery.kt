package io.github.ayush00git.xcurs

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Handler
import android.os.Looper

/** One xcurs laptop seen on the network, and the fingerprint it announced. */
data class Found(val laptop: Laptop, val pid: String)

/**
 * Finds xcurs laptops on the Wi-Fi with mDNS / DNS-SD (Android calls it NSD).
 *
 * 1. Browse for services of type `_xcurs._tcp`.
 * 2. Resolve each one to get its address, port and TXT records (`pid`).
 *
 * Callbacks run on the main thread, exactly once per search.
 */
class Discovery(context: Context) {
    private val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val main = Handler(Looper.getMainLooper())

    private var listener: NsdManager.DiscoveryListener? = null
    private var done = true

    // NsdManager.resolveService handles one request at a time, so queue them.
    private val pending = ArrayDeque<NsdServiceInfo>()
    private var resolving = false

    /** Our paired laptop: the one whose `pid` matches the token, or null. */
    fun find(token: String, timeoutMs: Long = 4000, onResult: (Laptop?) -> Unit) {
        val wanted = PairingCodec.pairingId(token)
        browse(timeoutMs, stopWhen = { it.pid == wanted }) { all ->
            onResult(all.firstOrNull { it.pid == wanted }?.laptop)
        }
    }

    /** Every xcurs laptop that answers within [timeoutMs] (for first-time pairing). */
    fun all(timeoutMs: Long = 2500, onResult: (List<Found>) -> Unit) =
        browse(timeoutMs, stopWhen = { false }, onDone = onResult)

    private fun browse(timeoutMs: Long, stopWhen: (Found) -> Boolean, onDone: (List<Found>) -> Unit) {
        stop()
        done = false
        val found = mutableListOf<Found>()

        fun finish() {
            main.post {
                if (done) return@post
                done = true
                stop()
                onDone(found.distinctBy { it.laptop })
            }
        }

        lateinit var resolveNext: () -> Unit

        @Suppress("DEPRECATION") // resolveService works on every API level we support
        fun resolve(info: NsdServiceInfo) {
            resolving = true
            nsd.resolveService(info, object : NsdManager.ResolveListener {
                override fun onResolveFailed(info: NsdServiceInfo, error: Int) {
                    main.post {
                        resolving = false
                        resolveNext()
                    }
                }

                override fun onServiceResolved(info: NsdServiceInfo) {
                    // Strip any "%wlan0" scope suffix from IPv6 addresses.
                    val address = info.host?.hostAddress?.substringBefore('%')
                    val pid = info.attributes["pid"]?.let { String(it) }.orEmpty()
                    main.post {
                        resolving = false
                        if (done) return@post
                        if (address != null) {
                            val f = Found(Laptop(address, info.port), pid)
                            found += f
                            if (stopWhen(f)) return@post finish()
                        }
                        resolveNext()
                    }
                }
            })
        }

        resolveNext = {
            if (!done && !resolving) pending.removeFirstOrNull()?.let(::resolve)
        }

        val l = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {}
            override fun onDiscoveryStopped(serviceType: String) {}
            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                finish()
            }
            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
            override fun onServiceLost(info: NsdServiceInfo) {}
            override fun onServiceFound(info: NsdServiceInfo) {
                main.post {
                    pending.addLast(info)
                    resolveNext()
                }
            }
        }
        listener = l
        nsd.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, l)
        main.postDelayed({ finish() }, timeoutMs)
    }

    fun stop() {
        listener?.let {
            try {
                nsd.stopServiceDiscovery(it)
            } catch (_: IllegalArgumentException) {
                // already stopped
            }
        }
        listener = null
        pending.clear()
        resolving = false
        main.removeCallbacksAndMessages(null)
    }

    private companion object {
        const val SERVICE_TYPE = "_xcurs._tcp"
    }
}
