# xcurs

Your phone, as a touchpad for your Linux laptop.

xcurs runs a tiny daemon on the laptop that creates a virtual mouse through the
kernel's `uinput` module, and serves a touchpad page you open on your phone.
Because it talks to the kernel instead of the display server, it works the same
on X11 and Wayland, on any distro.
