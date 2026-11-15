package io.github.ayush00git.xcurs

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Turns the knock listener back on after a reboot or an app update, if it was on. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val relevant = intent.action == Intent.ACTION_BOOT_COMPLETED ||
            intent.action == Intent.ACTION_MY_PACKAGE_REPLACED
        if (relevant && Store(context).knockEnabled) KnockService.start(context)
    }
}
