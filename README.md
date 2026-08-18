# Lavazza B2C IoT

Home Assistant integration for Lavazza cloud-connected coffee machines. Control your machine, monitor status, and receive real-time updates.

## Features

- **Real-time state updates**: Instant status changes from your machine
- **Device control**: Power on/off, start brewing, stop brewing, and more
- **Status monitoring**: Machine state, sensors (water level, temperature, etc.), and error codes
- **Custom recipes**: List and prepare your saved custom beverages
- **Diagnostics**: WiFi connection status, firmware info, physical button settings
- **Multi-country support**: IT, AU, UK, GB, DK, DE, FR, US

## Installation

### Via HACS (recommended)

1. Go to **Settings → Devices & Services → HACS**
2. Search for **"Lavazza B2C IoT"**
3. Click **Install**
4. Restart Home Assistant

### Manual Installation

1. Download this repository
2. Copy `custom_components/lavazza_b2c_iot/` to `custom_components/` in your Home Assistant config directory
3. Restart Home Assistant

## Configuration

### Initial Setup

1. Go to **Settings → Devices & Services → Create Integration**
2. Select **"Lavazza B2C IoT"**
3. Enter:
   - **Country**: Select your country (IT, AU, UK, GB, DK, DE, FR, US)
   - **Email**: Your Lavazza account email
   - **Password**: Your Lavazza account password

The integration will authenticate with your Lavazza account and establish real-time updates.

## Entities

### Device State Sensor

Shows the current state of your machine (e.g., idle, brewing, error).

**Entity ID**: `sensor.<device_serial>_state`

### Device Sensors

Dynamic sensors are created based on your machine type and available data:

- Water level, temperature, pressure
- Firmware version, WiFi status
- Custom recipe list (if available)

### Device Commands (Buttons)

Press buttons to control your machine:

- **Power On / Power Off**: Turn the machine on or off
- **Start Brewing**: Begin preparing a beverage
- **Stop Brewing**: Stop an in-progress operation
- **Prepare Favorite**: Start a custom recipe (if configured)

**Example automation:**

```yaml
automation:
  - alias: Make Coffee in the Morning
    trigger:
      platform: time
      at: "07:00:00"
    action:
      service: button.press
      target:
        entity_id: button.my_machine_start_brewing
```

## Troubleshooting

### Authentication Failed

- Verify your email and password are correct
- Ensure your Lavazza account is active and accessible from your region
- Check network connectivity to Lavazza servers

### No State Updates

- Ensure the integration is properly installed and running
- Verify your machine is connected to WiFi and reachable by Lavazza services
- Try manually reloading the integration from Settings → Devices & Services

### Missing Entities

Some entities may not be available depending on your machine model. Unsupported sensors appear with their raw code values for debugging.

## Support & Contributing

For issues, feature requests, or contributions, please open an issue on the project repository.

## License

This integration is provided as-is for personal use. See LICENSE for details.

---

**Note**: This integration communicates with Lavazza cloud services. Your credentials are used only for authentication and are never logged or shared.
