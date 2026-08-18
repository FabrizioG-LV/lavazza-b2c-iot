"""Constants for the lavazza_b2c_iot integration."""

DOMAIN = "lavazza_b2c_iot"

# Broker endpoint (internal, not user-configurable)
BROKER_URL = "https://your-broker-url.workers.dev"

# Broker security: pre-shared key (same value as BROKER_KEY in worker env)
BROKER_KEY = "your-broker-key-here"

# Config flow keys
CONF_COUNTRY = "country"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_ACCESS_TOKEN = "access_token"
CONF_UID = "uid"
CONF_TOKEN_TYPE = "token_type"
CONF_INSTALLATION_ID = "installation_id"
CONF_CLIENT_SECRET = "client_secret"

# FCM config (from broker)
CONF_FCM_CONFIG = "fcm_config"
CONF_FIREBASE_PROJECT_ID = "firebase_project_id"
CONF_FIREBASE_APP_ID = "firebase_app_id"
CONF_FIREBASE_SENDER_ID = "firebase_sender_id"
CONF_FIREBASE_API_KEY = "firebase_api_key"
CONF_APP_PACKAGE_NAME = "app_package_name"

# API endpoints map (from broker)
CONF_API_ENDPOINTS = "api_endpoints"

# FCM credentials (per-installation, saved after first checkin)
CONF_FCM_CREDENTIALS = "fcm_credentials"

# Entity registration
UNIQUE_ID_DEVICE = "{serial}"
UNIQUE_ID_SENSOR = "{serial}_{key}"
UNIQUE_ID_BUTTON = "{serial}_{code}"
UNIQUE_ID_ACCOUNT = "{entry_id}_{key}"

# API defaults
APP_VERSION = "V99.99.99"  # Arbitrary high version to avoid WAF flags; actual version is optional

# Logging
LOGGER_NAME = f"custom_components.{DOMAIN}"

# Coordinator names
COORDINATOR_DEVICE_LIST = "device_list"
COORDINATOR_DEVICE_STATE = "device_state"
COORDINATOR_DEVICE_ERRORS = "device_errors"
COORDINATOR_ACCOUNT_PROFILE = "account_profile"
