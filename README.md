# Lavazza B2C IoT — Home Assistant Integration

Control your Lavazza IoT coffee machine directly from Home Assistant. Get live device status, brew alerts, and maintenance notifications.

## Requirements

- **Home Assistant** 2024.1 or later
- **Lavazza B2C account** with at least one cloud-connected coffee machine

## Installation

### Via HACS (Recommended)

1. Open Home Assistant → **Settings** → **Devices & Services**
2. Click **Custom repositories** (bottom right)
3. Paste: `https://github.com/FabrizioG-LV/lavazza-b2c-iot`
4. Category: **Integration**
5. Click **Create**, then **Install**
6. Restart Home Assistant

### Manual Installation

1. Download this repository
2. Copy `custom_components/lavazza_b2c_iot/` to `<HA config>/custom_components/`
3. Restart Home Assistant

## Setup

1. Go to **Settings** → **Devices & Services**
2. Click **Create Integration**
3. Search for **"Lavazza B2C IoT"**
4. Select your country
5. Enter your Lavazza B2C email and password
6. Done! Your devices and controls appear under **Devices & Services**

**First run takes 30 seconds** — the integration discovers your devices and sets up sensors/controls.

## What You Get

### Device Status
- Current state (Idle, Heating, Brewing, Descaling, etc.)
- Temperature and pressure sensors
- Maintenance reminders (descaling needed, pod count, etc.)

Error alert decoding (door open, empty water tank, etc.) is planned but not yet available in this release.

### Controls
- Command buttons (start/stop brewing, recipe selection) are planned but not yet available in this release — device status/sensors are fully functional, command execution is still in progress

### Supported Machines
- **Assoluta** (BTC) — Espresso with steam wand
- **Voicy** (VCY) — Single-serve pod system
- **Tablì** (TAB) — Multi-beverage pod system

## Updates & Status

Status updates happen automatically:
- **Instant** when you use the machine
- **Every 10 minutes** as a fallback if the machine is idle

No action needed — everything syncs on its own.

## Troubleshooting

### "Token Expired" Error
**Solution**: Go to **Settings** → **Devices & Services** → Your integration → **Reconfigure**. Re-enter your email/password.

### Device Not Found
**Check**:
1. Is the device linked in the official Lavazza app?
2. Did you select the correct country during setup?
3. Try unlinking/re-linking the device in the Lavazza app, then reconfigure the integration

### Entities Show "Unavailable"
**Common causes**:
- Device is turned off
- Device hasn't communicated recently (turn it on and use it)
- Home Assistant lost internet connection temporarily
- Machine error (check the machine's display)

**Solution**: Restart your machine or wait a few minutes for a refresh.

### No Entities Appear
**Try**:
1. Wait 30 seconds after setup (entities take time to load)
2. Refresh the page (F5 or Cmd+R)
3. Restart Home Assistant if nothing appears
4. Confirm the machine is actually linked to your account in the official Lavazza app — an account with no linked machines will set up successfully but create zero entities

## Support

- **Found a bug?** Report it on [GitHub Issues](https://github.com/FabrizioG-LV/lavazza-b2c-iot/issues)
- **Have a feature idea?** Let us know!

---

**Version**: 0.1.0  
**Author**: Fabrizio Giannini  
**License**: All rights reserved. This code is provided for personal reference/installation via HACS only; redistribution or modification is not authorized.
