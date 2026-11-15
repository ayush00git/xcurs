package io.github.ayush00git.xcurs

import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.app.AlertDialog
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.SystemClock
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.view.WindowManager
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.core.view.updatePadding
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning

/**
 * The whole app is one screen:
 *
 *   not paired  ->  "scan qr"  ->  saved
 *   paired      ->  find the laptop over mDNS (fall back to the last address)
 *               ->  load the laptop's own touchpad page in a full-screen WebView
 *
 * The touchpad UI is the same web page the browser shows, so every gesture
 * and effect stays in one place (xcurs/web on the laptop).
 */
class MainActivity : ComponentActivity() {

    private lateinit var store: Store
    private lateinit var discovery: Discovery

    private lateinit var web: WebView
    private lateinit var overlay: LinearLayout
    private lateinit var title: TextView
    private lateinit var subtitle: TextView
    private lateinit var primary: TextView
    private lateinit var secondary: TextView
    private var breathing: ObjectAnimator? = null

    private var pageReady = false
    private var loadFailed = false
    private var pausedAt = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        discovery = Discovery(this)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContentView(buildUi())
        connect()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (!pageReady) connect()
    }

    override fun onResume() {
        super.onResume()
        hideSystemBars()
        web.onResume()
        // Away for a while? The laptop may have a new IP by now: look again.
        if (pageReady && pausedAt > 0 && SystemClock.elapsedRealtime() - pausedAt > STALE_AFTER_MS) {
            connect()
        }
    }

    override fun onPause() {
        pausedAt = SystemClock.elapsedRealtime()
        web.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        discovery.stop()
        web.destroy()
        super.onDestroy()
    }

    // ---- flow --------------------------------------------------------------

    private fun connect() {
        val token = store.token ?: return autoPair()
        show("finding your laptop", breathe = true)
        discovery.find(token) { found ->
            if (found != null) store.lastLaptop = found
            val laptop = found ?: store.lastLaptop
            if (laptop == null) showNotFound() else open(laptop, token)
        }
    }

    private fun open(laptop: Laptop, token: String) {
        pageReady = false
        loadFailed = false
        web.loadUrl(PairingCodec.pageUrl(laptop, token))
    }

    private fun onPageReady() {
        pageReady = true
        stopBreathing()
        overlay.animate().alpha(0f).setDuration(FADE_MS).withEndAction {
            overlay.visibility = View.GONE
        }
        web.animate().alpha(1f).setDuration(FADE_MS)
    }

    /** First run: find any xcurs laptop on this Wi-Fi and ask it for the token. */
    private fun autoPair() {
        show("looking for your laptop", breathe = true)
        discovery.all { found ->
            if (found.isEmpty()) {
                showPairing("no laptop found\nrun xcurs on it, on the same wi-fi")
                return@all
            }
            AutoPair.tryAll(found.map { it.laptop }) { result ->
                when (result) {
                    is AutoPair.Result.Paired -> {
                        store.save(result.pairing)
                        connect()
                    }
                    AutoPair.Result.Closed -> showPairing(
                        "your laptop's pairing window is closed\nrestart xcurs there, then try again",
                    )
                    AutoPair.Result.Unreachable -> showPairing(
                        "found your laptop but can't reach it\nallow port 8710 in its firewall",
                    )
                }
            }
        }
    }

    private fun pair(text: String?) {
        val pairing = text?.let(PairingCodec::parse)
        if (pairing == null) {
            toast("That isn't an xcurs pairing link")
            return
        }
        store.save(pairing)
        connect()
    }

    private fun scan() {
        val options = GmsBarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
            .build()
        GmsBarcodeScanning.getClient(this, options).startScan()
            .addOnSuccessListener { pair(it.rawValue) }
            .addOnFailureListener { pasteDialog() }
    }

    private fun pasteDialog() {
        val clip = (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager)
            .primaryClip?.getItemAt(0)?.text?.toString().orEmpty()
        val input = EditText(this).apply {
            hint = "http://…:8710/#t=…"
            inputType = InputType.TYPE_TEXT_VARIATION_URI
            setText(clip.takeIf { "#t=" in it })
        }
        AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle("Paste the link xcurs printed")
            .setView(input)
            .setPositiveButton("Pair") { _, _ -> pair(input.text.toString()) }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // ---- screens -----------------------------------------------------------

    private fun showPairing(message: String) = show(
        message,
        primaryLabel = "try again", onPrimary = ::autoPair,
        secondaryLabel = "scan qr", onSecondary = ::scan,
    )

    private fun showNotFound() = show(
        "can't reach your laptop\nis xcurs running on the same wi-fi?",
        primaryLabel = "retry", onPrimary = ::connect,
        secondaryLabel = "pair again", onSecondary = {
            store.forget()
            autoPair()
        },
    )

    private fun show(
        message: String,
        breathe: Boolean = false,
        primaryLabel: String? = null,
        onPrimary: () -> Unit = {},
        secondaryLabel: String? = null,
        onSecondary: () -> Unit = {},
    ) {
        pageReady = false
        web.animate().cancel()
        web.alpha = 0f
        overlay.animate().cancel()
        overlay.visibility = View.VISIBLE
        overlay.animate().alpha(1f).setDuration(FADE_MS)

        subtitle.text = message
        // Room above the buttons only when there are buttons, so a lone
        // message sits exactly in the middle of the screen.
        val hasButtons = primaryLabel != null || secondaryLabel != null
        subtitle.updatePadding(bottom = if (hasButtons) 40.dp else 0)
        for ((button, label, action) in listOf(
            Triple(primary, primaryLabel, onPrimary),
            Triple(secondary, secondaryLabel, onSecondary),
        )) {
            button.visibility = if (label == null) View.GONE else View.VISIBLE
            button.text = label
            button.setOnClickListener { action() }
        }
        if (breathe) startBreathing() else stopBreathing()
    }

    private fun startBreathing() {
        if (breathing != null) return
        breathing = ObjectAnimator.ofFloat(subtitle, View.ALPHA, 0.6f, 0.2f).apply {
            duration = 1100
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            start()
        }
    }

    private fun stopBreathing() {
        breathing?.cancel()
        breathing = null
        subtitle.alpha = 0.6f
    }

    // ---- views -------------------------------------------------------------

    private fun buildUi(): View {
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }

        web = WebView(this).apply {
            setBackgroundColor(Color.BLACK)
            alpha = 0f
            overScrollMode = View.OVER_SCROLL_NEVER
            isVerticalScrollBarEnabled = false
            isHorizontalScrollBarEnabled = false
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true // the page keeps its settings in localStorage
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView, url: String) {
                    if (!loadFailed && url.startsWith("http")) onPageReady()
                }

                override fun onReceivedError(
                    view: WebView,
                    request: WebResourceRequest,
                    error: WebResourceError,
                ) {
                    if (request.isForMainFrame) {
                        loadFailed = true
                        showNotFound()
                    }
                }
            }
        }
        root.addView(web, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))

        title = TextView(this).apply {
            text = getString(R.string.app_name)
            setTextColor(Color.WHITE)
            textSize = 26f
            typeface = Typeface.create("sans-serif-thin", Typeface.NORMAL)
            letterSpacing = 0.55f
            balanceTracking()
        }
        subtitle = TextView(this).apply {
            setTextColor(Color.WHITE)
            alpha = 0.6f
            textSize = 12f
            letterSpacing = 0.12f
            gravity = Gravity.CENTER
            setLineSpacing(0f, 1.5f)
            setPadding(0, 18.dp, 0, 0)
            balanceTracking()
        }
        primary = pill(filled = true)
        secondary = pill(filled = false)

        overlay = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.BLACK)
            addView(title)
            addView(subtitle)
            addView(primary, pillParams())
            addView(secondary, pillParams())
        }
        root.addView(overlay, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        return root
    }

    private fun pill(filled: Boolean) = TextView(this).apply {
        gravity = Gravity.CENTER
        textSize = 12f
        letterSpacing = 0.3f
        isAllCaps = true
        setTextColor(if (filled) Color.BLACK else Color.WHITE)
        background = GradientDrawable().apply {
            cornerRadius = 100f.dp
            if (filled) setColor(Color.WHITE) else setStroke(1.dp, Color.argb(90, 255, 255, 255))
        }
        isClickable = true
        isFocusable = true
    }

    private fun pillParams() = LinearLayout.LayoutParams(220.dp, 48.dp).apply {
        topMargin = 12.dp
    }

    /**
     * Letter spacing is also added after the last letter, which pushes
     * tracked-out text left of centre. Pad the start by the same amount.
     */
    private fun TextView.balanceTracking() =
        updatePadding(left = (letterSpacing * textSize).toInt())

    private fun hideSystemBars() {
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    private fun toast(text: String) = Toast.makeText(this, text, Toast.LENGTH_SHORT).show()

    private val Int.dp: Int get() = (this * resources.displayMetrics.density).toInt()
    private val Float.dp: Float get() = this * resources.displayMetrics.density

    private companion object {
        const val FADE_MS = 450L
        const val STALE_AFTER_MS = 60_000L
    }
}
