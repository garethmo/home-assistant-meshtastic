from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import helpers
from .entity import MeshtasticNodeEntity

if TYPE_CHECKING:
    from . import MeshtasticConfigEntry

_LOGGER = logging.getLogger(__name__)


def _build_buttons(nodes, runtime_data):
    """Build button entities for all nodes."""
    _LOGGER.info("Building buttons for %d nodes: %s", len(nodes), list(nodes.keys()))
    coordinator = runtime_data.coordinator
    gateway = runtime_data.client.get_own_node()
    
    entity_description = ButtonEntityDescription(
        key="reboot",
        name="Reboot",
        icon="mdi:restart",
    )
    
    buttons = [
        MeshtasticNodeRebootButton(
            coordinator=coordinator,
            entity_description=entity_description,
            gateway=gateway,
            node_id=node_id,
            client=runtime_data.client,
        )
        for node_id in nodes
    ]
    _LOGGER.info("Created %d button entities", len(buttons))
    return buttons


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeshtasticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Meshtastic button entities."""
    _LOGGER.info("Setting up Meshtastic button platform for entry %s", entry.entry_id)
    await helpers.setup_platform_entry(hass, entry, async_add_entities, _build_buttons)


class MeshtasticNodeRebootButton(MeshtasticNodeEntity, ButtonEntity):
    """Meshtastic node reboot button."""

    def __init__(self, coordinator, entity_description, gateway, node_id: int, client) -> None:
        """Initialize the button."""
        super().__init__(coordinator, gateway, node_id, Platform.BUTTON, entity_description)
        self._client = client

    def _async_update_attrs(self) -> None:
        """Update attributes - buttons don't need to update from coordinator."""
        # Buttons don't have state that needs updating from coordinator data
        pass

    async def async_press(self) -> None:
        """Handle the button press - reboot the node."""
        _LOGGER.info("Rebooting node %s", self._node_id)
        
        # Send reboot command with 5 second delay
        await self._client.reboot(5)
