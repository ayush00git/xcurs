package io.github.ayush00git.xcurs

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.provider.Settings
import androidx.core.content.ContextCompat

/**
 * Listens for a triple knock on the back of the phone and opens xcurs.
 *
 * Android only lets an app keep working in the background as a *foreground
 * service*, which must show a notification for as long as it runs. To save
 * battery the sensor is only on while the screen is on: a knock in your
 * pocket shouldn't wake anything.
 */
class KnockService : Service(), SensorEventListener {

    private lateinit var sensors: SensorManager
    private var accelerometer: Sensor? = null
    private var listening = false
    private val detector = KnockDetector(onKnocks = ::onTripleKnock)

    private val screen = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                Intent.ACTION_SCREEN_ON -> listen(true)
                Intent.ACTION_SCREEN_OFF -> listen(false)
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        sensors = getSystemService(SENSOR_SERVICE) as SensorManager
        accelerometer = sensors.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        createChannels(this)
        goForeground()
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_SCREEN_ON)
            addAction(Intent.ACTION_SCREEN_OFF)
        }
        ContextCompat.registerReceiver(this, screen, filter, ContextCompat.RECEIVER_NOT_EXPORTED)
        listen((getSystemService(POWER_SERVICE) as PowerManager).isInteractive)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            Store(this).knockEnabled = false
            KnockTileService.refresh(this)
            stopSelf()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    override fun onDestroy() {
        listen(false)
        unregisterReceiver(screen)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun listen(on: Boolean) {
        val sensor = accelerometer ?: return
        if (on == listening) return
        listening = on
        if (on) {
            // 5000 µs = 200 Hz, fast enough to catch a knock (~10 ms) and the
            // fastest rate apps may use without a special permission.
            sensors.registerListener(this, sensor, SAMPLING_PERIOD_US)
        } else {
            sensors.unregisterListener(this)
        }
    }

    override fun onSensorChanged(event: SensorEvent) {
        val v = event.values
        detector.onSample(event.timestamp / 1_000_000, v[0], v[1], v[2]) // ns -> ms
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun onTripleKnock() {
        buzz()
        val open = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
        if (Settings.canDrawOverlays(this)) {
            // "Display over other apps" is what lets a background app open a
            // screen on Android 10+. Without it, fall back to a notification.
            startActivity(open)
        } else {
            val tap = PendingIntent.getActivity(this, 1, open, PendingIntent.FLAG_IMMUTABLE)
            val n = Notification.Builder(this, CHANNEL_KNOCK)
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle("Knock knock")
                .setContentText("Tap to open xcurs")
                .setContentIntent(tap)
                .setAutoCancel(true)
                .setTimeoutAfter(10_000)
                .build()
            getSystemService(NotificationManager::class.java).notify(NOTIFY_KNOCK, n)
        }
    }

    private fun buzz() {
        val vibrator = if (Build.VERSION.SDK_INT >= 31) {
            getSystemService(VibratorManager::class.java).defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            getSystemService(Vibrator::class.java)
        }
        vibrator.vibrate(VibrationEffect.createOneShot(28, VibrationEffect.DEFAULT_AMPLITUDE))
    }

    private fun goForeground() {
        val stop = PendingIntent.getService(
            this, 0,
            Intent(this, KnockService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        val n = Notification.Builder(this, CHANNEL_LISTENING)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle("Knock three times to open xcurs")
            .setContentIntent(open)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(null, "Turn off", stop).build())
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIFY_LISTENING, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFY_LISTENING, n)
        }
    }

    companion object {
        private const val ACTION_STOP = "io.github.ayush00git.xcurs.STOP_KNOCK"
        private const val CHANNEL_LISTENING = "listening"
        private const val CHANNEL_KNOCK = "knock"
        private const val NOTIFY_LISTENING = 1
        private const val NOTIFY_KNOCK = 2
        private const val SAMPLING_PERIOD_US = 5_000

        fun start(context: Context) {
            Store(context).knockEnabled = true
            ContextCompat.startForegroundService(context, Intent(context, KnockService::class.java))
            KnockTileService.refresh(context)
        }

        fun stop(context: Context) {
            Store(context).knockEnabled = false
            context.stopService(Intent(context, KnockService::class.java))
            KnockTileService.refresh(context)
        }

        private fun createChannels(context: Context) {
            val nm = context.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_LISTENING, "Knock listener", NotificationManager.IMPORTANCE_MIN)
                    .apply { setShowBadge(false) },
            )
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_KNOCK, "Knock heard", NotificationManager.IMPORTANCE_HIGH),
            )
        }
    }
}
