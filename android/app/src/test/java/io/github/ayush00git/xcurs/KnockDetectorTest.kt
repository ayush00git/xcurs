package io.github.ayush00git.xcurs

import org.junit.Assert.assertEquals
import org.junit.Test
import kotlin.math.PI
import kotlin.math.sin
import kotlin.random.Random

/**
 * Feeds synthetic 200 Hz accelerometer signals: a phone lying still (gravity
 * on z plus a little sensor noise), with knocks and motion added on top.
 */
class KnockDetectorTest {

    private val rate = 5L // ms per sample (200 Hz)

    private fun run(
        durationMs: Long,
        knocksAt: List<Long> = emptyList(),
        knockSize: Float = 4f,
        walking: Boolean = false,
    ): Int {
        var fired = 0
        val d = KnockDetector { fired++ }
        val rnd = Random(7)
        var t = 0L
        while (t <= durationMs) {
            var x = rnd.nextFloat() * 0.1f - 0.05f
            var y = rnd.nextFloat() * 0.1f - 0.05f
            var z = 9.81f + rnd.nextFloat() * 0.1f - 0.05f
            if (walking) {
                val s = 3f * sin(2 * PI * 2.0 * t / 1000.0).toFloat() // 2 steps a second
                x += s; y += s * 0.5f; z += s
            }
            // A knock: a sharp push, a rebound, then a small ring.
            for (k in knocksAt) {
                when (t - k) {
                    0L -> z += knockSize
                    5L -> z -= knockSize * 0.6f
                    10L -> z += knockSize * 0.25f
                }
            }
            d.onSample(t, x, y, z)
            t += rate
        }
        return fired
    }

    @Test
    fun tripleKnockFires() = assertEquals(1, run(2500, listOf(1000, 1250, 1500)))

    @Test
    fun twoKnocksDoNothing() = assertEquals(0, run(2500, listOf(1000, 1250)))

    @Test
    fun knocksTooFarApartDoNothing() = assertEquals(0, run(4000, listOf(1000, 1700, 2400)))

    @Test
    fun stillPhoneNeverFires() = assertEquals(0, run(10_000))

    @Test
    fun walkingNeverFires() = assertEquals(0, run(10_000, walking = true))

    @Test
    fun knocksWhileWalkingAreIgnored() =
        assertEquals(0, run(4000, listOf(2000, 2250, 2500), walking = true))

    @Test
    fun aDropIsNotAKnock() = assertEquals(0, run(2500, listOf(1000, 1250, 1500), knockSize = 40f))

    @Test
    fun sixKnocksFireOnceThanksToCooldown() =
        assertEquals(1, run(3500, listOf(1000, 1250, 1500, 1750, 2000, 2250)))

    @Test
    fun canFireAgainAfterCooldown() =
        assertEquals(2, run(6000, listOf(1000, 1250, 1500, 4000, 4250, 4500)))
}
