"""Enphase Envoy Raw Data Support.

This custom integration registers an enphase_envoy_raw_data integration
that only provides a read_data(endpoint) and send_data(endpoint,data)
action/service. No entities are provided.

!!! SENDING DATA TO AN ENVOY ENDPOINT HAS RISK FOR PROPER OPERATION OF THE ENVOY.
DOING SO IS AT YOUR OWN RISK AND SHOULD ONLY BE DONE FULLY UNDERSTANDING ANY EFFECT OF IT !!!

This integration does not replace the core integration. It can be used next to it
"""

from pyenphase import EnvoyAuthenticationError, EnvoyAuthenticationRequired

DOMAIN = "enphase_envoy_raw_data"

CONF_UPDATER = "updater"

NAME = "Enphase Envoy Raw Data"

ENVOY_NAME = "Envoy-raw-data"

UNIQUE_ID = f"{DOMAIN}_for_"

INVALID_AUTH_ERRORS = (EnvoyAuthenticationError, EnvoyAuthenticationRequired)
