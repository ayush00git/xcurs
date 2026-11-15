package io.github.ayush00git.xcurs

import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService

/**
 * A Quick Settings tile ("xcurs knock") to switch the knock listener on/off.
 *
 * Turning it off is instant. Turning it on goes through the app, because
 * Android only lets a foreground service start from a visible screen, and
 * that's also where we ask for the permissions it needs.
 */
class KnockTileService : TileService() {

    override fun onStartListening() {
        val tile = qsTile ?: return
        val on = Store(this).knockEnabled
        tile.state = if (on) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = "xcurs knock"
        if (Build.VERSION.SDK_INT >= 29) tile.subtitle = if (on) "on" else "off"
        tile.updateTile()
    }

    override fun onClick() {
        if (Store(this).knockEnabled) {
            KnockService.stop(this)
            onStartListening()
            return
        }
        val setup = Intent(this, MainActivity::class.java)
            .setAction(MainActivity.ACTION_SETUP_KNOCK)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (Build.VERSION.SDK_INT >= 34) {
            startActivityAndCollapse(
                PendingIntent.getActivity(this, 0, setup, PendingIntent.FLAG_IMMUTABLE),
            )
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(setup)
        }
    }

    companion object {
        fun refresh(context: Context) =
            requestListeningState(context, ComponentName(context, KnockTileService::class.java))
    }
}
