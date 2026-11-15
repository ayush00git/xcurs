package io.github.ayush00git.xcurs

import kotlin.math.sqrt

/**
 * Hears a triple knock on the back of the phone, from raw accelerometer samples.
 *
 * Pure Kotlin (no Android), so it can be unit-tested with synthetic signals.
 *
 * How it works:
 *  1. Gravity is a slow signal and a knock is a sharp one. A low-pass filter
 *     tracks gravity, and subtracting it leaves only fast motion (high-pass).
 *  2. A *spike* is fast motion above [threshold]. Anything above [maxSpike]
 *     is a drop or a slam, not a knock.
 *  3. A knock is an *impulse*: it rises above the threshold and falls back
 *     within [maxWidthMs]. Motion that stays high longer (a step, a shake)
 *     is not a knock, and it cancels any sequence in progress. Spikes closer
 *     than [minGapMs] count as the same knock still ringing.
 *  4. [knocks] spikes, each within [maxGapMs] of the previous one, make a
 *     triple knock.
 *  5. A sequence may only *start* while the phone is calm. That ignores
 *     walking, running and shaking, which spike all the time.
 */
class KnockDetector(
    private val knocks: Int = 3,
    private val threshold: Float = 1.8f,      // m/s², fast motion that counts as a spike
    private val maxSpike: Float = 25f,        // m/s², beyond this it's a drop, not a knock
    private val minGapMs: Long = 70,
    private val maxWidthMs: Long = 40,
    private val maxGapMs: Long = 550,
    private val calmLevel: Float = 0.6f,      // m/s², average motion allowed before knock one
    private val cooldownMs: Long = 1500,
    private val onKnocks: () -> Unit,
) {
    private var started = false
    private var lastT = 0L
    private var gx = 0f
    private var gy = 0f
    private var gz = 0f
    private var energy = 0f                   // running average of fast motion

    private var count = 0
    private var lastSpikeT = 0L
    private var cooldownUntil = 0L

    // the spike currently above the threshold, if any
    private var inSpike = false
    private var spikeStart = 0L
    private var spikePeak = 0f
    private var calmAtStart = false

    /** Feed one sample: time in ms, acceleration in m/s². Returns true on a triple knock. */
    fun onSample(tMs: Long, x: Float, y: Float, z: Float): Boolean {
        if (!started) {
            started = true
            lastT = tMs
            gx = x; gy = y; gz = z
            return false
        }
        val dt = (tMs - lastT).coerceIn(1L, 100L).toFloat()
        lastT = tMs

        // 1. gravity: low-pass with a ~100 ms time constant
        val a = dt / (GRAVITY_TAU_MS + dt)
        gx += (x - gx) * a
        gy += (y - gy) * a
        gz += (z - gz) * a
        val hx = x - gx
        val hy = y - gy
        val hz = z - gz
        val motion = sqrt(hx * hx + hy * hy + hz * hz)

        // 5. calm is judged on the motion *before* this sample
        val calm = energy < calmLevel
        energy += (motion - energy) * (dt / (ENERGY_TAU_MS + dt))

        if (motion >= threshold) {
            if (!inSpike) {
                inSpike = true
                spikeStart = tMs
                spikePeak = 0f
                calmAtStart = calm
            }
            spikePeak = maxOf(spikePeak, motion)
            if (tMs - spikeStart > maxWidthMs) count = 0  // 3. sustained motion, not a knock
            return false
        }
        if (!inSpike) {
            if (count > 0 && tMs - lastSpikeT > maxGapMs) count = 0  // 4. too slow: start over
            return false
        }

        // The spike just ended. Was it a knock?
        inSpike = false
        val width = tMs - spikeStart
        val t = spikeStart
        if (width > maxWidthMs || spikePeak > maxSpike) return false  // 3. / 2.
        if (t < cooldownUntil) return false
        if (count > 0 && t - lastSpikeT > maxGapMs) count = 0         // 4.
        if (count > 0 && t - lastSpikeT < minGapMs) return false      // 3. ringing
        if (count == 0 && !calmAtStart) return false                  // 5.

        count++
        lastSpikeT = t
        if (count < knocks) return false

        count = 0
        cooldownUntil = t + cooldownMs
        onKnocks()
        return true
    }

    private companion object {
        const val GRAVITY_TAU_MS = 100f
        const val ENERGY_TAU_MS = 250f
    }
}
