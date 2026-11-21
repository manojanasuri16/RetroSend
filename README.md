# RetroSend

Send and receive photos, videos, music, any file and text messages between an **old Nokia phone** (S60 3rd Edition: N79, N82, N95, E71, 6120 and others) and the **[LocalSend](https://localsend.org) app** on Android, iPhone, Windows, macOS or Linux, over Wi-Fi.

RetroSend speaks the LocalSend v2 protocol, so the other device just runs the normal LocalSend app. No cable, no Bluetooth pairing and no PC in between.

| | |
|---|---|
| **Phones** | Nokia S60 3rd Edition (FP1/FP2), tested on a Nokia N79 |
| **Other side** | LocalSend on any platform, with **Encryption turned off** |
| **Network** | Both devices on the same Wi-Fi |

---

## Contents

- [Features](#features)
- [Install](#install)
- [Using RetroSend](#using-retrosend)
- [Troubleshooting](#troubleshooting)
- [Building from source](#building-from-source)
- [How it works](#how-it-works)
- [Project layout](#project-layout)
- [Credits](#credits)

---

## Features

- **Send** photos, videos, music, any file, or a text message to a LocalSend device.
- **Multi-select:** mark several files, even in different folders, and send them in one transfer.
- **Previews in the file picker:**
  - photos: the camera's built-in thumbnail (fast, even for 5 MP photos)
  - music: album art plus title, artist and album from the MP3's ID3 tags
  - videos: length and size, read from the MP4/3GP header
- **Receive** one or many files from LocalSend, with an Accept/Decline prompt (or auto-accept). Files are saved to `E:\RetroSend\`.
- **Receive text messages**, shown on screen.
- **Finds devices automatically:** LocalSend multicast announcements plus a sweep of the local network (needed on S60, see [How it works](#how-it-works)). You can also add a device by IP.
- **Send | Receive tabs**, native S60 look, works with the keypad.
- **No permission pop-ups:** it's a native app, so it gets its permissions once, at install, and it remembers your Wi-Fi network.

## Install

Download from the **[latest release](https://github.com/manojanasuri16/RetroSend/releases/latest)**:

- **`RetroSend_with_Python.sis`**: RetroSend **plus** Nokia's Python for S60 1.4.5 runtime, in one package. This is all you need.
- `RetroSend.sis`: the app alone, if Python for S60 1.4.5 is already installed.

On the phone:

1. **Menu → Applications → App. mgr. → Options → Settings**
   - *Software installation*: **All**
   - *Online certificate check*: **Off**
2. Copy the `.sis` to the phone (USB cable in *Mass storage* mode, Bluetooth, or a card reader). Open it in **File manager** and install.
3. You'll see **one** "untrusted supplier" warning, because RetroSend is self-signed. Accept it.
4. If it says **"Certificate expired"**, the culprit is Nokia's runtime certificate (it expired years ago). Set the phone's date to **2009**, install, then set the date back. RetroSend's own certificate is valid from 2008, so both install with the date set back.

> **Upgrading from an older test build?** If the install is refused, remove the old RetroSend first (*App. mgr. → RetroSend → Options → Remove*).

## Using RetroSend

### On the other device (once)
Open **LocalSend → Settings** and turn **Encryption off**. If "Require PIN" is on, turn it off too. Keep LocalSend open, on the same Wi-Fi as the phone.

### First start on the phone
RetroSend asks **once** which Wi-Fi network to use and remembers it. To change it later, go to *Options → Change Wi-Fi*.

### Send tab
- **Send a photo / video / music** opens the picker in `E:\Images`, `E:\Videos` or `E:\Music` (or a similar folder).
- **Send any file** lets you pick a drive and browse anywhere.
- **Send text message**
- **Devices** shows the devices found so far, a scan, or *Add by IP*.

**Picker keys:**

| Key | Action |
|---|---|
| Up / Down (or 2 / 8) | Move |
| Centre (or 5, or Right) | Open a folder, or mark/unmark a file |
| Left | Go up a folder |
| Options → **Send marked (N)** | Choose a device and send |
| Options → Mark all files here / Unmark all | |
| Right softkey | Back / cancel |

After *Send marked*, pick the device. If your device isn't listed, choose **Scan again** (this can take up to a minute) or **Enter IP address...** and type the IP shown in LocalSend.

### Receive tab
- Shows **Ready to receive**, your name, your IP (`192.168.x.x:53317`) and the save folder.
- **Open received files**: a picker over `E:\RetroSend\`, so you can pass files on to another device.
- **Auto-accept: ON/OFF**
- **Log**: what happened, useful for troubleshooting.

When someone sends you files, RetroSend lists them and asks you to **Accept**. Progress shows in the title bar.

### Closing
Use **Options → Exit**. On S60 the red key only hides an app. If RetroSend says *"already running in the background"*, hold the **Menu** key, select the other RetroSend and press **C**.

## Troubleshooting

| Problem | Fix |
|---|---|
| Other device not found | LocalSend open? **Encryption off**? Same Wi-Fi? Try *Scan again*, or *Enter IP address*. |
| Phone not found by the other device | In LocalSend, add the N79 manually with the IP shown on RetroSend's Receive tab. |
| "Create WLAN connection in offline mode?" | The phone is in the **Offline** profile. Answer Yes, or switch to **General**. |
| App pauses 1-2 s at start | That's the phone starting Wi-Fi (a blocking system call). Normal. |
| "Certificate expired" during install | Set the date to 2009, install, set it back. |
| "needs a PIN" | Turn off *Require PIN* in LocalSend. |
| Anything else | Open the **Log**, or read `E:\retrosend_log.txt` with the phone in Mass storage mode. It records every step and error. |

## Building from source

Tested on Linux (Manjaro). Needs `curl`, `git`, `python3` and `openssl`. Everything else is downloaded into `tools/` by the setup script. Nothing is installed system-wide.

```sh
tools/setup.sh                 # private Python 2.7, patched Ensymble, PyS60 runtime
pys60/build_sis.sh             # -> pys60/dist/RetroSend.sis, RetroSend_with_Python.sis, retrosend.py
sh pys60/tests/run.sh          # Python 2.2 syntax check + protocol, sweep, media and picker tests
```

`pys60/build_sis.sh` creates a self-signed certificate in `pys60/cert/` on first run. It's valid 2008-2037; see the install notes for why. Keep the key private: it's in `.gitignore`.

**Running without installing:** install Python for S60 and its *Script Shell*, copy `pys60/dist/retrosend.py` to `E:\Python\`, then *Python → Options → Run script*. Errors show on screen.

## How it works

RetroSend implements the receiving and sending parts of the **[LocalSend protocol v2](https://github.com/localsend/protocol)** over plain HTTP: `register`, `info`, `prepare-upload`, `upload` and `cancel`. Discovery is a UDP multicast announcement plus an HTTP sweep of the subnet. Text messages are a `text/plain` file with a `preview` field.

The native app targets **Python for S60 1.4.5** (Python 2.2.2, 2008), so the code avoids anything newer than Python 2.2 (`tools/check_py22.py` enforces this). Along the way it hit several PyS60 quirks, documented in **[docs/PYS60-NOTES.md](docs/PYS60-NOTES.md)**:

- Sockets only work on the **main thread**, through callbacks. A background thread has no Symbian active scheduler, and the app freezes. RetroSend is fully single-threaded and event-driven.
- `socket.close()` **stops the whole Wi-Fi connection** and closes the shared socket server, so RetroSend never closes sockets while running (it uses `shutdown()` instead).
- `bind(("", port))` fails. Use `"0.0.0.0"`.
- `accept()` reports a wrong peer address (`0.8.0.0`), and `getpeername()` isn't implemented. That's why devices are discovered by sweeping the network.
- `random.randint(0, 0x7fffffff)` overflows on Python 2.2.

## Project layout

```
pys60/                  native S60 app (Python for S60 1.4.5)
  retrosend.py          the app: protocol, async networking, UI, picker
  media.py              ID3 tags/album art and MP4 duration (pasted into the app at build time)
  build_sis.sh          builds RetroSend.sis and RetroSend_with_Python.sis
  icon.svg
  tests/                PC tests with stand-ins for the S60 modules (appuifw, e32, ...)
  tools/check_py22.py   rejects Python features newer than 2.2
tools/setup.sh          downloads the build tools
tools/ensymble-retrosend.patch   makes Ensymble work with current OpenSSL on Linux
docs/PYS60-NOTES.md     PyS60 pitfalls found while building this
```

## Credits

- [LocalSend](https://localsend.org) and its [protocol](https://github.com/localsend/protocol). RetroSend is an independent client, not affiliated with LocalSend.
- [Python for S60](https://sourceforge.net/projects/pys60/) by Nokia. `RetroSend_with_Python.sis` bundles Nokia's signed Python for S60 1.4.5 runtime unchanged.
- [Ensymble](https://github.com/essaic/ensymble) by Jussi Ylänen, for building SIS packages.
