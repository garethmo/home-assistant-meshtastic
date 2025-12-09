# SPDX-FileCopyrightText: 2024-2025 Pascal Brogle @broglep
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.text import TextEntity
from homeassistant.core import callback, Event
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    EVENT_MESHTASTIC_DOMAIN_EVENT,
    EVENT_MESHTASTIC_DOMAIN_EVENT_DATA_ATTR_MESSAGE,
    MeshtasticDomainEventType,
)
from .entity import GatewayChannelEntity, GatewayDirectMessageEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from .data import MeshtasticConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeshtasticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Meshtastic text entities."""
    client = entry.runtime_data.client
    gateway_node = await client.async_get_own_node()
    channels = await client.async_get_channels()
    
    # Create entities for channels
    entities = []
    for channel in channels:
        if channel["role"] != "DISABLED":
            entities.append(
                MeshtasticChannelText(
                    entry.entry_id,
                    gateway_node["num"],
                    channel["index"],
                    channel["settings"]["name"],
                    channel["role"] == "PRIMARY",
                    channel["role"] == "SECONDARY",
                    client,
                )
            )
            
    # Create entity for Direct Messages
    entities.append(
        MeshtasticDirectMessageText(
            entry.entry_id,
            gateway_node["num"],
            client,
        )
    )

    async_add_entities(entities)


class MeshtasticChatMixin:
    """Mixin for Meshtastic Chat entities."""
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    _history: list[dict[str, Any]]

    def __init__(self) -> None:
        self._history = []
        self._attr_extra_state_attributes = {"history": self._history}

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_MESHTASTIC_DOMAIN_EVENT, self._on_meshtastic_event)
        )

    @callback
    def _on_meshtastic_event(self, event: Event) -> None:
        """Handle incoming Meshtastic events."""
        # This method should be overridden or implemented to filter relevant events
        pass

    def _add_to_history(self, from_node: str, message: str, timestamp: float) -> None:
        """Add a message to the history."""
        self._history.append({
            "from": from_node,
            "message": message,
            "timestamp": timestamp,
        })
        # Keep last 50 messages
        if len(self._history) > 50:
            self._history.pop(0)
        
        self._attr_extra_state_attributes["history"] = self._history
        # Do not update native_value (input box) with received message
        self.async_write_ha_state()


class MockGatewayEntity:
    def __init__(self, suggested_object_id: str):
        self.suggested_object_id = suggested_object_id

class MeshtasticChannelText(MeshtasticChatMixin, GatewayChannelEntity, TextEntity):
    """Representation of a Meshtastic Channel Chat."""

    def __init__(
        self,
        config_entry_id: str,
        gateway_node: int,
        index: int,
        name: str,
        primary: bool,
        secondary: bool,
        client: Any,
    ) -> None:
        # Mock gateway entity for suggested_object_id
        # We don't have easy access to the real GatewayEntity here without passing it down
        # But we can reconstruct the suggested ID: "gateway shortname"
        # For now, let's just use a placeholder or try to get it from client?
        # client.get_own_node() has user info.
        
        own_node = client.get_own_node()
        short_name = own_node.get("user", {}).get("shortName", "UNK")
        gateway_entity = MockGatewayEntity(f"gateway {short_name}")

        GatewayChannelEntity.__init__(
            self,
            config_entry_id,
            gateway_node,
            gateway_entity,
            index,
            name,
            {"psk": "", "uplinkEnabled": True, "downlinkEnabled": True},
            primary,
            secondary,
            has_logbook=False,
        )
        MeshtasticChatMixin.__init__(self)
        self._client = client
        self._attr_name = (name or ("Primary" if primary else "Secondary" if secondary else f"Channel {index}")) + " Chat"
        self._attr_unique_id = f"{config_entry_id}_chat_channel_{gateway_node}_{index}"

    async def async_set_value(self, value: str) -> None:
        """Send a text message."""
        await self._client.send_text(value, channel_index=self._index)
        self._attr_native_value = ""
        self.async_write_ha_state()

    @callback
    def _on_meshtastic_event(self, event: Event) -> None:
        """Handle incoming Meshtastic events."""
        data = event.data
        
        channel_unique_id = GatewayChannelEntity.build_unique_id(
            self._attr_unique_id.split("_")[0],
            int(self._attr_unique_id.split("_")[3]),
            self._index
        )
        
        er_instance = er.async_get(self.hass)
        channel_entity_id = er_instance.async_get_entity_id(DOMAIN, DOMAIN, channel_unique_id)
        
        if channel_entity_id and data.get("entity_id") == channel_entity_id:
             self._add_to_history(data.get("from", "?"), data.get("message", ""), event.time_fired.timestamp())

    @property
    def suggested_object_id(self) -> str | None:
        """Return a predictable object ID."""
        # Clean up name for ID: "Primary Chat" -> "primary_chat"
        clean_name = self._attr_name.lower().replace(" ", "_")
        return f"meshtastic_{clean_name}"


class MeshtasticDirectMessageText(MeshtasticChatMixin, GatewayDirectMessageEntity, TextEntity):
    """Representation of a Meshtastic Direct Message Chat."""

    def __init__(
        self,
        config_entry_id: str,
        gateway_node: int,
        client: Any,
    ) -> None:
        own_node = client.get_own_node()
        short_name = own_node.get("user", {}).get("shortName", "UNK")
        gateway_entity = MockGatewayEntity(f"gateway {short_name}")

        GatewayDirectMessageEntity.__init__(
            self,
            config_entry_id,
            gateway_node,
            gateway_entity,
            has_logbook=False,
        )
        MeshtasticChatMixin.__init__(self)
        self._client = client
        self._attr_name = "Direct Message Chat"
        self._attr_unique_id = f"{config_entry_id}_chat_dm_{gateway_node}"

    async def async_set_value(self, value: str) -> None:
        """Send a text message."""
        # For DM, we need a destination.
        # Text entity doesn't support extra arguments in set_value.
        # So this entity can only broadcast? Or reply to last?
        # Or maybe we parse "dest: message"?
        # For now, let's just broadcast (or fail).
        # Actually, send_text without destination is broadcast.
        await self._client.send_text(value)
        self._attr_native_value = ""
        self.async_write_ha_state()

    @callback
    def _on_meshtastic_event(self, event: Event) -> None:
        """Handle incoming Meshtastic events."""
        data = event.data
        
        dm_unique_id = GatewayDirectMessageEntity.build_unique_id(
            self._attr_unique_id.split("_")[0],
            int(self._attr_unique_id.split("_")[3])
        )
        
        er_instance = er.async_get(self.hass)
        dm_entity_id = er_instance.async_get_entity_id(DOMAIN, DOMAIN, dm_unique_id)
        
        if dm_entity_id and data.get("entity_id") == dm_entity_id:
             self._add_to_history(data.get("from", "?"), data.get("message", ""), event.time_fired.timestamp())

    @property
    def suggested_object_id(self) -> str | None:
        """Return a predictable object ID."""
        return "meshtastic_direct_message_chat"
