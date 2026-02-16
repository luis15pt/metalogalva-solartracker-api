#!/bin/bash
#
# Setup Wine + Box86 on Raspberry Pi 5 (ARM64)
# This allows running the Windows STcontrol app for protocol validation
#
set -e

echo '=== Setting up Wine + Box86 on Raspberry Pi 5 ==='
echo 'This may take 10-15 minutes...'
echo ''

# Add armhf architecture for 32-bit libraries
echo '[1/7] Adding armhf architecture...'
sudo dpkg --add-architecture armhf
sudo apt-get update

# Install core dependencies
echo '[2/7] Installing core 32-bit libraries...'
sudo apt-get install -y \
    libc6:armhf \
    libstdc++6:armhf \
    libx11-6:armhf \
    libxext6:armhf \
    libfreetype6:armhf \
    libfontconfig1:armhf \
    libglib2.0-0:armhf \
    libasound2:armhf \
    libpng16-16:armhf \
    libncurses6:armhf \
    zlib1g:armhf

# Install Box86 from Pi-Apps repo
echo '[3/7] Adding Box86 repository...'
wget -qO- https://pi-apps-coders.github.io/box86-debs/KEY.gpg | sudo gpg --dearmor -o /usr/share/keyrings/box86-archive-keyring.gpg 2>/dev/null || true
echo 'deb [signed-by=/usr/share/keyrings/box86-archive-keyring.gpg] https://Pi-Apps-Coders.github.io/box86-debs/debian ./' | sudo tee /etc/apt/sources.list.d/box86.list > /dev/null
sudo apt-get update

echo '[4/7] Installing Box86...'
sudo apt-get install -y box86-rpi5arm64 || sudo apt-get install -y box86-generic-arm || {
    echo 'Box86 package not available, building from source...'
    sudo apt-get install -y git build-essential cmake
    cd /tmp
    git clone https://github.com/ptitSeb/box86.git
    cd box86
    mkdir build && cd build
    cmake .. -DRPI5ARM64=1 -DCMAKE_BUILD_TYPE=RelWithDebInfo
    make -j$(nproc)
    sudo make install
}

# Install Wine (32-bit)
echo '[5/7] Installing Wine...'
# Try pre-built wine for ARM
if ! command -v wine &> /dev/null; then
    # Download wine-i386 built for Box86
    cd /tmp
    wget -q https://github.com/Kron4ek/Wine-Builds/releases/download/8.21/wine-8.21-x86.tar.xz -O wine.tar.xz || \
    wget -q https://github.com/Kron4ek/Wine-Builds/releases/download/7.0/wine-7.0-x86.tar.xz -O wine.tar.xz

    sudo mkdir -p /opt/wine
    sudo tar -xf wine.tar.xz -C /opt/wine --strip-components=1

    # Create symlinks
    sudo ln -sf /opt/wine/bin/wine /usr/local/bin/wine
    sudo ln -sf /opt/wine/bin/wineserver /usr/local/bin/wineserver
    sudo ln -sf /opt/wine/bin/wineboot /usr/local/bin/wineboot
fi

# Install display server (VNC)
echo '[6/7] Installing VNC server...'
sudo apt-get install -y tigervnc-standalone-server xvfb x11-apps

# Initialize Wine prefix
echo '[7/7] Initializing Wine (this may take a few minutes)...'
export DISPLAY=:99
Xvfb :99 -screen 0 1024x768x16 &
XVFB_PID=$!
sleep 2

export WINEPREFIX="$HOME/.wine32"
export WINEARCH=win32
export BOX86_LOG=0
export BOX86_NOBANNER=1

# Initialize wine
wine wineboot --init 2>/dev/null || true
sleep 5

# Kill Xvfb
kill $XVFB_PID 2>/dev/null || true

echo ''
echo '=== Setup complete! ==='
echo ''
echo 'To run the Windows app:'
echo '  1. Start VNC server: vncserver :1 -geometry 1024x768'
echo '  2. Connect via VNC to pi:5901'
echo '  3. Run: DISPLAY=:1 wine "/path/to/STcontrol V4.0.4.0.exe"'
echo ''
echo 'Or run headless with Xvfb:'
echo '  Xvfb :99 -screen 0 1024x768x16 &'
echo '  DISPLAY=:99 wine "/path/to/STcontrol V4.0.4.0.exe"'
