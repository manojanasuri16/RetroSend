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
- **Send a whole folder:** the folder structure is kept on the other device (`Album/song.mp3`).
- **Photo grid:** "Send a photo" opens a thumbnail grid (switch to the list view in Options).
- **Send contacts:** pick contacts and send them as a `.vcf` file.
- **Browser sharing:** turn it on, and any phone or PC on the Wi-Fi can open `http://<phone-ip>:53317/` in a normal browser to download the files you shared or upload files and text to the phone. No app needed on the other side.
- **Previews in the file picker:**
  - photos: the camera's built-in thumbnail (fast, even for 5 MP photos)
  - music: album art plus title, artist and album from the MP3's ID3 tags
  - videos: length and size, read from the MP4/3GP header
- **Receive** one or many files from LocalSend, with an Accept/Decline prompt (or auto-accept). Photos, music and videos are saved to `E:\Images`, `E:\Music` and `E:\Videos`, so Gallery and the Music player find them. Everything else goes to `E:\RetroSend\` (the sorting can be switched off).
- **Open received files** in the phone's own viewer or player, straight from RetroSend.
- **Cancel sending / Stop receiving** from the Options menu, at any time during a transfer.
- **Speed and time left** in the title bar while sending or receiving (e.g. `45% 120 KB/s 0:32 left`).
- **Remembers devices:** devices you've used are listed right away after a restart, and their addresses are re-checked automatically.
- **Receive text messages**, shown on screen.
- **Finds devices automatically:** remembered devices are re-checked at start. New LocalSend devices are located with a fast UDP search, about 12 seconds (needed on S60, see [How it works](#how-it-works)). You can also add a device by IP.
- **Send | Receive tabs** with two-line items (a short hint under each), native S60 look, works with the keypad.
- **Transfer screen:** a full-screen progress bar with file name, file N of M, size, speed and time left, plus Cancel. It ends with a clear done/failed result.
- **Easy repeat sends:** the device you sent to last is listed first.
- **No permission pop-ups:** it's a native app, so it gets its permissions once, at install, and it remembers your Wi-Fi network.

## Install

Download from the **[latest release](https://github.com/manojanasuri16/RetroSend/releases/latest)**:

- **`PythonForS60_1_4_5_3rdEd.sis`**: Nokia's Python for S60 1.4.5 runtime (unchanged). Install it **once**.
- **`RetroSend-<version>-S60v3.sis`**: the app. Install it after Python, and install each new version over the old one.
- `retrosend-<version>.py`: the same app as a single script, to run from the Python Script Shell (useful for seeing errors).
- `SHA256SUMS.txt`: checksums.

On the phone:

1. **Menu → Applications → App. mgr. → Options → Settings**
   - *Software installation*: **All**
   - *Online certificate check*: **Off**
2. Copy the files to the phone (USB cable in *Mass storage* mode, Bluetooth, or a card reader). Open them in **File manager**.
3. Install **`PythonForS60_1_4_5_3rdEd.sis`** first. If it says **"Certificate expired"** (Nokia's certificate is old), set the phone's date to **2009**, install, then set the date back.
4. Install **`RetroSend-<version>-S60v3.sis`**. You'll see **one** "untrusted supplier" warning, because RetroSend is self-signed. Accept it.

> **If RetroSend (or any Python app) does nothing when you open it,** the Python runtime is missing or damaged. Releases 1.0.0 to 1.1.1 offered a combined "with-Python" package, which could remove Python when it was replaced. Remove RetroSend and Python for S60 in App. mgr., then install Python and RetroSend again as above.

## Using RetroSend

### On the other device (once)
Open **LocalSend → Settings** and turn **Encryption off**. If "Require PIN" is on, turn it off too. Keep LocalSend open, on the same Wi-Fi as the phone.

### First start on the phone
RetroSend asks **once** which Wi-Fi network to use and remembers it. To change it later, go to *Options → Change Wi-Fi*.

### Send tab
- **Send a photo** opens a thumbnail grid of `E:\Images`. **Send a video / music** opens the list picker in `E:\Videos` or `E:\Music`.
- **Send any file or folder** lets you pick a drive and browse anywhere. Use *Options → Mark whole folder* to send a folder.
- **Send contacts**: tick contacts, then pick a device. They're sent as a `.vcf` file.
- **Send text message**
- **Share files to a browser**: pick files that browsers may download (see Browser sharing below).
- **Devices** shows known and found devices, a scan, *Add by IP*, and *Forget this device*.

**Picker keys:**

| Key | Action |
|---|---|
| Up / Down (or 2 / 8) | Move |
| Centre (or 5, or Right) | Open a folder, or mark/unmark a file |
| Left | Go up a folder |
| Options → **Send marked (N)** | Choose a device and send |
| Options → Open file | Opens it in the phone's viewer or player |
| Options → Mark whole folder | Marks every file in the selected folder |
| Options → Mark all files here / Unmark all | |
| Options → Grid view / List view | Switch between the photo grid and the list |
| Right softkey | Back / cancel |

After *Send marked*, pick the device. If your device isn't listed, choose **Scan again** (finding a new device takes about 12 seconds) or **Enter IP address...** and type the IP shown in LocalSend.

### Receive tab
- Shows **Ready to receive**, your name (select it to rename), and your IP (`192.168.x.x:53317`).
- **Received files**: the last 30 received files. Open one, send it on, or show it in its folder.
- **Browse received folder**: the picker over `E:\RetroSend\`. The centre key opens a file.
- **Auto-accept: ON/OFF**
- **Sort into Images/Music/Videos: ON/OFF**
- **Browser sharing: ON/OFF**: shows the address to open in a browser when it's on.
- **Log**: what happened, useful for troubleshooting.
- **About**: the version number.

### Browser sharing
Turn on **Browser sharing** on the Receive tab (or use *Send → Share files to a browser*). On any phone, tablet or PC on the same Wi-Fi, open `http://<phone-ip>:53317/` in a browser to:
- download the files you chose to share
- upload one or more files to the phone
- send a text message to the phone

Anyone on the same Wi-Fi can open that page while it's on, so turn it off when you're done.

When someone sends you files, RetroSend lists them and asks you to **Accept**. Progress shows in the title bar.

### Cancelling
While a transfer runs, the first Options item is **Cancel sending** (the other device is told) or **Stop receiving** (the half-received file is deleted).

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
pys60/build_sis.sh             # -> pys60/dist/RetroSend.sis and retrosend.py
sh pys60/tests/run.sh          # Python 2.2 syntax check + protocol, locate, media, picker, grid, web tests
```

`pys60/build_sis.sh` creates a self-signed certificate in `pys60/cert/` on first run. It's valid 2008-2037; see the install notes for why. Keep the key private: it's in `.gitignore`.

**Running without installing:** install Python for S60 and its *Script Shell*, copy `retrosend-<version>.py` from the release (or `pys60/dist/retrosend.py`) to `E:\Python\`, then *Python → Options → Run script*. Errors show on screen.

## How it works

RetroSend implements the receiving and sending parts of the **[LocalSend protocol v2](https://github.com/localsend/protocol)** over plain HTTP: `register`, `info`, `prepare-upload`, `upload` and `cancel`. Discovery is a UDP multicast announcement plus a UDP halving search for devices whose address PyS60 can't see. Text messages are a `text/plain` file with a `preview` field.

The native app targets **Python for S60 1.4.5** (Python 2.2.2, 2008), so the code avoids anything newer than Python 2.2 (`tools/check_py22.py` enforces this). Along the way it hit several PyS60 quirks, documented in **[docs/PYS60-NOTES.md](docs/PYS60-NOTES.md)**:

- Sockets only work on the **main thread**, through callbacks. A background thread has no Symbian active scheduler, and the app freezes. RetroSend is fully single-threaded and event-driven.
- `socket.close()` **stops the whole Wi-Fi connection** and closes the shared socket server, so RetroSend never closes sockets while running (it uses `shutdown()` instead).
- `bind(("", port))` fails. Use `"0.0.0.0"`.
- `accept()` reports a wrong peer address (`0.8.0.0`), and `getpeername()` isn't implemented. So when a LocalSend device registers, RetroSend finds its IP by announcing to half of the remaining addresses per round (UDP, no connections) and watching for its answer.
- `random.randint(0, 0x7fffffff)` overflows on Python 2.2.

## Project layout

```
pys60/                  native S60 app (Python for S60 1.4.5)
  retrosend.py          the app: protocol, async networking, UI, picker; VERSION is defined here
  launcher.py           tiny starter (installed as default.py): shows any start-up error on screen
  media.py              ID3 tags/album art and MP4 duration    } pasted into the app
  grid.py               photo grid screen                      } at build time
  webshare.py           browser sharing (web page, download/upload) }
  picker.py             file picker, previews, shared drawing helpers }
  transfer.py           full-screen transfer progress           }
  build_sis.sh          builds RetroSend.sis (reads VERSION from retrosend.py)
  icon.svg
  tests/                PC tests with stand-ins for the S60 modules (appuifw, e32, ...)
  tools/check_py22.py   rejects Python features newer than 2.2
tools/setup.sh          downloads the build tools
tools/ensymble-retrosend.patch   makes Ensymble work with current OpenSSL on Linux
docs/PYS60-NOTES.md     PyS60 pitfalls found while building this
```

## Credits

- [LocalSend](https://localsend.org) and its [protocol](https://github.com/localsend/protocol). RetroSend is an independent client, not affiliated with LocalSend.
- [Python for S60](https://sourceforge.net/projects/pys60/) by Nokia. The releases include Nokia's signed Python for S60 1.4.5 runtime, unchanged.
- [Ensymble](https://github.com/essaic/ensymble) by Jussi Ylänen, for building SIS packages.
