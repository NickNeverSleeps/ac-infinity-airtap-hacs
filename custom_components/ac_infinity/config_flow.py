from __future__ import annotations

import logging
from typing import Any

from ac_infinity_ble.const import MANUFACTURER_ID
from bleak import BleakClient
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS, CONF_SERVICE_DATA
from homeassistant.data_entry_flow import FlowResult

from .const import BLEAK_EXCEPTIONS, DOMAIN
from .device import ACInfinityDevice, DeviceInfoEx

_LOGGER = logging.getLogger(__name__)


def parse_manufacturer_data(data: bytes) -> DeviceInfoEx:
    from ac_infinity_ble.protocol import parse_manufacturer_data as parse
    return DeviceInfoEx.create(parse(data))


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        try:
            device = parse_manufacturer_data(
                discovery_info.advertisement.manufacturer_data[MANUFACTURER_ID]
            )
        except Exception:  # pylint: disable=broad-except
            _LOGGER.debug(
                "Could not parse advertisement from %s; allowing manual setup",
                discovery_info.address,
                exc_info=True,
            )
        else:
            self.context["title_placeholders"] = {"name": device.name}
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]
            await self.async_set_unique_id(
                discovery_info.address, raise_on_progress=False
            )
            self._abort_if_unique_id_configured()
            try:
                controller = ACInfinityDevice(
                    discovery_info.device,
                    advertisement_data=discovery_info.advertisement,
                )
                await controller.update()
            except BLEAK_EXCEPTIONS:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"
            else:
                await controller.stop()
                return self.async_create_entry(
                    title=controller.name,
                    data={
                        CONF_ADDRESS: discovery_info.address,
                        CONF_SERVICE_DATA: parse_manufacturer_data(
                            discovery_info.advertisement.manufacturer_data[
                                MANUFACTURER_ID
                            ]
                        ),
                    },
                )

        if discovery := self._discovery_info:
            self._discovered_devices[discovery.address] = discovery
        else:
            current_addresses = self._async_current_ids()
            for discovery in async_discovered_service_info(self.hass):
                if (
                    discovery.address in current_addresses
                    or discovery.address in self._discovered_devices
                    or MANUFACTURER_ID
                    not in discovery.advertisement.manufacturer_data
                ):
                    continue
                self._discovered_devices[discovery.address] = discovery

        if not self._discovered_devices:
            return await self.async_step_manual()

        _LOGGER.debug("Discovered devices: %s", self._discovered_devices)

        devices = {}
        for service_info in self._discovered_devices.values():
            if MANUFACTURER_ID not in service_info.advertisement.manufacturer_data:
                continue
            try:
                device = parse_manufacturer_data(
                    service_info.advertisement.manufacturer_data[MANUFACTURER_ID]
                )
            except Exception:  # pylint: disable=broad-except
                _LOGGER.debug(
                    "Could not parse advertisement from %s",
                    service_info.address,
                    exc_info=True,
                )
                continue
            devices[service_info.address] = f"{device.name} ({service_info.address})"

        # A generic Bluetooth discovery may find nearby, unrelated devices.  Do
        # not send an empty ``vol.In`` mapping to the frontend: it renders as
        # an "address" label with no selectable input.
        if not devices:
            return await self.async_step_manual()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(devices),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle setup with a Bluetooth address supplied by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            discovery_info = next(
                (
                    discovery
                    for discovery in async_discovered_service_info(self.hass)
                    if discovery.address.upper() == address
                ),
                None,
            )

            if discovery_info is None:
                errors["base"] = "address_not_found"
            elif not (
                ble_device := bluetooth.async_ble_device_from_address(
                    self.hass, discovery_info.address, connectable=True
                )
            ):
                errors["base"] = "address_not_found"
            else:
                # A manual address is intentional: do not reject it merely
                # because its cached advertisement is incomplete or malformed.
                # First prove that Home Assistant can actually connect, then
                # reuse the integration's protocol-level connection test.
                client = BleakClient(ble_device)
                try:
                    await client.connect()
                except BLEAK_EXCEPTIONS:
                    errors["base"] = "cannot_connect"
                finally:
                    if client.is_connected:
                        try:
                            await client.disconnect()
                        except BLEAK_EXCEPTIONS:
                            _LOGGER.debug(
                                "Error disconnecting from %s after setup test",
                                discovery_info.address,
                                exc_info=True,
                            )

                if errors:
                    return self.async_show_form(
                        step_id="manual",
                        data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
                        errors=errors,
                    )

                self._discovered_devices[discovery_info.address] = discovery_info
                return await self.async_step_user(
                    {CONF_ADDRESS: discovery_info.address}
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
            errors=errors,
        )
