package io.github.ayush00git.xcurs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PairingCodecTest {

    @Test
    fun parsesTheQrUrl() {
        val p = PairingCodec.parse("http://192.168.1.20:8710/#t=AbC-d_9")!!
        assertEquals("AbC-d_9", p.token)
        assertEquals(Laptop("192.168.1.20", 8710), p.laptop)
    }

    @Test
    fun defaultsThePort() {
        assertEquals(8710, PairingCodec.parse("http://10.0.0.5/#t=x")!!.laptop.port)
    }

    @Test
    fun handlesIpv6() {
        val p = PairingCodec.parse("http://[fe80::1]:9000/#t=x")!!
        assertEquals("fe80::1", p.laptop.host)
        assertEquals("http://[fe80::1]:9000/#t=x", PairingCodec.pageUrl(p.laptop, "x"))
    }

    @Test
    fun rejectsJunk() {
        assertNull(PairingCodec.parse("hello"))
        assertNull(PairingCodec.parse("http://192.168.1.20:8710/"))      // no token
        assertNull(PairingCodec.parse("ftp://192.168.1.20/#t=x"))        // wrong scheme
        assertNull(PairingCodec.parse("http://192.168.1.20/#t=<script>")) // bad token chars
    }

    @Test
    fun pairingIdMatchesTheLaptop() {
        // Same value xcurs/beacon.py computes: sha256("s3cret").hexdigest()[:16]
        assertEquals("1ec1c26b50d5d3c5", PairingCodec.pairingId("s3cret"))
        assertEquals("", PairingCodec.pairingId("")) // a laptop running --no-auth
    }
}
