package io.github.ayush00git.xcurs

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Handler
import android.os.Looper

/**
 * Finds our laptop on the Wi-Fi with mDNS / DNS-SD (Android calls it NSD).
 *
 * 1. Browse for services of type `_xcurs._tcp`.
 * 2. Resolve each one to get its address, port and TXT records.
 * 3. Keep the one whose `pid` TXT record matches our token's fingerprint.
 *
 * [onResult] is called exactly once, on the main thread: with the laptop, or
 * with null if nothing matched before [timeoutMs].
 */
class Discovery(context: Context) {
    private val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val main = Handler(Looper.getMainLooper())

    private var listener: NsdManager.DiscoveryListener? = null
    private var done = true

    // NsdManager.resolveService handles one request at a time, so queue them.
    private val pending = ArrayDeque<NsdServiceInfo>()
    private var resolving = false

    fun find(token: String, timeoutMs: Long = 4000, onResult: (Laptop?) -> Unit) {
        stop()
        done = false
        val wanted = PairingCodec.pairingId(token)

        fun finish(laptop: Laptop?) {
            main.post {
                if (done) return@post
                done = true
                stop()
                onResult(laptop)
            }
        }

        lateinit var resolveNext: () -> Unit

        @Suppress("DEPRECATION") // resolveService works on every API level we support
        fun resolve(info: NsdServiceInfo) {
            resolving = true
            nsd.resolveService(info, object : NsdManager.ResolveListener {
                override fun onResolveFailed(info: NsdServiceInfo, error: Int) {
                    resolving = false
                    main.post { resolveNext() }
                }

                override fun onServiceResolved(info: NsdServiceInfo) {
                    resolving = false
                    val pid = info.attributes["pid"]?.let { String(it) }
                    val host = info.host
                    if (pid == wanted && host != null) {
                        // Strip any "%wlan0" scope suffix from IPv6 addresses.
                        val address = host.hostAddress?.substringBefore('%')
                        if (address != null) {
                            finish(Laptop(address, info.port))
                            return
                        }
                    }
                    main.post { resolveNext() }
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
                finish(null)
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
        main.postDelayed({ finish(null) }, timeoutMs)
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
        main.removeCallbacksAndMessages(null)
    }

    private companion object {
        const val SERVICE_TYPE = "_xcurs._tcp"
    }
}

