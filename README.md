# 3D printed Super 8 Film Scanner

Using OpenCV and Open Source software to scan and create videos from Super 8 film reel, along with a 3D printed frame.

The code and scanner were created quickly to achieve the job of scanning a handful of Super 8 reels at an acceptable quality.

The code is not optimised or user friendly, but pull requests are very welcome!

## New web app (work in progress)

The scripts in `legacy/` are the original Marlin-based workflow, kept for reference. The new version is `app/` (Pi web UI) plus `firmware/` (RP2040 controller).

On Raspberry Pi OS (Bookworm):

    sudo apt install -y python3-picamera2 python3-opencv python3-numpy
    python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m app --config scanner.json

Open `http://<pi-hostname>.local:8000`. There is no login, so only run it on a network you trust: anyone on the network can move the motors and the light from the page or the console whenever no scan is running. Console moves are capped (20,000 steps and 15 s per move), and a move cannot be stopped from the app.
Each reel is saved to `scans/<name>/frames/` as aligned, uncropped PNGs, with `scan.json`. The device does not make a video: see "Encoding on a desktop" below.

A 50 ft reel is about 3,600 frames of about 20 MB PNGs, so roughly 70-80 GB: check free disk space before a scan.
The page shows the live gate with the target row, scan controls, camera and light settings, flagged frames, and a terminal at the bottom. The terminal lists every command sent to the controller (`→`), its reply (`←`), scan events such as nudges and winds (`●`) and errors (`✗`), and lets you type `ADVANCE`, `WIND`, `LIGHT` or `STATUS` yourself while no scan is running (type `help` for the arguments). It keeps the last 500 entries in memory; Clear only clears your view.
Hardware numbers (steps per frame, motor rates, sprocket threshold) live in `scanner.json`; see `app/config.py` for every setting and its default.

## Encoding on a desktop

The Pi only collects frames. Copy `scans/<name>/` to a desktop and encode it there; a stronger CPU or a GPU is much faster than the Pi. Install `ffmpeg` (`brew install ffmpeg`, `sudo apt install ffmpeg`, or `winget install ffmpeg`), then:

    python tools/encode_reel.py scans/<name>

This writes `scans/<name>/reel.mp4` (H.264, 18 fps). It needs only Python 3 and ffmpeg. With `--encoder auto` (the default) it uses the first hardware encoder your ffmpeg offers (nvenc, videotoolbox, qsv, amf, vaapi) and, if that one fails to start, tries the next available hardware encoder and then the CPU encoder; it prints which one made the file. Useful options:

- `--encoder cpu|nvenc|videotoolbox|qsv|amf|vaapi` to force one (no fallback), `--codec hevc` for H.265, `--height 1080` for a smaller copy, `--output PATH`, `--fps N` (integer). Encoding goes to `reel.part.mp4` first and replaces `reel.mp4` only on success, so a failed run keeps an earlier file.
- `--quality N`: one number whose meaning depends on the encoder. `cpu`: CRF, lower is better, default 15. `nvenc`, `qsv`, `amf`, `vaapi`: quantizer, lower is better (defaults 19, 20, 18, 20). `videotoolbox`: 0-100, higher is better (default 65).
- `--list-encoders` shows what your ffmpeg offers and which one auto would pick. `--dry-run` prints the exact ffmpeg command and exits without encoding.
- Missing frames (a lost write) are listed in a warning; the video skips them.

What is tested: pytest checks the command building for every encoder and the CPU path's command, with no ffmpeg needed. Only these have been run, by hand, on one Mac with synthetic frames and never on a real scan: `libx264`, `libx265` and `h264_videotoolbox`. `hevc_videotoolbox` and every NVIDIA (nvenc), Intel (qsv), AMD (amf) and VAAPI encoder, for both H.264 and HEVC, have not been run. The default quality values for the hardware encoders are unverified, so check the first result by eye. If one fails, use `--encoder cpu`.

Without the tool, this ffmpeg command does the same for the CPU path, from inside the reel folder:

    ffmpeg -framerate 18 -start_number 0 -i frames/frame_%08d.png -vf scale=trunc(iw/2)*2:trunc(ih/2)*2 -c:v libx264 -preset slower -crf 15 -pix_fmt yuv420p reel.mp4

Design notes: [architecture](docs/design/architecture.md), [hardware](docs/design/hardware.md), [wiring](docs/design/wiring.md), [bill of materials](docs/design/bom.md), [datasheets](docs/datasheets/README.md). Project plan and next steps: [roadmap](docs/ROADMAP.md).

The code is unlikely to run straight out of the box on your computer/system, it will need minor amendments to folder names/paths etc.


Items needed for this project:
* [Raspberry Pi 4](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/)
* [Pi Advanced 12megapixel Camera](https://www.raspberrypi.com/products/raspberry-pi-high-quality-camera/)
* [Microscope lens for the Raspberry Pi High Quality Camera - 0.12-1.8x](https://shop.pimoroni.com/products/microscope-lens-0-12-1-8x)
* 3D printed frame (files in this repository)
* Two small depth stepper motors (NEMA 17 style)
* RAMPS style motherboard for controlling the stepper motors and running [MARLIN](https://github.com/MarlinFirmware/Marlin)
* Two stepper drivers (for example A4988)
* ~5000K "cool white" MR16 style LED light bulb (5 Watt)
* 240V Power supply (an old Ender3 PSU will do)
* MicroSD card

# YouTube video

See the video on how to use and build this device.

https://youtu.be/rd1Xu6e6nrw

# Setup (legacy)

This is a rough setup description and some steps might be missing, but here is what's necessary:

## Step 1 - Flash Marlin to the mainboard
Flash your mainboard with the Marlin Firmware. You can find the latest release [here](https://marlinfw.org/meta/download/).

Open Arduino IDE, make the required changes (for your mainboard), connect the Mainboard via USB and upload the firmware to the Mainboard.

## Step 2 - Install RaspOS on the Raspberry Pi
Install the Raspberry Pi Imager, which you can find [here](https://www.raspberrypi.com/software/).

Plug in the microSD card into your computer and choose to install the **Legacy 32-bit OS** in the imager software. Use CTRL+SHIFT+X to open the advanced settings.  Choose a hostname, for example "scanner". Then add a username and password. Activate SSH under "services" and add your Wifi settings.

## Step 3 - Wiring
Assemble the scanner according to the 3D files.

![Mainboard](Sample_Images/mainboardcabeling.png)

Plug in the stepper drivers into the mainboards Y and Z axis, then plug in the stepper motors in these axis. You should add the heatsink to the Y axis stepper driver, as it's the one used the most.

Slot the Raspberry Pi HQ cameras ribbon cable into the Raspberry Pi and lock it in place. 

Plug the LED wires into the fan header. 

Connect the power supply to the mainboard via the two cables. Make sure the power supply is disconnected.

Connect the mainboard to the Raspberry Pi.

## Step 4 - Connecting to the Raspberry Pi
If you don't plan to use the scanner with dedicated monitor, keyboard and mouse, you have to connect to it via Terminal and VNC. 

Turn on the Raspberry Pi and the PSU. 

Use SSH to connect to <username>@scanner.local, then install VNC server to control your scanner in the future. If your screen stays black after connecting, run "vncserver-virtual" to add a virtual display. 

## Step 5 - Install dependencies
To install OpenCV, run `sudo apt-get update` , then `sudo apt-get install build-essential cmake pkg-config libjpeg-dev libtiff5-dev libjasper-dev libpng-dev libavcodec-dev libavformat-dev libswscale-dev libv4l-dev libxvidcore-dev libx264-dev libfontconfig1-dev libcairo2-dev libgdk-pixbuf2.0-dev libpango1.0-dev libgtk2.0-dev libgtk-3-dev libatlas-base-dev gfortran libhdf5-dev libhdf5-serial-dev libhdf5-103 python3-pyqt5 python3-dev -y`

you might also need to run `pip install opencv-python==4.5.3.56` .

# Scanning Process (legacy)

## Step 1 - Capture full frame masters

On a Raspberry Pi (4 is possible), use the python code in `RasPi_Camera_Super8Scanner.py` to capture all the individual frames to individual PNG files.

This will generate a large number of files (3000+) of significant file size 2+MByte each.  Camera captures approximately 3megapixel images.

Scanning is slow, running around 1.25 frames per second, so a 3 minute reel takes 1 hour.  

Speed was not a critical issue when designing this solution, however the longest delay is capturing the image from the Raspberry Pi camera.

The images captured would look like this (only higher resolution).  Notice you can see the sproket hole and the black border on the right of the image.
![Full frame sample image](Sample_Images/Full_Frame_Sample.png)

## Step 2 - Alignment

Step one captured the full frame of the film, this process takes those master images and accurately crops them to vertically and horizontally align them based on the sproket hole.

OpenCV is used to detect the hole and align/crop the image.

The code is in `ImageRegistrationCropping.py` its likely you will need to tweak the code to cater for the particular file size/resolution you are using and the camera configuration.

Look for the variable `frame_dims` to control the output image dimensions.  Its likely you will also need to change the folder names.

The files are put into a folder named "Aligned".  Example image.
![Aligned frame sample image](Sample_Images/Aligned_Sample.png)

You can modify the provided `config.json` file to suit your needs. These are the available configurations:

```json
{
    "image_name": "frame_????????", // The name of the images to be processed
    "input_path": "Capture", // The folder where the images are stored
    "output_path": "Aligned", // The folder where the aligned images will be stored
    "extensions": ["png", "jpg", "jpeg"], // The extensions of the images to be processed
    "average_sample_count": 11, // This will be saved automatically if you run a new analysis
    "average_width": 512, // This will be saved automatically if you run a new analysis
    "average_height": 649, // This will be saved automatically if you run a new analysis
    "average_area": 306419, // This will be saved automatically if you run a new analysis
    "resize_image": [ // if you want to resize the images after alignment
        3840, // width
        2160 // height
    ],
    "frame_dims": [ // You can get this after adjusting the first frame dimensions
        0, // x offset
        -904, // y offset
        3192, // width
        2305 // height
    ]
}
```

## Step 3 - Denoise (optional)

A post process called de-noise filtering can be used to improve image quality.  This code can be found in `Denoise.py`

This is a significantly slow process, so a faster CPU helps a lot.  You can tweak the amount of correction made with these values

```
h=3, hColor=3, templateWindowSize=7,searchWindowSize=29
```

For a description of the paramters, check out the [OpenCV documentation](https://docs.opencv.org/3.4/d1/d79/group__photo__denoise.html#gaa501e71f52fb2dc17ff8ca5e7d2d3619).

The files are put into a folder named "Denoise".  Example image.
![Frame after denoise filtering](Sample_Images/After_DeNoise.png)

## Step 4 - Create Video

### FFMPEG
You can use the open source FFMPEG tool to convert a series of pictures into a video, using a command similar to this:
```
ffmpeg.exe -y -start_number 0 -framerate 18 -i "Aligned\frame_%08d.png" -vcodec h264 -preset slower -tune grain -crf 15 -vf "fps=18,format=yuv420p" -r 18 film_output.mp4
```

### Video editor software
Alternatively, use video editing software like [Davinci Resolve](https://www.blackmagicdesign.com/products/davinciresolve/) to import the pictures and generate a video.

This can also be used to colour correct the film, remove noise and grain and generally improve the final video.
